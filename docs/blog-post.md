# Building an Always-On Memory Agent with AWS Bedrock: The Engineering Deep-Dive

*How we built a persistent memory system using tool-use loops, contentless FTS5 indexes, and consolidation cycles — without a single embedding or vector database.*

---

## Why I Stopped Building RAG Pipelines

After building my fifth RAG system, I noticed the same pattern: we spend weeks tuning chunk sizes, experimenting with embedding models, configuring retrieval parameters — and the system still can't tell you that your Monday meeting contradicts your Thursday design doc.

The issue isn't retrieval quality. It's that **RAG is architecturally passive**. It embeds once, stores, and retrieves by similarity. It never:
- Processes information after ingestion
- Discovers connections between unrelated documents
- Compresses knowledge over time
- Generates insights proactively

So I built something different.

## The Core Technical Idea

Use the LLM itself as the memory engine. No embeddings. No vector store. The model reads structured records, reasons about them, and writes new structured records.

Three operations, each a **Bedrock Converse API call with tool use**:

```
INGEST:       text → LLM + store_memory tool → structured record in SQLite
CONSOLIDATE:  batch read → LLM + store_consolidation tool → insights + links
QUERY:        FTS5 pre-filter → LLM + read tools → synthesized answer
```

Let me break down each engineering decision.

## 1. Tool Use Over JSON Prompting

The most impactful architectural choice: using Bedrock's **tool use protocol** instead of prompting for JSON output.

### The Problem with JSON Prompting

```python
# What most people do (fragile)
prompt = """Extract the following as JSON:
{"summary": "...", "entities": [...], "importance": 0.0-1.0}"""

response = bedrock.converse(messages=[{"role": "user", "content": [{"text": prompt}]}])
# Now you pray it's valid JSON, not markdown-wrapped, not truncated
parsed = json.loads(response["output"]["message"]["content"][0]["text"])  # 💥
```

This fails 5-15% of the time. You end up writing regex fallbacks, JSON repair logic, retry loops for malformed output.

### Tool Use: Schema-Enforced Structured Output

```python
tools = [{
    "toolSpec": {
        "name": "store_memory",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "raw_text": {"type": "string"},
                    "summary": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "topics": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number", "description": "0.0 to 1.0"}
                },
                "required": ["raw_text", "summary", "entities", "topics", "importance"]
            }
        }
    }
}]

response = bedrock.converse(
    modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    system=[{"text": INGEST_PROMPT}],
    messages=messages,
    toolConfig={"tools": tools},
    inferenceConfig={"maxTokens": 2048}  # CRITICAL: always set explicitly
)
```

When `stopReason == "tool_use"`, the model's output is **guaranteed** to conform to the schema. The response contains:

```python
{
    "output": {"message": {"content": [
        {"toolUse": {
            "toolUseId": "call_abc123",
            "name": "store_memory",
            "input": {
                "raw_text": "...",
                "summary": "Team chose gRPC for internal services",
                "entities": ["gRPC", "REST"],
                "topics": ["architecture", "API"],
                "importance": 0.8
            }
        }}
    ]}}
}
```

No parsing. No validation. No repair. The protocol enforces it.

### The Multi-Round Loop

The agent needs multiple tool calls per operation (read → reason → write). Implementation:

```python
def invoke(self, system_prompt, user_message, tools, max_rounds=5):
    messages = [{"role": "user", "content": [{"text": user_message}]}]

    for _ in range(max_rounds):
        response = self._call_with_retry(system_prompt, messages, tools)
        output = response["output"]["message"]
        messages.append(output)

        if response["stopReason"] == "tool_use":
            # Execute tools locally, return results
            tool_results = []
            for block in output["content"]:
                if "toolUse" in block:
                    call = block["toolUse"]
                    result = self.executor.execute(call["name"], call["input"])
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": call["toolUseId"],
                            "content": [{"json": result}]
                        }
                    })
            messages.append({"role": "user", "content": tool_results})
            # Loop continues — model sees results, decides next action
        else:
            # Model finished, extract text
            return " ".join(b["text"] for b in output["content"] if "text" in b)

    return "Max rounds exceeded"
```

This enables the consolidation agent to:
1. Call `read_unconsolidated_memories` → receives list of memories
2. Reason about connections (internal, no tool call)
3. Call `store_consolidation` → writes insight + links
4. Return confirmation text

All in one invocation. The model controls the flow.

## 2. The maxTokens Trap (Bedrock-Specific)

**This is the #1 silent failure mode on Bedrock that nobody documents properly.**

If you don't set `maxTokens` in `inferenceConfig`, Bedrock defaults to the model's maximum (e.g., 4096 for Haiku). This means:
1. Every call **reserves** 4096 tokens of your per-model quota
2. With 10 concurrent requests, you've reserved 40K tokens
3. Request #11 gets `ThrottlingException` — even though actual output is 200 tokens

