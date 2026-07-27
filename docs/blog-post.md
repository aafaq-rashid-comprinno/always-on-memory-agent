# Building an Always-On Memory Agent with AWS Bedrock: Beyond RAG

*A practical guide to giving AI agents persistent, evolving memory without vector databases*

---

## The Problem Every AI Engineer Hits

You've built the RAG pipeline. You've tuned the chunk sizes, experimented with embedding models, deployed the vector database. And yet — your AI assistant still feels *stateless*. It retrieves documents, but it doesn't *understand* them. It finds similar text, but it doesn't discover that your Monday meeting contradicts your Wednesday design doc.

The gap isn't retrieval. It's **active memory processing**.

Human brains don't just store and retrieve. During sleep, the hippocampus replays the day's experiences, finds connections, compresses details into insights, and integrates new knowledge with existing mental models. No AI memory system does this today.

Until now.

## What We Built

An **always-on memory agent** that runs 24/7 as a background process, continuously:

1. **Ingesting** information (text, images, PDFs) into structured memory
2. **Consolidating** memories on a timer — finding patterns you never asked about
3. **Answering** queries with synthesized, cited responses

The entire system is:
- **One LLM** (AWS Bedrock Claude Haiku 4.5)
- **One database** (SQLite or PostgreSQL)
- **One Docker container**
- **~$3/month** in LLM costs

No vector database. No embedding model. No retrieval pipeline. No LangChain.

## Why Not RAG?

RAG is the default architecture for LLM memory. But it has fundamental limitations that become obvious at scale:

| What RAG Does | What's Missing |
|---|---|
| Embeds text into vectors | No understanding of *what* was embedded |
| Retrieves by cosine similarity | Can't find connections between unrelated chunks |
| Returns top-K chunks | Doesn't synthesize across multiple sources |
| Processes on query | Never proactively discovers patterns |
| Static after ingestion | No re-processing, no compression, no insight |

**The core issue**: RAG treats memory as a *search problem*. But memory isn't search. Memory is an active cognitive process that transforms raw experience into structured knowledge.

Consider this example:

```
Document 1 (Monday):    "Team decided to use gRPC for internal services"
Document 2 (Wednesday): "Benchmark shows gRPC is 3x faster than REST"  
Document 3 (Friday):    "Sprint retro: API latency is our top pain point"
```

A RAG system stores three embeddings. If you search "gRPC", you get documents 1 and 2. If you search "latency", you get document 3. But nobody discovers that **all three are one story**: the latency problem (doc 3) was already solved by the gRPC decision (doc 1), validated by benchmarks (doc 2).

Our memory agent's consolidation cycle finds this automatically:

```
Insight: "The gRPC migration decision directly addresses the sprint's
top pain point. Benchmark data confirms 3x improvement expected."
Connection: Doc 1 ↔ Doc 2 ↔ Doc 3 (decision → evidence → problem)
```

## Architecture: LLM-as-Memory-Engine

The key insight is using the **LLM itself** as both the encoding engine and the retrieval engine. No separate models, no separate infrastructure.

```
┌───────────────────────────────────────────────────────────┐
│                    INGEST AGENT                             │
│                                                           │
│  "Remember: team decided on gRPC for internal services"   │
│       │                                                   │
│       ▼ (Bedrock Converse API + tool use)                 │
│                                                           │
│  Tool call: store_memory({                                │
│    summary: "Team chose gRPC over REST for internals",    │
│    entities: ["gRPC", "REST", "internal services"],       │
│    topics: ["architecture", "API design"],                │
│    importance: 0.8                                        │
│  })                                                       │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│              CONSOLIDATION AGENT (every 30 min)            │
│                                                           │
│  Tool call: read_unconsolidated_memories()                │
│       │                                                   │
│       ▼ (LLM reads all pending memories)                  │
│                                                           │
│  Tool call: store_consolidation({                         │
│    source_ids: [1, 2, 3],                                 │
│    insight: "gRPC decision solves the latency problem",   │
│    connections: [{from: 1, to: 3, rel: "solves"}]         │
│  })                                                       │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│                    QUERY AGENT                              │
│                                                           │
│  "What should we focus on?"                               │
│       │                                                   │
│       ▼ (FTS5 pre-filter → top 20 relevant memories)      │
│       ▼ (LLM synthesizes answer)                          │
│                                                           │
│  "Based on your memories:                                 │
│   1. gRPC migration addresses latency [Memory 1,3]        │
│   2. Benchmarks confirm 3x improvement [Memory 2]         │
│   3. This is your sprint's top priority [Memory 3]"       │
└───────────────────────────────────────────────────────────┘
```

