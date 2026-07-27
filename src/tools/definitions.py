"""
Tool definitions in Bedrock Converse API format.

Each tool spec defines the schema that the LLM uses to generate
structured tool calls.
"""

# ─── Individual Tool Specs ─────────────────────────────────────

STORE_MEMORY_SPEC = {
    "toolSpec": {
        "name": "store_memory",
        "description": "Store a processed memory in the database.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "raw_text": {
                        "type": "string",
                        "description": "Original input text or full description of content",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Concise 1-2 sentence summary",
                    },
                    "entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Key people, companies, products, or concepts",
                    },
                    "topics": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 topic tags",
                    },
                    "importance": {
                        "type": "number",
                        "description": "Float 0.0 to 1.0 indicating importance",
                    },
                    "source": {
                        "type": "string",
                        "description": "Where this information came from",
                    },
                },
                "required": ["raw_text", "summary", "entities", "topics", "importance"],
            }
        },
    }
}

READ_ALL_MEMORIES_SPEC = {
    "toolSpec": {
        "name": "read_all_memories",
        "description": "Read all stored memories from the database, most recent first.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}

READ_UNCONSOLIDATED_MEMORIES_SPEC = {
    "toolSpec": {
        "name": "read_unconsolidated_memories",
        "description": "Read memories that have not been consolidated yet.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}

STORE_CONSOLIDATION_SPEC = {
    "toolSpec": {
        "name": "store_consolidation",
        "description": "Store a consolidation result and mark source memories as consolidated.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "source_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "IDs of memories that were consolidated",
                    },
                    "summary": {
                        "type": "string",
                        "description": "Synthesized summary across source memories",
                    },
                    "insight": {
                        "type": "string",
                        "description": "One key pattern or insight discovered",
                    },
                    "connections": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from_id": {"type": "integer"},
                                "to_id": {"type": "integer"},
                                "relationship": {"type": "string"},
                            },
                        },
                        "description": "Connections found between memories",
                    },
                },
                "required": ["source_ids", "summary", "insight", "connections"],
            }
        },
    }
}

READ_CONSOLIDATION_HISTORY_SPEC = {
    "toolSpec": {
        "name": "read_consolidation_history",
        "description": "Read past consolidation insights.",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}

GET_MEMORY_STATS_SPEC = {
    "toolSpec": {
        "name": "get_memory_stats",
        "description": "Get current memory statistics (total, unconsolidated, consolidations).",
        "inputSchema": {"json": {"type": "object", "properties": {}}},
    }
}

# ─── All Specs ─────────────────────────────────────────────────

TOOL_SPECS: list[dict] = [
    STORE_MEMORY_SPEC,
    READ_ALL_MEMORIES_SPEC,
    READ_UNCONSOLIDATED_MEMORIES_SPEC,
    STORE_CONSOLIDATION_SPEC,
    READ_CONSOLIDATION_HISTORY_SPEC,
    GET_MEMORY_STATS_SPEC,
]

# ─── Tool Subsets Per Agent Type ───────────────────────────────

TOOL_MAP: dict[str, list[dict]] = {
    "ingest": [STORE_MEMORY_SPEC],
    "consolidate": [READ_UNCONSOLIDATED_MEMORIES_SPEC, STORE_CONSOLIDATION_SPEC],
    "query": [READ_ALL_MEMORIES_SPEC, READ_CONSOLIDATION_HISTORY_SPEC],
    "status": [GET_MEMORY_STATS_SPEC],
}
