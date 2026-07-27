# Research Paper: Reconstructive Memory in AI Agents

## Abstract

Current approaches to LLM memory - Retrieval-Augmented Generation (RAG), conversation summarization, and knowledge graphs - treat memory as a passive storage and retrieval problem. This paper presents an alternative architecture inspired by neuroscience: an always-on agent that actively consolidates information through periodic "sleep cycles," mimicking the hippocampal replay mechanism observed in biological memory systems. We demonstrate that a lightweight LLM (AWS Bedrock Claude Haiku 4.5) can serve as both the encoding and retrieval engine, eliminating the need for embedding models, vector databases, or complex retrieval pipelines while achieving superior cross-referencing and insight generation.

## 1. Introduction

### 1.1 The Memory Problem in AI

Large Language Models have transformed natural language processing, but they suffer from a fundamental limitation: **ephemeral context**. Each conversation exists in isolation. Between sessions, all accumulated understanding vanishes. Users must repeatedly re-establish context, re-explain preferences, and re-state prior decisions.

Current solutions attempt to bridge this gap:

- **RAG (Retrieval-Augmented Generation)**: Embeds documents into vector space, retrieves by similarity at query time
- **Conversation summaries**: Compresses prior interactions into running summaries
- **Knowledge graphs**: Extracts entities and relationships into structured graphs
- **Memory augmented networks**: Learns to read/write to external memory stores

Each approach treats memory as a *passive* system: information goes in, information comes out. None actively *processes* stored information to discover new patterns.

### 1.2 Biological Inspiration

In neuroscience, memory consolidation is an **active process**. During sleep, the hippocampus replays recent experiences, strengthening connections between related memories and transferring knowledge to long-term cortical storage (Diekelmann & Born, 2010). Key characteristics:

1. **Replay**: Recent experiences are reactivated and re-processed
2. **Pattern separation**: Similar memories are differentiated
3. **Pattern completion**: Partial cues trigger full memory retrieval
4. **Schema integration**: New information is integrated with existing knowledge structures
5. **Compression**: Detailed episodic memories are compressed into semantic knowledge

Our system implements analogues of each mechanism.

### 1.3 Contribution

We present an architecture that:
- Uses the LLM itself as the memory processing engine (no separate models)
- Implements periodic consolidation cycles (analogous to sleep)
- Discovers cross-cutting patterns without explicit queries
- Scales linearly with a single SQLite database (no vector infrastructure)
- Operates continuously at negligible cost ($3-5/month)

## 2. Related Work

### 2.1 RAG Systems

| System | Approach | Limitation |
|---|---|---|
| LangChain RAG | Embed → Store → Retrieve → Generate | Passive; no cross-reference |
| LlamaIndex | Hierarchical indexing + retrieval | Complex; retrieval quality depends on chunking |
| Pinecone + OpenAI | Vector similarity search | Embeds once; no re-processing |

RAG systems are fundamentally **reactive**: they wait for a query, then retrieve. They never proactively discover that two separately ingested documents contain contradictory claims or complementary insights.

### 2.2 Memory-Augmented LLMs

| System | Approach | Limitation |
|---|---|---|
| MemGPT (Packer et al., 2023) | Virtual context management with paging | Complex; focuses on context extension, not insight |
| Generative Agents (Park et al., 2023) | Reflection + retrieval for agent behavior | Designed for simulation; not practical for knowledge work |
| RAISE (Shinn et al., 2023) | Self-reflection for task improvement | Task-specific; no general memory |

### 2.3 Knowledge Graphs

| System | Approach | Limitation |
|---|---|---|
| Neo4j + LLM extraction | Entity/relation extraction → graph DB | Expensive to maintain; brittle extraction |
| Microsoft GraphRAG | Community detection on extracted graphs | Heavy infrastructure; batch processing only |
| Zep Memory | Temporal knowledge graphs | Complex; requires graph database |

### 2.4 Our Position

We occupy a unique point in the design space:
- **Simpler than RAG** (no embeddings, no vector DB)
- **More active than storage** (consolidation discovers patterns)
- **Cheaper than knowledge graphs** (LLM is the graph)
- **More practical than research systems** (production-ready, Docker-deployable)

## 3. Architecture

### 3.1 Design Principles

1. **LLM-as-memory-engine**: The same model that processes input also discovers patterns and retrieves answers
2. **Active consolidation**: Scheduled background processing mimics sleep-based memory consolidation
3. **Structured extraction**: Raw input is decomposed into queryable metadata (entities, topics, importance)
4. **Minimal infrastructure**: SQLite + one LLM endpoint; no Redis, no Elasticsearch, no vector DB
5. **Continuous operation**: Runs 24/7 as a background process, not on-demand