## The Bedrock Converse API: Why Tool Use Matters

A critical implementation detail: we use Bedrock's **tool use** (function calling) instead of asking the LLM to output JSON directly.

**Why this matters:**

```python
# ❌ Fragile: asking for JSON output
prompt = "Extract entities as JSON: {entities: [...]}"
# Result: Sometimes valid JSON, sometimes markdown, sometimes explanation

# ✅ Robust: tool use with schema enforcement
tools = [{
    "toolSpec": {
        "name": "store_memory",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "entities": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "number"}
                },
                "required": ["summary", "entities", "importance"]
            }
        }
    }
}]

response = bedrock.converse(
    modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
    messages=messages,
    toolConfig={"tools": tools},
    inferenceConfig={"maxTokens": 2048}  # ALWAYS set explicitly
)
```

The model **must** conform to the JSON schema or the call fails. No regex parsing. No "please output valid JSON" prompt gymnastics. The Converse API enforces structure at the protocol level.

### The Tool-Use Loop

The agent implements a multi-round tool-use loop:

```python
for round in range(max_rounds):
    response = bedrock.converse(**kwargs)
    
    if response["stopReason"] == "tool_use":
        # Model wants to call a tool
        results = execute_tools(response)
        messages.append(assistant_message)
        messages.append(tool_results)
        # Continue loop — model sees results, may call more tools
    else:
        # Model finished — return text
        return extract_text(response)
```

This allows the agent to:
1. Call `read_unconsolidated_memories` → get data
2. Analyze the data (internal reasoning)
3. Call `store_consolidation` → save results
4. Return a human-readable confirmation

All in a single invocation with guaranteed structured I/O.

## Consolidation: The Secret Sauce

The consolidation algorithm is deceptively simple:

```
Every 30 minutes:
  1. Read memories where consolidated = false
  2. If < 2 memories: skip
  3. Send to LLM: "Find connections and patterns"
  4. LLM returns: insight + connections
  5. Store the consolidation, mark memories as processed
```

But the *results* are powerful because the LLM's attention mechanism naturally identifies:
- **Shared entities** across memories (same people, products, concepts)
- **Causal chains** (this decision led to that outcome)
- **Contradictions** (Monday said X, Wednesday said not-X)
- **Complementary evidence** (paper A + paper B together support theory C)

No graph algorithms. No clustering. No explicit relationship extraction pipeline. The model's 200K-token context window **is** the working memory where pattern recognition happens.

## Scaling Without Vectors: FTS5 Pre-Filtering

The obvious objection: "Reading all memories for every query doesn't scale."

Correct. That's why we add **full-text search pre-filtering**:

```python
def search_memories(self, query: str, limit: int = 20):
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

SQLite's FTS5 is **built-in** (no extra infrastructure) and handles thousands of memories efficiently. The query flow becomes:

```
User question
    │
    ▼ (extract keywords)
FTS5 search → top 20 relevant memories
    │
    ▼ (only these go to the LLM)
Bedrock Converse → synthesized answer
```

For PostgreSQL (production), we use `tsvector`:

```sql
SELECT * FROM memories
WHERE to_tsvector('english', summary || ' ' || source)
      @@ plainto_tsquery('english', $1)
