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
                  FTS5 pre-filters relevant memories for speed.
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

- **Query tab** — Chat with your memory ("What patterns do you see?")
- **Ingest tab** — Paste text or upload files
- **Memories tab** — Browse, inspect, delete stored memories

### API

```bash
# Ingest
curl -X POST http://localhost:8888/ingest \
  -H "Content-Type: application/json" \
  -d '{"text": "AI agents are the future", "source": "article"}'

# Query
curl "http://localhost:8888/query?q=what+do+you+know"

# Stream (SSE)
curl -N "http://localhost:8888/query/stream?q=summarize+everything"

# Consolidate
curl -X POST http://localhost:8888/consolidate

# View insights
curl http://localhost:8888/consolidations

# Status
curl http://localhost:8888/status
```

### File Drop

```bash
cp notes.md inbox/
cp diagram.png inbox/
cp report.pdf inbox/
# Auto-ingested within 5 seconds
```

## Features

| Feature | Description |
|---|---|
| **Chunking** | Large files auto-split into 3000-char segments |
| **Deduplication** | SHA256 hash prevents storing the same content twice |
| **FTS5 Search** | Full-text pre-filtering for fast, relevant queries |
| **Streaming** | Server-Sent Events for real-time query responses |
| **Multimodal** | Images and PDFs via inbox folder (Claude/Nova Lite) |
| **Auto-retry** | Exponential backoff on transient Bedrock errors |
| **Consolidation** | Periodic pattern discovery across memories |

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check + model info |
| `/status` | GET | Memory counts |
| `/memories` | GET | List all memories |
| `/consolidations` | GET | List all insights |
| `/query?q=...` | GET | Query with natural language |
| `/query/stream?q=...` | GET | Streaming query (SSE) |
| `/ingest` | POST | Store text `{"text": "...", "source": "..."}` |
| `/consolidate` | POST | Trigger consolidation |
| `/delete` | POST | Delete memory `{"memory_id": 1}` |
| `/clear` | POST | Full reset |

## Model Options

| Model | Multimodal | Cost | Notes |
|---|---|---|---|
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | ✅ | Low | Default, reliable tool use |
| `us.amazon.nova-lite-v1:0` | ✅ Images | Lowest | Occasional tool errors |
| `us.amazon.nova-micro-v1:0` | ❌ | Lowest | Text only |
| `us.anthropic.claude-sonnet-4-6-20250514-v1:0` | ✅ | Medium | Best quality |

## Architecture

```
always-on-memory-agent/
├── src/
│   ├── config/          # Settings + constants (env-driven)
│   ├── db/              # SQLite + FTS5 + repository pattern
│   ├── tools/           # Bedrock tool schemas + executor
│   ├── agents/          # Bedrock client + MemoryAgent + chunking
│   ├── api/             # HTTP routes (aiohttp)
│   ├── watcher/         # File watcher + consolidation loop
│   └── main.py          # Entry point
├── dashboard.py         # Streamlit UI
├── docs/                # Detailed documentation
│   ├── 01-use-case.md       # 6 detailed use case scenarios
│   ├── 02-solution.md       # Technical approach + data flow
│   ├── 03-architecture.md   # System design + module layers
│   ├── 04-challenges.md     # 10 challenges with mitigations
│   └── 05-research-paper.md # Academic-style paper with evaluation
├── tests/               # Unit tests
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── pyproject.toml
```

## Documentation

| Doc | Contents |
|---|---|
| [Use Cases](docs/01-use-case.md) | 6 detailed scenarios with examples |
| [Solution](docs/02-solution.md) | Technical approach, why not RAG, data flow |
| [Architecture](docs/03-architecture.md) | Module layers, DB schema, concurrency model |
| [Challenges](docs/04-challenges.md) | 10 known limitations with mitigations |
| [Research Paper](docs/05-research-paper.md) | Academic treatment with evaluation results |

## Configuration

All settings via `.env` or environment variables. See [.env.example](.env.example).

CLI flags override env vars:
```bash
python -m src.main --model us.amazon.nova-lite-v1:0 --port 9000 --watch ./docs
```

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
make run           Start agent locally
make dashboard     Start Streamlit UI
make docker-up     Docker Compose up
make docker-down   Stop containers
make docker-logs   Tail logs
make test          Run tests
make lint          Lint code
make clean         Reset database
```

## License

MIT