```python
# ❌ NEVER do this
response = bedrock.converse(modelId=MODEL, messages=messages)

# ✅ ALWAYS set explicitly
response = bedrock.converse(
    modelId=MODEL,
    messages=messages,
    inferenceConfig={"maxTokens": 2048}  # reserve only what you need
)
```

For our agent:
- Ingest: 512 tokens sufficient (summary + tool call)
- Consolidate: 1024 tokens (insight + connections)
- Query: 2048 tokens (synthesized answer)

We use 2048 as a safe default. Could optimize per-agent-type for higher throughput.

## 3. Contentless FTS5: The Scaling Trick

At 50 memories, the query agent can read everything. At 500, context overflow. We need pre-filtering.

**Design choice**: SQLite FTS5 in **contentless** mode.

### Why Contentless?

```sql
-- Content-backed FTS (stores text twice — wasteful)
CREATE VIRTUAL TABLE fts USING fts5(summary, content='memories');

-- Contentless FTS (stores only the index — half the disk)
CREATE VIRTUAL TABLE memories_fts USING fts5(summary, entities, topics, content='');
```

Contentless means the FTS table doesn't store a copy of the text — it only stores the inverted index for search. We JOIN back to the `memories` table for actual content:

```python
def search_memories(self, query, limit=20):
    terms = [t for t in query.split() if len(t) > 2]
    fts_query = " OR ".join(terms)
    
    rows = db.execute("""
        SELECT m.* FROM memories m
        JOIN memories_fts fts ON m.id = fts.rowid
        WHERE memories_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (fts_query, limit)).fetchall()
    
    return rows
```

### The Contentless Gotcha

You **cannot** `DELETE FROM` or `UPDATE` a contentless FTS5 table. This caused a production bug:

```python
# ❌ Crashes: "cannot DELETE from contentless fts5 table"
db.execute("DELETE FROM memories_fts WHERE rowid = ?", (memory_id,))

# ❌ Also crashes on clear
db.execute("DELETE FROM memories_fts")
```

**Solutions:**
- For single deletes: let stale entries remain. The JOIN filters them out since the parent row is gone.
- For full clear: `DROP TABLE` and recreate.

```python
def clear_all(self):
    db.execute("DELETE FROM memories")
    db.execute("DROP TABLE IF EXISTS memories_fts")
    db.execute("CREATE VIRTUAL TABLE memories_fts USING fts5(summary, entities, topics, content='')")
    db.commit()
```

### Performance

| Memories | Without FTS (read all) | With FTS5 |
|---|---|---|
| 50 | 2.8s (fine) | 2.1s |
| 200 | 11.5s (slow) | 2.9s |
| 1000 | Context overflow | 3.2s |

FTS5 keeps query latency flat regardless of total memory count.

## 4. Chunking: Why 3000 Characters?

Large inputs (10K+ chars) cause a specific failure: the model spends all its output tokens *describing* the content and never reaches the tool call. It literally runs out of generation budget before `store_memory` is invoked.

```
Input: 10,000 char document
Model output: "This document discusses..." (uses 2048 tokens describing)
Result: stopReason = "max_tokens" (not "tool_use")
Memory stored: NOTHING
```

### The Fix: Paragraph-Aware Chunking

```python
def chunk_text(text, max_chars=3000, overlap=200):
    if len(text) <= max_chars:
        return [text]

    chunks = []
    paragraphs = text.split("\n\n")
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars:
            chunks.append(current.strip())
            # Overlap: last 200 chars of previous chunk start the next
            current = chunks[-1][-overlap:] + "\n\n" + para
        else:
            current += "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())
    return chunks
```

**Why 3000?** 
- 3000 chars ≈ 750-1000 tokens input
- Leaves 1000+ tokens for the model to reason and emit the tool call
- Paragraph boundaries preserve semantic coherence
- 200-char overlap prevents information loss at boundaries

**Why not sentence-level like LangChain?** Paragraphs are the natural semantic unit for the type of content this agent handles (notes, articles, reports). Sentence splitting over-fragments.

## 5. Deduplication via Content Hashing

Users drop the same file twice. The file watcher re-scans. Repeated API calls. Without dedup, you get duplicate memories that pollute consolidation and waste query tokens.

```python
def compute_text_hash(text):
    normalized = " ".join(text.lower().split())  # collapse whitespace, lowercase
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]
```

**Normalization matters**: The same content with different whitespace or capitalization should be detected as duplicate. We normalize before hashing.

```python
def ingest(self, text, source=""):
    text_hash = compute_text_hash(text)
    if self._repo.is_duplicate(text_hash):
        return "Skipped: duplicate content."
    
    # ... proceed with ingestion
    self._repo.record_hash(text_hash)
```