ORDER BY ts_rank(...) DESC
LIMIT 20;
```

Same concept, different engine. No Pinecone. No OpenSearch. No monthly infrastructure bill.

## Handling Large Inputs: Chunking Strategy

The original system failed silently on large files — the LLM would use all its output tokens describing the content and never call `store_memory`. Our solution: **automatic paragraph-aware chunking**.

```python
def chunk_text(text: str, max_chars: int = 3000, overlap: int = 200):
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    paragraphs = text.split("\n\n")
    current_chunk = ""
    
    for para in paragraphs:
        if len(current_chunk) + len(para) > max_chars:
            chunks.append(current_chunk)
            # Overlap preserves context at boundaries
            current_chunk = chunks[-1][-overlap:] + "\n\n" + para
        else:
            current_chunk += "\n\n" + para
    
    return chunks
```

A 10,000-character document becomes 3-4 chunks, each independently ingested with source attribution (`"meeting-notes.md (part 2/4)"`). Combined with SHA256 deduplication, re-ingesting the same file is a no-op.

## Cost Breakdown: $3/month for 24/7 Operation

| Operation | Input | Output | Frequency | Monthly |
|---|---|---|---|---|
| Ingest | ~800 tokens | ~400 tokens | 50/day | $0.60 |
| Consolidate | ~2500 tokens | ~600 tokens | 48/day | $1.20 |
| Query | ~3000 tokens | ~500 tokens | 30/day | $1.50 |
| **Total** | | | | **~$3.30** |

Compare:
- Pinecone Starter: **$70/month**
- OpenSearch Serverless: **$175/month**
- Weaviate Cloud: **$25/month**
- Our system: **$3.30/month** (and that's the *entire* system, not just storage)

The trick: Claude Haiku 4.5 is cheap enough to be the encoding, consolidation, AND retrieval engine simultaneously.

## Production Considerations

### Database Backend

Development → SQLite (zero config, single file):
```bash
MEMORY_DB=data/memory.db
```

Production → PostgreSQL (managed, persistent):
```bash
DATABASE_URL=postgresql://user:pass@rds-instance.amazonaws.com:5432/memorydb
```

The agent auto-detects which backend to use. Same interface, different engine.

### Retry Logic

Bedrock occasionally returns `ModelErrorException` (malformed tool output from the model). We handle this with exponential backoff:

```python
RETRYABLE_ERRORS = ("ModelErrorException", "ThrottlingException", "ModelTimeoutException")

for attempt in range(MAX_RETRIES):
    try:
        return client.converse(**kwargs)
    except ClientError as e:
        if e.response["Error"]["Code"] in RETRYABLE_ERRORS:
            time.sleep(RETRY_BACKOFF * (2 ** attempt))
        else:
            raise
```

### Streaming Responses

For query latency perception, we support Server-Sent Events:

```bash
curl -N "http://localhost:8888/query/stream?q=summarize+everything"

data: Based on
data:  your memories,
data:  here are the key
data:  patterns...
data: [DONE]
```

Using `converse_stream` on the Bedrock side, tokens flow to the client as they're generated.

## When to Use This vs RAG

| Use This When | Use RAG When |
|---|---|
| Information accumulates over time | You have a static document corpus |
| You need cross-source synthesis | You need exact chunk retrieval |
| Pattern discovery matters | Similarity search is sufficient |
| Budget is constrained | You can afford vector DB infra |
| You want proactive insights | Reactive Q&A is enough |
| <1000 memories | >10,000 documents |
| Personal/team knowledge | Enterprise-scale search |

They can also be complementary: use RAG for your document corpus, use this agent for synthesis and insight discovery on top.

## Try It

```bash
git clone https://github.com/aafaq-rashid-comprinno/always-on-memory-agent
cd always-on-memory-agent
cp .env.example .env
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... AWS_REGION=us-east-1
docker compose up --build
```

Dashboard at http://localhost:8501. API at http://localhost:8888.

Feed it your notes, articles, meeting summaries. Wait for consolidation. Then ask: *"What patterns do you see?"*

You might be surprised what your own information has been trying to tell you.

---

*The full source, architecture docs, and a research paper are at [github.com/aafaq-rashid-comprinno/always-on-memory-agent](https://github.com/aafaq-rashid-comprinno/always-on-memory-agent).*
