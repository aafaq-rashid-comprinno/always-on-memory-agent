# Challenges

## 1. Context Window Limits

### Problem

The Query Agent reads **all memories** into context before answering. As memories grow beyond the model's context window (128K tokens for Nova Lite, 200K for Claude), this breaks.

### Current Impact

- ~50 memories × 200 tokens each = 10K tokens (safe)
- ~500 memories = 100K tokens (approaching limits)
- ~1000+ memories = context overflow

### Mitigation Strategies

| Strategy | Complexity | Tradeoff |
|---|---|---|
| Limit to most recent N memories | Low | Loses old context |
| Pre-filter by topic/entity match | Medium | Needs keyword extraction from query |
| Hierarchical summarization | Medium | Consolidation creates compressed layers |
| Hybrid: SQLite FTS + LLM | Medium | Add full-text search, feed top results to LLM |
| Move to vector store at scale | High | Adds infrastructure, loses simplicity |

### Recommended Path

Short-term: Aggressive consolidation (compress 10 memories → 1 insight). Long-term: Add SQLite FTS5 for pre-filtering before LLM reads.

---

## 2. Consolidation Quality

### Problem

The consolidation agent sometimes produces:
- **Shallow connections** ("these are both about technology")
- **Hallucinated relationships** (linking unrelated memories)
- **Over-consolidation** (merging things that should stay separate)

### Root Cause

The cheaper models (Nova Lite, Nova Micro) have weaker reasoning than Claude Sonnet. Consolidation is the most intellectually demanding task - it requires abstract pattern recognition across disparate inputs.

### Mitigation Strategies

- Use a **stronger model** for consolidation only (Claude Haiku) while keeping Nova Lite for ingest/query
- Add **structured constraints** to the consolidation prompt (require specific evidence for connections)
- Require **minimum overlap** (shared entities or topics) before allowing a connection
- Add a **confidence score** to consolidations, surface only high-confidence insights

---

## 3. Cost at Scale

### Problem

Every operation requires a Bedrock API call. At continuous 24/7 operation:

| Operation | Frequency | Tokens/call | Monthly cost (Nova Lite) |
|---|---|---|---|
| Ingest | 50/day | ~500 in + ~300 out | ~$0.50 |
| Consolidate | 48/day | ~2000 in + ~500 out | ~$1.00 |
| Query | 20/day | ~5000 in + ~500 out | ~$1.50 |
| **Total** | | | **~$3/month** |

Nova Lite is cheap enough. But switching to Claude Sonnet multiplies costs by 10-50x.

### Mitigation Strategies

- Keep **Nova Lite as default** for routine operations
- Use **conditional model routing** (simple ingest → Micro, complex query → Haiku)
- **Batch consolidation** (process more memories per cycle, fewer cycles)
- **Cache query results** for repeated questions
- Set **token budgets** per operation with MAX_TOKENS

---

## 4. Synchronous Bedrock Calls

### Problem

boto3's Bedrock client is synchronous. In the current architecture:
- HTTP requests block until Bedrock responds (2-10 seconds)
- File watcher blocks during ingestion
- Only one Bedrock call happens at a time

### Impact

- Dashboard feels slow (query takes 5-10 seconds)
- File watcher can fall behind if many files arrive simultaneously
- Cannot parallelize ingest + query

### Mitigation Strategies

| Strategy | Complexity | Impact |
|---|---|---|
| `asyncio.to_thread()` for boto3 calls | Low | Unblocks event loop |
| Bedrock streaming (ConverseStream) | Medium | Faster perceived latency for queries |
| Background task queue (asyncio.Queue) | Medium | Decouple ingestion from file watcher |
| Multiple workers (process pool) | High | True parallelism |

### Recommended Path

Wrap boto3 calls in `asyncio.to_thread()` - minimal code change, significant UX improvement.

---

## 5. No Semantic Search

### Problem