Stored in a dedicated table:
```sql
CREATE TABLE content_hashes (
    hash TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
```

O(1) lookup. No false positives with SHA256. Survives restarts.

## 6. Retry Logic: Handling ModelErrorException

Bedrock (especially Nova models) occasionally returns `ModelErrorException` with "Model produced invalid sequence as part of ToolUse." This means the model generated malformed JSON that didn't match the tool schema — Bedrock caught it and returned an error instead of garbage.

```python
RETRYABLE_ERRORS = ("ModelErrorException", "ThrottlingException", "ModelTimeoutException")
MAX_RETRIES = 3

def _call_with_retry(self, system_prompt, messages, tools):
    for attempt in range(MAX_RETRIES):
        try:
            return self._client.converse(**kwargs)
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code in RETRYABLE_ERRORS:
                wait = 2 * (2 ** attempt)  # 2s, 4s, 8s
                log.warning(f"⚠️ {error_code} (attempt {attempt+1}), retry in {wait}s")
                time.sleep(wait)
            else:
                return None  # Non-retryable
    return None
```

**Model choice matters here**: Claude Haiku 4.5 has <1% tool use failures. Nova Lite has ~5%. If you're using Nova, retries are essential. If you're using Claude, they're insurance.

## 7. Streaming via ConverseStream

For the query endpoint, 5-10 second latency feels broken. Streaming tokens as they generate makes it feel instant.

```python
def invoke_stream(self, system_prompt, user_message, tools):
    messages = [{"role": "user", "content": [{"text": user_message}]}]

    for _ in range(self._max_rounds):
        response = self._client.converse_stream(**kwargs)
        
        tool_use_blocks = []
        current_tool = None
        
        for event in response["stream"]:
            if "contentBlockDelta" in event:
                delta = event["contentBlockDelta"]["delta"]
                if "text" in delta:
                    yield delta["text"]  # Stream to client immediately
                elif "toolUse" in delta:
                    # Accumulate tool input (not streamable)
                    tool_input_buffer += delta["toolUse"].get("input", "")
            
            elif "contentBlockStop" in event:
                if current_tool:
                    current_tool["input"] = json.loads(tool_input_buffer)
                    tool_use_blocks.append(current_tool)
        
        if tool_use_blocks:
            # Execute tools, continue loop (next round will stream text)
            results = [execute(t) for t in tool_use_blocks]
            messages.append(...)  # tool results
        else:
            return  # Done streaming
```

Server-side, we expose as SSE:

```python
async def handle_query_stream(request):
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await response.prepare(request)
    
    for chunk in agent.query_stream(question):
        await response.write(f"data: {chunk}\n\n".encode())
    
    await response.write(b"data: [DONE]\n\n")
    return response
```

Client consumption:
```javascript
const events = new EventSource("/query/stream?q=what+do+you+know");
events.onmessage = (e) => {
    if (e.data === "[DONE]") events.close();
    else document.getElementById("answer").textContent += e.data;
};
```

## 8. Database Abstraction: SQLite → PostgreSQL

The repository interface is identical for both backends:

```python
class MemoryRepository:      # SQLite + FTS5
class PostgresRepository:    # PostgreSQL + tsvector

# Both implement:
def store_memory(raw_text, summary, entities, topics, importance, source) -> dict
def get_all_memories(limit) -> dict
def search_memories(query, limit) -> dict
def store_consolidation(source_ids, summary, insight, connections) -> dict
def is_duplicate(text_hash) -> bool
# ... etc
```

Factory selects at startup:
```python
def get_repository():
    settings = get_settings()
    if settings.database_url.startswith("postgresql"):
        return PostgresRepository()
    return MemoryRepository()
```

PostgreSQL differences:
- `JSONB` columns (queryable) vs `TEXT` storing JSON strings
- `tsvector` + GIN index vs FTS5 virtual table
- `TIMESTAMPTZ` vs ISO text strings
- `ON CONFLICT DO NOTHING` vs `INSERT OR IGNORE`
- Connection pooling concern (we open/close per operation — fine for single-user, add pgbouncer for scale)

## 9. The Consolidation Algorithm

This is the differentiator. Everything else is engineering. This is the *intelligence*.

```python
CONSOLIDATE_PROMPT = """You are a Memory Consolidation Agent.
1. Call read_unconsolidated_memories
2. If fewer than 2 memories, say 'Nothing to consolidate.'
3. Find connections and patterns across the memories
4. Create a synthesized summary and one key insight
5. Call store_consolidation with source_ids, summary, insight, connections

Connections: list of {from_id, to_id, relationship} dicts.
Think deeply about cross-cutting patterns."""
```

