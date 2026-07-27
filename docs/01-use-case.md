# Use Case

## Problem Statement

AI assistants today suffer from **memory amnesia**. They process information in real-time but forget everything between sessions. Users repeatedly re-explain context, preferences, and prior decisions. There is no persistent, evolving understanding that grows over time.

## Target Users

| Persona | Pain Point |
|---|---|
| Knowledge workers | Drowning in information across tools - notes, emails, articles, meetings |
| Researchers | Need to track connections across dozens of papers and sources |
| Product teams | Lose institutional knowledge as context switches between projects |
| Executives | Want a "second brain" that synthesizes signals from multiple streams |
| Developers | Context from design docs, Slack threads, and PRs fragments across tools |

## Core Use Cases

### 1. Continuous Information Capture

**Scenario:** A product manager reads 10 articles, attends 3 meetings, and reviews 5 Slack threads daily. By Friday, they cannot recall which article mentioned a specific statistic or which meeting produced a key decision.

**Solution:** Drop files, paste text, or send via API. The agent extracts structure, assigns importance, and stores everything with metadata.

### 2. Automatic Pattern Discovery

**Scenario:** A researcher ingests papers over weeks. Individually, each paper is a data point. But the connections between papers - shared methodologies, contradicting findings, emerging trends - are invisible without deliberate effort.

**Solution:** The consolidation agent runs periodically, finding cross-cutting patterns and generating insights that the user never explicitly asked for.

### 3. Contextual Recall

**Scenario:** "What should I focus on this quarter?" requires synthesizing goals from a planning doc, priorities from a meeting, constraints from a budget review, and signals from market research - all ingested at different times.

**Solution:** The query agent reads all memories plus consolidation insights and synthesizes a grounded answer with source citations.

### 4. Multimodal Memory

**Scenario:** Important information lives in screenshots, photos of whiteboards, voice memos from commutes, PDFs from legal, and video recordings of presentations.

**Solution:** Multimodal ingestion via Bedrock (Nova Lite, Claude) processes images, documents, and text into the same structured memory format.

## What This Is NOT

- Not a search engine (it synthesizes, not retrieves)
- Not a RAG system (no embeddings, no similarity search)
- Not a chatbot (it runs 24/7 as a background process)
- Not a note-taking app (it actively processes and connects)

## Success Metrics

| Metric | Target |
|---|---|
| Information recall accuracy | >85% on ingested content |
| Time to answer (query latency) | <10 seconds |
| Consolidation insight quality | User finds >50% of insights actionable |
| Operational cost (24/7) | <$5/month on Nova Lite |
| Zero-maintenance uptime | Runs unattended for weeks |