The query agent reads **all** memories linearly. It cannot efficiently find the 3 relevant memories out of 500. Unlike RAG systems with vector similarity, there is no relevance ranking before the LLM reads.

### Why This Matters

- Wastes tokens (LLM reads irrelevant memories)
- Reduces answer quality (relevant signal lost in noise)
- Hits context limits faster

### Mitigation Strategies

- **SQLite FTS5** - Full-text search on summary/entities/topics fields. Query → extract keywords → FTS → top 20 → LLM reads
- **Topic-based filtering** - Extract topics from query, filter memories by matching topics
- **Importance-based prioritization** - Always include high-importance memories, filter low-importance
- **Recency bias** - Weight recent memories higher unless query is explicitly historical
- **Hybrid RAG** - Add pgvector or Bedrock Knowledge Base for similarity search (defeats the "no vector DB" simplicity)

### Recommended Path

SQLite FTS5 is the sweet spot - zero infrastructure, built into SQLite, good enough for 1000s of memories.

---

## 6. Single-User Design

### Problem

The current architecture assumes one user:
- Single SQLite database
- No authentication on API
- No user isolation
- Single memory namespace

### For Multi-User

| Concern | Solution |
|---|---|
| Data isolation | Separate DB per user, or user_id column |
| Authentication | API key or JWT middleware |
| Rate limiting | Per-user token budgets |
| Storage | Move from SQLite to PostgreSQL |
| Deployment | One container per user, or shared with tenant isolation |

### Recommended Path

For a demo/personal tool: current design is fine. For a product: add `user_id` to all tables, add API key auth, move to Postgres.

---

## 7. Memory Accuracy

### Problem

The LLM can:
- **Misinterpret** content during ingestion (wrong entities, incorrect summary)
- **Hallucinate** during queries (claim memories say things they don't)
- **Lose nuance** in summarization (important qualifiers dropped)

### Mitigation Strategies

- Store **raw_text alongside summary** (allows re-processing)
- Add **user feedback loop** (mark memories as accurate/inaccurate)
- Use **citations** in queries (user can verify against source)
- Keep **source attribution** (filename, timestamp) for traceability
- Run **periodic accuracy audits** (sample memories, compare to raw)

---

## 8. File Watcher Reliability

### Problem

The polling-based file watcher:
- Misses files if processing is slow and files are deleted externally
- No retry for failed ingestions
- No progress indicator for large files
- Race condition if file is still being written when polled

### Mitigation Strategies

- Use `watchdog` library for OS-level file events (instead of polling)
- Add a **retry queue** for failed ingestions
- Check file size stability before processing (wait for write completion)
- Log processed files to DB (already implemented via `processed_files` table)
- Add a **/inbox/failed/** folder for files that cannot be processed

---

## 9. Testing Bedrock Interactions

### Problem

Unit testing the agent requires mocking Bedrock API responses, which are complex (multi-round tool use, varying response formats).

### Mitigation Strategies

- **Repository layer is fully testable** without mocking (pure SQLite)
- **Tool executor is testable** without Bedrock (just function calls)
- **Integration tests** use a real Bedrock endpoint (expensive, slow)
- **Mock the boto3 client** with recorded responses for agent-level tests
- Use `moto` library for AWS service mocking (limited Bedrock support)

---

## 10. Observability

### Problem

When the agent is running 24/7 unattended:
- How do you know it is working?
- How do you detect quality degradation?
- How do you debug a bad consolidation?

### Current State

- Logging to stdout (basic)
- `/status` endpoint (memory counts)
- `/health` endpoint (liveness)

### Needed For Production

- Structured logging (JSON) with correlation IDs
- Metrics: ingest count, consolidation count, query latency, error rate
- Alerts: consolidation failures, high error rate, Bedrock throttling
- Audit trail: every LLM call logged with input/output
- Cost tracking: tokens used per operation per day

### Recommended Stack

CloudWatch Logs + Metrics for AWS-native observability, or OpenTelemetry for vendor-neutral tracing.