What makes this work:
- The model sees ALL unconsolidated memories simultaneously (up to 10)
- Its attention mechanism naturally identifies shared entities and themes
- The tool schema forces structured output (connections + insight)
- The "think deeply" instruction triggers chain-of-thought reasoning

What the model actually does internally:
1. Identifies shared entities across memories
2. Infers causal/temporal/thematic relationships
3. Synthesizes a meta-pattern that no individual memory contains
4. Formalizes connections as typed relationships

This is essentially **automatic knowledge graph construction** — but without the graph database, without NER pipelines, without relationship extraction models. One LLM call.

## 10. Cost Engineering

The system runs 24/7. Every cent matters.

### Token Budget Per Operation

| Operation | System prompt | User content | Tool schemas | Output | Total |
|---|---|---|---|---|---|
| Ingest | 150 tokens | 750 tokens (chunk) | 200 tokens | 400 tokens | ~1500 |
| Consolidate | 120 tokens | 2000 tokens (10 memories) | 300 tokens | 600 tokens | ~3000 |
| Query | 130 tokens | 1500 tokens (FTS results) | 200 tokens | 500 tokens | ~2300 |

### Monthly Cost (Claude Haiku 4.5)

```
Input:  $0.80 / 1M tokens
Output: $4.00 / 1M tokens

Ingest:      50/day × 30 × (1100 × $0.80 + 400 × $4.00) / 1M = $0.60
Consolidate: 48/day × 30 × (2400 × $0.80 + 600 × $4.00) / 1M = $1.20
Query:       30/day × 30 × (1800 × $0.80 + 500 × $4.00) / 1M = $1.50
─────────────────────────────────────────────────────────────────────────
Total: ~$3.30/month
```

### Comparison

| System | Monthly cost | What you get |
|---|---|---|
| This agent | $3.30 | Ingest + consolidate + query |
| Pinecone Starter | $70 | Vector storage only (no processing) |
| OpenSearch Serverless | $175 | Search infra only |
| Weaviate Cloud | $25 | Vector storage only |
| Full RAG stack (typical) | $200-500 | Embed + store + retrieve + generate |

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                    asyncio Event Loop                             │
│                                                                 │
│  ┌──────────────┐  ┌─────────────────┐  ┌───────────────────┐  │
│  │ File Watcher │  │ Consolidation   │  │ aiohttp Server    │  │
│  │ (poll 5s)    │  │ Loop (30 min)   │  │ (HTTP + SSE)      │  │
│  └──────┬───────┘  └────────┬────────┘  └────────┬──────────┘  │
│         │                   │                     │             │
│         └───────────────────┼─────────────────────┘             │
│                             ▼                                   │
│                    ┌─────────────────┐                          │
│                    │  MemoryAgent    │                          │
│                    │  (facade)       │                          │
│                    └────────┬────────┘                          │
│                             │                                   │
│              ┌──────────────┼──────────────┐                    │
│              ▼              ▼              ▼                    │
│     ┌──────────────┐ ┌──────────┐ ┌──────────────┐            │
│     │ BedrockClient│ │ Chunking │ │ToolExecutor  │            │
│     │ (retry+stream)│ │ (3000ch) │ │ (6 tools)    │            │
│     └──────┬───────┘ └──────────┘ └──────┬───────┘            │
│            │                              │                    │
│            ▼                              ▼                    │
│   ┌─────────────────┐           ┌─────────────────┐           │
│   │ AWS Bedrock     │           │ Repository      │           │
│   │ Converse API    │           │ (SQLite/Postgres)│           │
│   └─────────────────┘           └─────────────────┘           │
└─────────────────────────────────────────────────────────────────┘
```

## What I'd Do Differently

1. **Use `content=memories` FTS5** instead of contentless — enables DELETE operations, slightly more disk but avoids the DROP/recreate hack on clear.

2. **Add `asyncio.to_thread()`** around boto3 calls — currently blocks the event loop. Fine for single-user but blocks concurrent HTTP requests.

3. **Per-agent-type maxTokens** — ingest needs 512, query needs 2048. Setting 2048 globally wastes quota reservation on ingest calls.

4. **Importance decay** — memories not accessed should lose importance over time. Currently all memories are equal after ingestion.

5. **Structured consolidation triggers** — instead of pure timer-based, trigger when N memories share entities/topics (smarter batching).

## Try It

```bash
git clone https://github.com/aafaq-rashid-comprinno/always-on-memory-agent
cd always-on-memory-agent
cp .env.example .env
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-1
docker compose up --build
```

The entire system is ~1200 lines of Python across 12 modules. No framework. No LangChain. No abstractions hiding the mechanics. Every Bedrock call, every tool schema, every database query is explicit and auditable.

Read the source: it's the best documentation.

---

*Source: [github.com/aafaq-rashid-comprinno/always-on-memory-agent](https://github.com/aafaq-rashid-comprinno/always-on-memory-agent)*