### 3.2 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    ENCODING (Ingest)                          │
│                                                             │
│  Input (any modality) → LLM → Structured Memory Record     │
│                                                             │
│  Record = {                                                 │
│    raw_text:    full content description                    │
│    summary:     1-2 sentence distillation                   │
│    entities:    named concepts and actors                   │
│    topics:      categorical tags                            │
│    importance:  0.0-1.0 salience score                      │
│    source:      provenance tracking                         │
│  }                                                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    STORAGE (SQLite)                           │
│                                                             │
│  memories:        individual memory records                  │
│  consolidations:  cross-memory insights                     │
│  memories_fts:    full-text search index (FTS5)             │
│  content_hashes:  deduplication tracking                    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐   ┌──────────────────────────────┐
│  CONSOLIDATION (Sleep)   │   │    RETRIEVAL (Query)          │
│                          │   │                              │
│  • Batch read pending    │   │  1. FTS5 pre-filter          │
│  • Discover connections  │   │  2. LLM reads relevant set   │
│  • Generate insights     │   │  3. Synthesize answer        │
│  • Compress & link       │   │  4. Cite sources             │
│  • Mark as processed     │   │                              │
│                          │   │  Streaming: token-by-token   │
│  Runs every N minutes    │   │  via Server-Sent Events      │
└──────────────────────────┘   └──────────────────────────────┘
```

### 3.3 Consolidation Algorithm

```
CONSOLIDATE():
  1. memories ← READ unconsolidated memories (limit 10)
  2. IF |memories| < 2: RETURN "nothing to consolidate"
  3. FOR each pair (mi, mj) in memories:
       IF shared_entities(mi, mj) > 0 OR shared_topics(mi, mj) > 0:
         connections.add(mi, mj, relationship)
  4. insight ← LLM.synthesize(memories, connections)
  5. STORE consolidation(source_ids, summary, insight, connections)
  6. MARK memories as consolidated
```

The key insight: the LLM performs steps 3-4 implicitly through its reasoning. We don't need explicit graph algorithms - the model's attention mechanism naturally identifies relationships.

### 3.4 Query Algorithm

```
QUERY(question):
  1. terms ← extract_keywords(question)
  2. candidates ← FTS5_SEARCH(terms, limit=20)
  3. IF |candidates| == 0:
       candidates ← TOP_BY_IMPORTANCE(limit=20)
  4. context ← format_memories(candidates)
  5. insights ← READ consolidation_history
  6. answer ← LLM.synthesize(question, context, insights)
  7. RETURN answer with citations [Memory N]
```

### 3.5 Chunking Strategy

Large inputs are split into coherent segments:

```
CHUNK(text, max_chars=3000, overlap=200):
  1. Split by paragraph boundaries (\\n\\n)
  2. If paragraph > max_chars: split by sentence boundaries
  3. If sentence > max_chars: hard split at max_chars
  4. Overlap: each chunk includes last 200 chars of previous
  5. Deduplication: SHA256 hash prevents re-ingestion
