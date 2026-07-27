# Solution

## Approach

Build a **lightweight, always-on agent** that mimics how the human brain processes memory:

1. **Encoding** (Ingest) - Convert raw input into structured, retrievable form
2. **Consolidation** (Sleep cycles) - Periodically replay, connect, and compress
3. **Retrieval** (Query) - Reconstruct answers from stored traces + insights

The key insight: use the LLM itself as both the processing engine and the retrieval engine. No separate embedding model, no vector database, no retrieval pipeline. The LLM reads raw memories and synthesizes answers directly.

## Why Not RAG?

| Traditional RAG | This Agent |
|---|---|
| Embed once, retrieve by similarity | Process actively, consolidate periodically |
| Passive storage | Active pattern discovery |
| Returns chunks | Synthesizes answers |
| Needs embedding model + vector DB | Just an LLM + SQLite |
| No cross-reference | Finds connections automatically |
| Degrades with scale | Consolidation compresses over time |

## Solution Components

### 1. Ingest Agent

**Input:** Any text, image, or document
**Output:** Structured memory record

```
Raw Input → LLM (extract) → {
    summary: "...",
    entities: [...],
    topics: [...],
    importance: 0.0-1.0,
    source: "..."
}
```

The LLM does the heavy lifting - no NER models, no topic classifiers, no importance heuristics. A single model call handles all extraction.

### 2. Consolidation Agent

**Input:** Unconsolidated memories (batch)
**Output:** Connections + insights

Runs on a timer (default: 30 min). Mimics sleep consolidation:
- Reviews recent memories
- Identifies cross-cutting patterns
- Generates meta-insights
- Links related memories

This is the differentiator. No other memory system actively discovers patterns without being asked.

### 3. Query Agent

**Input:** Natural language question
**Output:** Synthesized answer with citations

Reads all memories + consolidation history, then generates a grounded response. References specific memory IDs so the user can trace claims to sources.

### 4. Infrastructure Layer

- **File Watcher** - Monitors inbox folder, auto-ingests new files
- **HTTP API** - REST endpoints for programmatic access
- **SQLite** - Persistent storage, zero-config, portable
- **Docker** - Reproducible deployment, easy scaling

## Technology Choices

| Component | Choice | Rationale |
|---|---|---|
| LLM | AWS Bedrock (Nova Lite) | Cheapest multimodal, managed, no infra |
| API style | Bedrock Converse + tool use | Unified across models, structured output |
| Storage | SQLite | Zero-config, single-file, portable |
| HTTP | aiohttp | Async, lightweight, production-ready |
| Background tasks | asyncio | Native Python, no Celery/Redis needed |
| Dashboard | Streamlit | Fast to build, good enough for demo |
| Packaging | Docker Compose | Agent + Dashboard as isolated services |
| Config | python-dotenv + dataclass | Type-safe, env-var driven, 12-factor |

## Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│                        INPUT CHANNELS                         │
├────────────────┬───────────────────┬─────────────────────────┤
│  File Watcher  │    HTTP API       │    Dashboard Upload      │
│  (./inbox/)    │    (POST /ingest) │    (Streamlit)           │
└───────┬────────┴────────┬──────────┴──────────┬──────────────┘
        │                 │                     │
        └─────────────────┼─────────────────────┘
                          ▼
              ┌───────────────────────┐
              │     INGEST AGENT      │
              │  (Bedrock Converse)   │
              │                       │
              │  Extract:             │
              │  • Summary            │
              │  • Entities           │
              │  • Topics             │
              │  • Importance         │
              └───────────┬───────────┘
                          │ store_memory()
                          ▼
              ┌───────────────────────┐
              │     SQLite DB         │
              │                       │
              │  memories             │
              │  consolidations       │
              │  processed_files      │
              └───────────┬───────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
┌─────────────────────┐  ┌─────────────────────┐
│  CONSOLIDATION LOOP │  │    QUERY AGENT      │
│  (every 30 min)     │  │  (on demand)        │
│                      │  │                     │
│  • Read pending      │  │  • Read all memories│
│  • Find patterns     │  │  • Read insights    │
│  • Generate insight  │  │  • Synthesize answer│
│  • Link memories     │  │  • Cite sources     │
└──────────────────────┘  └─────────────────────┘
```

## Deployment Model

```
┌─────────────────────────────────────────────┐
│            Docker Compose                    │
│                                             │
│  ┌─────────────────────┐  ┌─────────────┐  │
│  │  Agent Container    │  │  Dashboard  │  │
│  │  • File watcher     │  │  Container  │  │
│  │  • Consolidation    │  │  • Streamlit│  │
│  │  • HTTP API (:8888) │  │  • UI (:8501│  │
│  │  • SQLite           │  │             │  │
│  └─────────┬───────────┘  └──────┬──────┘  │
│            │                      │         │
│            └──────────────────────┘         │
│                   HTTP                      │
└─────────────────────────────────────────────┘
        │
        ▼ (Bedrock API calls)
┌─────────────────────────────────────────────┐
│           AWS Bedrock                        │
│           (Nova Lite / Claude Haiku)         │
└─────────────────────────────────────────────┘
```
