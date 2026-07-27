# Always-On Memory Agent (AWS Bedrock)

An always-on AI memory agent that continuously processes, consolidates, and connects information using AWS Bedrock. No vector database, no embeddings - just an LLM that reads, thinks, and writes structured memory.

Inspired by [GoogleCloudPlatform/always-on-memory-agent](https://github.com/GoogleCloudPlatform/generative-ai/tree/main/gemini/agents/always-on-memory-agent), ported to AWS Bedrock.

## Architecture

```
src/
├── config/          Settings, constants, environment management
├── db/              SQLite schema, connection, repository (CRUD)
├── tools/           Tool definitions (Bedrock format) + executor
├── agents/          Bedrock Converse client + MemoryAgent interface
├── api/             HTTP routes and handlers (aiohttp)
├── watcher/         File watcher + consolidation loop
└── main.py          Entry point - wires everything together
```

```
                    ┌─────────────────────────────────────┐
  ./inbox/ ────────►│         FILE WATCHER                │
                    └────────────────┬────────────────────┘
                                     │
  HTTP :8888 ──────►┌────────────────▼────────────────────┐
                    │          MEMORY AGENT                │
                    │                                      │
                    │  ingest() ──► Bedrock ──► store_memory
                    │  query()  ──► Bedrock ──► read + synthesize
                    │  consolidate() ──► Bedrock ──► find patterns
                    └────────────────┬────────────────────┘
                                     │
                    ┌────────────────▼────────────────────┐
                    │       SQLite (data/memory.db)        │
                    └─────────────────────────────────────┘
```

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env    # configure model + region
docker compose up --build
```

- Agent API: http://localhost:8888
- Dashboard: http://localhost:8501

### Local

```bash
pip install -r requirements.txt
cp .env.example .env

# Run the agent
make run

# In another terminal
make dashboard
```

### Makefile Commands

```bash
make help          # Show all commands
make run           # Start agent
make dashboard     # Start Streamlit UI
make docker-up     # Docker Compose up
make docker-down   # Stop containers
make test          # Run tests
make lint          # Lint code
make clean         # Reset database
```

## Configuration

All settings live in `.env` (or environment variables). See `.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `BEDROCK_MODEL_ID` | `us.amazon.nova-lite-v1:0` | Bedrock model |
| `AWS_REGION` | `us-east-1` | AWS region |
| `PORT` | `8888` | API port |
| `WATCH_DIR` | `./inbox` | Auto-ingest folder |
| `CONSOLIDATE_INTERVAL` | `30` | Minutes between consolidation |
| `MAX_TOKENS` | `1024` | Max output tokens |
| `MEMORY_DB` | `data/memory.db` | Database path |

CLI flags override environment variables:

```bash
python -m src.main --model us.anthropic.claude-haiku-4-0 --port 9000 --watch ./docs
```

## Model Options

| Model | Multimodal | Cost | Use Case |
|---|---|---|---|
| `us.amazon.nova-lite-v1:0` | ✅ Images | Lowest | Default, 24/7 operation |
| `us.amazon.nova-micro-v1:0` | ❌ Text only | Lowest | Pure text workloads |
| `us.anthropic.claude-haiku-4-0` | ✅ Full | Low | Better reasoning |
| `us.anthropic.claude-sonnet-4-6` | ✅ Full | Medium | Best quality |

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check + model info |
| `/status` | GET | Memory counts |
| `/memories` | GET | List all memories |
| `/query?q=...` | GET | Query with natural language |
| `/ingest` | POST | Store text `{"text": "...", "source": "..."}` |
| `/consolidate` | POST | Trigger consolidation |
| `/delete` | POST | Delete memory `{"memory_id": 1}` |
| `/clear` | POST | Full reset |

## How It Works

1. **Ingest** - Feed text/images/PDFs. The LLM extracts summary, entities, topics, importance.
2. **Consolidate** - Every 30 min, the LLM finds patterns across memories (like brain during sleep).
3. **Query** - Ask anything. The LLM reads all memories and synthesizes an answer with citations.

## AWS Prerequisites

1. AWS credentials configured (`~/.aws/credentials` or IAM role)
2. Bedrock model access enabled in your region ([console](https://console.aws.amazon.com/bedrock/))
3. Minimum IAM permission: `bedrock:InvokeModel` on `arn:aws:bedrock:*::foundation-model/*`

## Development

```bash
pip install -e ".[dev]"
make test
make lint
```

## License

MIT