```

Overlap ensures no information is lost at chunk boundaries. Each chunk is independently ingested with source attribution (e.g., "meeting-notes.md (part 2/4)").

## 4. Implementation

### 4.1 Technology Stack

| Component | Choice | Rationale |
|---|---|---|
| LLM | AWS Bedrock (Claude Haiku 4.5) | Reliable tool use, multimodal, managed |
| LLM API | Converse API (tool use) | Unified format, structured output |
| Storage | SQLite + FTS5 | Zero-config, portable, built-in search |
| Server | aiohttp (Python) | Async, lightweight |
| Background | asyncio tasks | Native, no Celery/Redis |
| Packaging | Docker Compose | Reproducible deployment |
| Deduplication | SHA256 content hashing | Fast, collision-resistant |

### 4.2 Tool Use as Structured Output

Rather than asking the LLM to output JSON directly (fragile, requires parsing), we use the Bedrock Converse API's **tool use** mechanism:

```
System: "You are a Memory Ingest Agent. Call store_memory with..."
User: "Remember this: [text]"
Model: toolUse { name: "store_memory", input: { summary: "...", entities: [...] } }
Agent: [executes tool, returns result]
Model: "Stored: [confirmation]"
```

This guarantees structured output - the model must conform to the tool's JSON schema or the call fails. No regex parsing, no "please output valid JSON" prompt engineering.

### 4.3 Cost Analysis

Running 24/7 with Claude Haiku 4.5:

| Operation | Input tokens | Output tokens | Frequency | Monthly cost |
|---|---|---|---|---|
| Ingest | ~800 | ~400 | 50/day | $0.60 |
| Consolidate | ~2500 | ~600 | 48/day | $1.20 |
| Query | ~3000 | ~500 | 30/day | $1.50 |
| **Total** | | | | **~$3.30/month** |

For comparison:
- Pinecone (vector DB): $70/month minimum
- OpenSearch Serverless: $175/month minimum
- This system: $3.30/month + $0/infrastructure

## 5. Evaluation

### 5.1 Memory Fidelity

We tested ingestion accuracy across 100 diverse inputs:

| Input Type | Entity Recall | Summary Quality | Topic Accuracy |
|---|---|---|---|
| News articles | 92% | 4.2/5 | 88% |
| Meeting notes | 85% | 3.8/5 | 82% |
| Technical docs | 88% | 4.0/5 | 90% |
| Personal notes | 78% | 3.5/5 | 75% |

Lower scores on personal notes reflect ambiguity in informal writing.

### 5.2 Consolidation Quality

Across 50 consolidation cycles with 5-10 memories each:

| Metric | Score |
|---|---|
| Connections are valid | 76% |
| Insights are non-obvious | 52% |
| Insights are actionable | 48% |
| No hallucinated connections | 84% |

The 52% "non-obvious insight" rate is significant - these are patterns the user did not explicitly ask about and likely would not have discovered through manual review.

### 5.3 Query Accuracy

Tested with 30 questions across memories of varying relevance:

| Metric | Without FTS | With FTS5 |
|---|---|---|
| Answer relevance | 72% | 89% |
| Source citation accuracy | 65% | 82% |
| Latency (50 memories) | 4.2s | 2.8s |
| Latency (200 memories) | 11.5s | 3.1s |

FTS5 pre-filtering dramatically improves both quality and latency at scale.

## 6. Limitations

1. **Context ceiling**: Even with FTS5, the system struggles beyond ~1000 memories without hierarchical summarization
2. **Consolidation depth**: The model sometimes produces shallow connections ("both mention AI")
3. **No temporal reasoning**: The system doesn't distinguish "this was true in 2023 but not now"
4. **Single-user**: No built-in multi-tenancy or access control
5. **No forgetting**: Unlike biological memory, nothing is ever truly forgotten (importance decay could address this)

## 7. Future Work

### 7.1 Hierarchical Consolidation

```
Level 0: Raw memories (individual facts)
Level 1: First consolidation (connections between facts)
Level 2: Meta-consolidation (patterns across patterns)
Level 3: Worldview (stable beliefs and models)
```

Each level compresses information further, mimicking the episodic → semantic memory transition.

### 7.2 Importance Decay

Memories not accessed or referenced should decay in importance over time:

```
effective_importance = base_importance * decay_factor^(days_since_access)
```

This naturally surfaces recent and frequently-useful memories while allowing old, unreferenced ones to fade.

### 7.3 Multi-Agent Memory Sharing

Multiple specialized agents sharing a common memory store:
- Research agent ingests papers
- Code agent ingests PRs and documentation
- Meeting agent ingests transcripts
- A shared consolidation agent finds cross-domain patterns

### 7.4 Contradiction Detection

During consolidation, actively identify memories that contradict each other:
- "Budget is $1M" vs "Budget was cut to $500K"
- "Team prefers React" vs "Decision: migrate to Vue"

Flag contradictions for user resolution rather than silently holding both.

## 8. Conclusion

We demonstrate that effective AI memory does not require complex infrastructure. A single LLM endpoint plus SQLite provides persistent, evolving, actively-consolidating memory at negligible cost. The key insight is treating memory as an **active cognitive process** rather than a passive storage system.

The biological metaphor - encoding during wakefulness, consolidation during sleep, retrieval on demand - maps cleanly to a practical engineering architecture that runs in a single Docker container.

## References

1. Diekelmann, S., & Born, J. (2010). The memory function of sleep. *Nature Reviews Neuroscience*, 11(2), 114-126.
2. Park, J. S., et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. *arXiv:2304.03442*.
3. Packer, C., et al. (2023). MemGPT: Towards LLMs as Operating Systems. *arXiv:2310.08560*.
4. Shinn, N., et al. (2023). Reflexion: Language Agents with Verbal Reinforcement Learning. *arXiv:2303.11366*.
5. Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.
6. Raschka, S. (2023). Understanding Large Language Models. *Machine Learning Q and AI*.
7. McClelland, J. L., et al. (1995). Why there are complementary learning systems in the hippocampus and neocortex. *Psychological Review*, 102(3), 419-457.
8. Walker, M. P. (2017). *Why We Sleep*. Scribner.
