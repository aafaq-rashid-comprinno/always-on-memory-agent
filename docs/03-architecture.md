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

The agent supports two backends, auto-selected by configuration:

### SQLite (default - `MEMORY_DB` path)

```sql
-- Core memory storage
memories (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT,
    raw_text        TEXT,
    summary         TEXT,
    entities        TEXT (JSON),
    topics          TEXT (JSON),
    connections     TEXT (JSON),
    importance      REAL,
    created_at      TEXT (ISO),
    consolidated    INTEGER
)

-- FTS5 virtual table for full-text search
memories_fts (summary, entities, topics)

-- Consolidation insights
consolidations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ids      TEXT (JSON),
    summary         TEXT,
    insight         TEXT,
    created_at      TEXT (ISO)
)

-- Deduplication
content_hashes (
    hash            TEXT PRIMARY KEY,
    created_at      TEXT (ISO)
)

-- File tracking
processed_files (
    path            TEXT PRIMARY KEY,
    processed_at    TEXT (ISO)
)
```

### PostgreSQL (`DATABASE_URL` set)

```sql
-- Core memory storage (JSONB + tsvector)
memories (
    id              SERIAL PRIMARY KEY,
    source          TEXT,
    raw_text        TEXT,
    summary         TEXT,
    entities        JSONB,        -- native JSON, queryable
    topics          JSONB,
    connections     JSONB,
    importance      REAL,
    created_at      TIMESTAMPTZ,  -- proper timezone support
    consolidated    BOOLEAN
)

-- GIN index for full-text search
CREATE INDEX idx_memories_fts ON memories
    USING GIN (to_tsvector('english', summary || ' ' || source));

-- Same supporting tables with PostgreSQL types
consolidations (id SERIAL, source_ids JSONB, ...)
content_hashes (hash TEXT PRIMARY KEY, ...)
processed_files (path TEXT PRIMARY KEY, ...)
```

### Backend Selection

```
┌─────────────────────────────────────────────────────┐
│              src/db/__init__.py                       │
│                                                     │
│  get_repository()                                   │
│    │                                                │
│    ├── DATABASE_URL set? ──► PostgresRepository     │
│    │                         (pg_repository.py)     │
│    │                                                │
│    └── No DATABASE_URL ──► MemoryRepository         │
│                             (repository.py)         │
│                                                     │
│  Both implement the same interface:                  │
│    store_memory, get_all_memories, search_memories,  │
│    store_consolidation, is_duplicate, etc.           │
└─────────────────────────────────────────────────────┘
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
