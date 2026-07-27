"""
Tool executor - routes LLM tool calls to the repository layer.
"""

import logging

from src.db.repository import MemoryRepository

log = logging.getLogger("memory-agent")


class ToolExecutor:
    """Executes tool calls by routing to the MemoryRepository."""

    def __init__(self, repo: MemoryRepository):
        self._repo = repo
        self._handlers = {
            "store_memory": self._store_memory,
            "read_all_memories": self._read_all_memories,
            "read_unconsolidated_memories": self._read_unconsolidated_memories,
            "store_consolidation": self._store_consolidation,
            "read_consolidation_history": self._read_consolidation_history,
            "get_memory_stats": self._get_memory_stats,
        }

    def execute(self, tool_name: str, params: dict) -> dict:
        """Execute a tool by name with given parameters."""
        handler = self._handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return handler(params)
        except Exception as e:
            log.error(f"Tool execution error ({tool_name}): {e}")
            return {"error": str(e)}

    def _store_memory(self, params: dict) -> dict:
        result = self._repo.store_memory(
            raw_text=params["raw_text"],
            summary=params["summary"],
            entities=params.get("entities", []),
            topics=params.get("topics", []),
            importance=params.get("importance", 0.5),
            source=params.get("source", ""),
        )
        log.info(f"📥 Stored memory #{result['memory_id']}: {params['summary'][:60]}")
        return result

    def _read_all_memories(self, params: dict) -> dict:
        return self._repo.get_all_memories()

    def _read_unconsolidated_memories(self, params: dict) -> dict:
        return self._repo.get_unconsolidated_memories()

    def _store_consolidation(self, params: dict) -> dict:
        result = self._repo.store_consolidation(
            source_ids=params["source_ids"],
            summary=params["summary"],
            insight=params["insight"],
            connections=params.get("connections", []),
        )
        log.info(f"🔄 Consolidated {result['memories_processed']} memories")
        return result

    def _read_consolidation_history(self, params: dict) -> dict:
        return self._repo.get_consolidation_history()

    def _get_memory_stats(self, params: dict) -> dict:
        return self._repo.get_stats()
