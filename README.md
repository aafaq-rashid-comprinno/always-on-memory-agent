# Always-On Memory Agent (AWS Bedrock)

An always-on AI memory agent that continuously processes, consolidates, and connects information using AWS Bedrock. Inspired by how the human brain consolidates memories during sleep.

**No vector database. No embeddings. No RAG pipeline.** Just an LLM that reads, thinks, and writes structured memory.

> Inspired by [GoogleCloudPlatform/always-on-memory-agent](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent), rebuilt for AWS Bedrock with production-ready features.

## How It Works

```
1. INGEST     →  Feed it anything (text, images, PDFs)
                  LLM extracts: summary, entities, topics, importance

2. CONSOLIDATE → Every 30 min, finds patterns across memories (like sleep)
                  Discovers connections you never asked about

3. QUERY      →  Ask anything. Gets a synthesized answer with citations.
                  Full-text search pre-filters relevant memories for speed.
```

## Quick Start

### Docker (recommended)

```bash
# Configure
cp .env.example .env

# Export AWS credentials
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_REGION=us-east-1

# Run
docker compose up --build
```

- **Agent API**: http://localhost:8888
- **Dashboard**: http://localhost:8501

### Local

```bash
pip install -r requirements.txt
make run          # Terminal 1: agent
make dashboard    # Terminal 2: UI
```

## Usage

### Dashboard (http://localhost:8501)

| Tab | Purpose |
|---|---|
| 💬 Query | Chat with your memory |
| 📥 Ingest | Paste text or upload files |
| 📚 Memories | Browse, inspect, delete memories |
| 💡 Insights | View consolidation patterns and connections |

### API

```bash
# Ingest
curl -X POST http://localhost:8888/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "AI agents are the future", "source": "article"}'

# Query
curl "http://localhost:8888/query?q=what+do+you+know"

# Stream (Server-Sent Events)
curl -N "http://localhost:8888/query/stream?q=summarize+everything"

# View insights
curl http://localhost:8888/consolidations

# Consolidate
curl -X POST http://localhost:8888/consolidate

# Status
curl http://localhost:8888/status
```

### File Drop

```bash
cp notes.md inbox/        # text
cp diagram.png inbox/     # images
cp report.pdf inbox/      # documents
# Auto-ingested within 5 seconds
```

## Features

| Feature | Description |
|---|---|
| **Chunking** | Large files auto-split into 3000-char segments |
| **Deduplication** | SHA256 hash prevents storing the same content twice |
| **Full-Text Search** | FTS5 (SQLite) or tsvector (PostgreSQL) pre-filtering |
| **Streaming** | Server-Sent Events for real-time query responses |
| **Multimodal** | Images and PDFs via inbox folder |
| **Auto-retry** | Exponential backoff on transient Bedrock errors |
| **Consolidation** | Periodic pattern discovery across memories |
| **Dual Database** | SQLite (default) or PostgreSQL via `DATABASE_URL` |

## Database Options

### SQLite (default - zero config)

Just works. Data stored in `data/memory.db`. Good for personal use.

### PostgreSQL (managed, persistent, scalable)

Set `DATABASE_URL` to switch:

```bash
# Amazon RDS / Aurora
DATABASE_URL=postgresql://admin:secret@mydb.xxx.us-east-1.rds.amazonaws.com:5432/memorydb

# Supabase
DATABASE_URL=postgresql://postgres:password@db.xxx.supabase.co:5432/postgres

# Neon (serverless)
DATABASE_URL=postgresql://user:pass@ep-xxx.us-east-1.aws.neon.tech/memorydb

# Railway
DATABASE_URL=postgresql://postgres:pass@containers-xxx.railway.app:5432/railway

# Local
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/memorydb
```

PostgreSQL uses native JSONB columns, tsvector full-text search, and proper timestamps. The agent auto-detects which backend to use based on whether `DATABASE_URL` is set.

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check + model info |
| `/status` | GET | Memory counts |
| `/memories` | GET | List all memories |
| `/consolidations` | GET | List all insights and patterns |
| `/query?q=...` | GET | Query with natural language |
| `/query/stream?q=...` | GET | Streaming query (SSE) |
| `/ingest` | POST | Store text `{"text": "...", "source": "..."}` |
| `/consolidate` | POST | Trigger consolidation |
| `/delete` | POST | Delete memory `{"memory_id": 1}` |
| `/clear` | POST | Full reset |

## Model Options

| Model | Multimodal | Cost | Notes |
|---|---|---|---|
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | ✅ | Low | **Default** - reliable tool use |
| `us.amazon.nova-lite-v1:0` | ✅ Images | Lowest | Occasional tool errors |
| `us.amazon.nova-micro-v1:0` | ❌ | Lowest | Text only |
| `us.anthropic.claude-sonnet-4-6-20250514-v1:0` | ✅ | Medium | Best quality |

## Configuration

All settings via `.env` or environment variables. CLI flags override env vars.

```bash
python -m src.main --model us.amazon.nova-lite-v1:0 --port 9000 --watch ./docs
```

Key variables (see [.env.example](.env.example) for full list):

| Variable | Default | Description |
|---|---|---|
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model |
| `AWS_REGION` | `us-east-1` | AWS region |
| `DATABASE_URL` | _(unset = SQLite)_ | PostgreSQL connection string |
| `MEMORY_DB` | `data/memory.db` | SQLite path (when no DATABASE_URL) |
| `PORT` | `8888` | API port |
| `WATCH_DIR` | `./inbox` | Auto-ingest folder |
| `CONSOLIDATE_INTERVAL` | `30` | Minutes between consolidation |
| `MAX_TOKENS` | `2048` | Max output tokens per LLM call |

## Architecture

```
src/
├── config/          Settings + constants (env-driven)
├── db/              SQLite + PostgreSQL backends, repository pattern
│   ├── connection.py      SQLite schema + connection
│   ├── repository.py      SQLite CRUD + FTS5
│   ├── postgres.py        PostgreSQL schema + connection
│   └── pg_repository.py   PostgreSQL CRUD + tsvector
├── tools/           Bedrock tool schemas + executor
├── agents/          Bedrock client + MemoryAgent + chunking
│   ├── client.py          Converse API + retry + streaming
│   ├── memory_agent.py    High-level interface
│   └── chunking.py        Text splitting + dedup hashing
├── api/             HTTP routes (aiohttp)
├── watcher/         File watcher + consolidation loop
└── main.py          Entry point
```

## Documentation

| Doc | Contents |
|---|---|
| [Use Cases](docs/01-use-case.md) | 6 detailed scenarios with step-by-step examples |
| [Solution](docs/02-solution.md) | Technical approach, why not RAG, data flow |
| [Architecture](docs/03-architecture.md) | Module layers, DB schema, concurrency model |
| [Research Paper](docs/05-research-paper.md) | Academic treatment with evaluation results |

## AWS Prerequisites

1. AWS credentials (access key or IAM role)
2. Bedrock model access enabled ([console](https://console.aws.amazon.com/bedrock/) → Model access)
3. Minimum IAM: `bedrock:InvokeModel` + `bedrock:InvokeModelWithResponseStream`

## Development

```bash
pip install -e ".[dev]"
make test          # Run tests
make lint          # Lint code
make format        # Auto-format
make clean         # Reset database
```

## Makefile Commands

```
make help          Show all commands
make run           Start agent locally
make dashboard     Start Streamlit UI
make docker-up     Docker Compose up
make docker-down   Stop containers
make docker-logs   Tail logs
make test          Run tests
make lint          Lint code
make clean         Reset database
make install       Install dependencies
```

## License

MIT
