# Architecture

## System Overview

The Always-On Memory Agent is a single-process Python application with multiple concurrent subsystems running on asyncio. It communicates with AWS Bedrock for LLM inference and uses SQLite for persistence.

```
┌─────────────────────────────────────────────────────────────────┐
│                         PROCESS (python -m src.main)             │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    asyncio Event Loop                     │   │
│  │                                                          │   │
│  │  Task 1: watch_folder()      - polls inbox every 5s      │   │
│  │  Task 2: consolidation_loop() - fires every 30 min       │   │
│  │  Task 3: aiohttp server      - handles HTTP requests     │   │
│  │                                                          │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐  │
│  │   config   │  │     db     │  │   tools    │  │  agents  │  │
│  │            │  │            │  │            │  │          │  │
│  │ Settings   │  │ Connection │  │ Definitions│  │ Client   │  │
│  │ Constants  │  │ Repository │  │ Executor   │  │ Memory   │  │
│  │            │  │            │  │            │  │ Agent    │  │
│  └────────────┘  └─────┬──────┘  └─────┬──────┘  └────┬─────┘  │
│                        │              │               │         │
│                        ▼              │               │         │
│                 ┌──────────────┐      │               │         │
│                 │  SQLite DB   │◄─────┘               │         │
│                 │  memory.db   │                      │         │
│                 └──────────────┘                      │         │
│                                                       ▼         │
│                                              ┌──────────────┐   │
│                                              │ AWS Bedrock  │   │
│                                              │ (boto3)      │   │
│                                              └──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Module Architecture

### Layer Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                      ENTRY POINTS                            │
│  src/main.py          CLI + async loop orchestration         │
│  dashboard.py         Streamlit UI (separate process)        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     SERVICE LAYER                             │
│  src/api/server.py    HTTP handlers (aiohttp)                │
│  src/watcher/         Background tasks (file + consolidation)│
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     AGENT LAYER                               │
│  src/agents/memory_agent.py   High-level operations          │
│  src/agents/client.py         Bedrock Converse + tool loop   │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     TOOL LAYER                                │
│  src/tools/definitions.py   JSON schemas for Bedrock         │
│  src/tools/executor.py      Routes calls → repository        │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     DATA LAYER                                │
│  src/db/repository.py    CRUD operations                     │
│  src/db/connection.py    SQLite connection + schema           │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                     CONFIG LAYER                              │
│  src/config/settings.py    Environment-driven configuration  │
│  src/config/constants.py   Static values (prompts, types)    │
└─────────────────────────────────────────────────────────────┘
```

### Dependency Flow

Dependencies flow **downward only**. Each layer depends only on the layer directly below it.

```
main.py → api, watcher, agents, db.init
api     → agents
watcher → agents, db.repository
agents  → tools, config
tools   → db.repository
db      → config
config  → (nothing - leaf node)
```

No circular dependencies. No upward references.

## Database Schema

```sql
-- Core memory storage
memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT,        -- origin (filename, "api", "dashboard")
    raw_text        TEXT,        -- original or described content
    summary         TEXT,        -- LLM-generated 1-2 sentence summary
    entities        TEXT (JSON), -- ["person", "company", ...]
    topics          TEXT (JSON), -- ["ai", "strategy", ...]
    connections     TEXT (JSON), -- [{linked_to: id, relationship: "..."}]
    importance      REAL,        -- 0.0 to 1.0
    created_at      TEXT (ISO),  -- UTC timestamp
    consolidated    INTEGER      -- 0 = pending, 1 = processed
)

-- Consolidation insights
consolidations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ids      TEXT (JSON), -- [1, 2, 3] memory IDs consolidated
    summary         TEXT,        -- cross-cutting summary
    insight         TEXT,        -- key pattern discovered
    created_at      TEXT (ISO)
)

-- Processed file tracking (prevent re-ingestion)
processed_files (
    path            TEXT PRIMARY KEY,
    processed_at    TEXT (ISO)
)
```

## Bedrock Integration

### Converse API Tool-Use Loop

```
User Message
     │
     ▼
┌─────────────┐     ┌──────────────────┐
│   Bedrock   │────►│  Response with   │
│   Converse  │     │  toolUse blocks  │
└─────────────┘     └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Tool Executor    │
                    │  (local Python)   │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Tool Results    │
                    │  sent back as    │
                    │  toolResult msg  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Bedrock final   │
                    │  text response   │
                    └──────────────────┘
```

Each agent type gets:
- A **system prompt** defining its role
- A **tool subset** (only the tools it needs)
- Up to **5 rounds** of tool calling before forced stop

### Model Selection Strategy

| Priority | Model | When |
|---|---|---|
| Cost | Nova Micro | Text-only, highest volume |
| Balance | Nova Lite | Default - multimodal + cheap |
| Quality | Claude Haiku | Better reasoning needed |
| Premium | Claude Sonnet | Complex consolidation |

Cross-region inference (`us.` prefix) distributes load across US regions.

## Concurrency Model

```
asyncio event loop (single thread)
│
├── Task: watch_folder()
│   └── Polls every 5s
│   └── Calls agent.ingest() (blocking boto3 call)
│
├── Task: consolidation_loop()
│   └── Sleeps for 30 min
│   └── Calls agent.consolidate() (blocking boto3 call)
│
└── Task: aiohttp server
    └── Handles concurrent HTTP requests
    └── Each request calls agent methods (blocking boto3 call)
```

**Note:** boto3 calls are synchronous. In this single-user agent, this is acceptable. For multi-tenant scale, the boto3 calls should be moved to a thread pool (`asyncio.to_thread()`).

## Security Model

- AWS credentials via environment variables (no files in container)
- SQLite file on local disk (not exposed to network)
- No authentication on HTTP API (designed for local/private network use)
- No PII in tool schemas or system prompts
- Container runs as non-root (when configured)

For production:
- Add API key auth to HTTP endpoints
- Encrypt SQLite at rest
- Use IAM roles (ECS/EKS) instead of access keys
- Enable CloudTrail for Bedrock API auditing
