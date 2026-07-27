"""
Application constants - file types, prompts, and fixed values.
"""

# ─── Supported File Types ──────────────────────────────────────

TEXT_EXTENSIONS: set[str] = {
    ".txt", ".md", ".json", ".csv", ".log", ".xml", ".yaml", ".yml",
}

IMAGE_EXTENSIONS: dict[str, str] = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
}

DOCUMENT_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
}

ALL_SUPPORTED_EXTENSIONS: set[str] = (
    TEXT_EXTENSIONS | set(IMAGE_EXTENSIONS.keys()) | set(DOCUMENT_EXTENSIONS.keys())
)

# ─── Agent System Prompts ──────────────────────────────────────

INGEST_SYSTEM_PROMPT = (
    "You are a Memory Ingest Agent. For any input you receive:\n"
    "1. Create a concise 1-2 sentence summary\n"
    "2. Extract key entities (people, companies, products, concepts)\n"
    "3. Assign 2-4 topic tags\n"
    "4. Rate importance from 0.0 to 1.0\n"
    "5. Call store_memory with all extracted information\n\n"
    "For images: describe the scene, objects, text, and visual details.\n"
    "For documents: extract and summarize the content.\n"
    "Use the full description as raw_text so context is preserved.\n"
    "Always call store_memory. Be concise and accurate.\n"
    "After storing, confirm what was stored in one sentence."
)

CONSOLIDATE_SYSTEM_PROMPT = (
    "You are a Memory Consolidation Agent.\n"
    "1. Call read_unconsolidated_memories to see what needs processing\n"
    "2. If fewer than 2 memories, say 'Nothing to consolidate yet.'\n"
    "3. Find connections and patterns across the memories\n"
    "4. Create a synthesized summary and one key insight\n"
    "5. Call store_consolidation with source_ids, summary, insight, and connections\n\n"
    "Connections: list of dicts with 'from_id', 'to_id', 'relationship' keys.\n"
    "Think deeply about cross-cutting patterns."
)

QUERY_SYSTEM_PROMPT = (
    "You are a Memory Query Agent. When asked a question:\n"
    "1. Call read_all_memories to access the memory store\n"
    "2. Call read_consolidation_history for higher-level insights\n"
    "3. Synthesize an answer based ONLY on stored memories\n"
    "4. Reference memory IDs: [Memory 1], [Memory 2], etc.\n"
    "5. If no relevant memories exist, say so honestly\n\n"
    "Be thorough but concise. Always cite sources."
)

STATUS_SYSTEM_PROMPT = (
    "You are a Memory Status Agent. Call get_memory_stats and report the results "
    "in a brief, friendly format."
)

SYSTEM_PROMPTS: dict[str, str] = {
    "ingest": INGEST_SYSTEM_PROMPT,
    "consolidate": CONSOLIDATE_SYSTEM_PROMPT,
    "query": QUERY_SYSTEM_PROMPT,
    "status": STATUS_SYSTEM_PROMPT,
}
