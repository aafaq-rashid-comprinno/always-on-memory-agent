"""
High-level Memory Agent that combines the Bedrock client,
tool definitions, and system prompts into a clean interface.
"""

import logging
from pathlib import Path

from src.config import get_settings
from src.config.constants import (
    IMAGE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    SYSTEM_PROMPTS,
)
from src.db.repository import MemoryRepository
from src.tools.definitions import TOOL_MAP
from src.tools.executor import ToolExecutor
from src.agents.client import BedrockClient

log = logging.getLogger("memory-agent")


class MemoryAgent:
    """
    The main agent interface. Provides ingest, consolidate, query,
    and management operations.
    """

    def __init__(self):
        self._settings = get_settings()
        self._repo = MemoryRepository()
        self._executor = ToolExecutor(self._repo)
        self._client = BedrockClient(self._executor)

    # ─── Core Agent Operations ─────────────────────────────────

    def ingest(self, text: str, source: str = "") -> str:
        """Ingest text into memory."""
        msg = (
            f"Remember this information (source: {source}):\n\n{text}"
            if source
            else f"Remember this:\n\n{text}"
        )
        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["ingest"],
            user_message=msg,
            tools=TOOL_MAP["ingest"],
        )

    def ingest_image(self, file_path: Path) -> str:
        """Ingest an image file via multimodal."""
        suffix = file_path.suffix.lower()
        fmt = IMAGE_EXTENSIONS.get(suffix)
        if not fmt:
            return f"Unsupported image format: {suffix}"

        image_bytes = file_path.read_bytes()
        size_mb = len(image_bytes) / (1024 * 1024)
        if size_mb > self._settings.max_image_mb:
            log.warning(f"Skipping {file_path.name} ({size_mb:.1f}MB) - exceeds limit")
            return f"Skipped: image too large ({size_mb:.1f}MB)"

        content_blocks = [{"image": {"format": fmt, "source": {"bytes": image_bytes}}}]
        msg = f"Analyze this image and extract all meaningful information (source: {file_path.name})."
        log.info(f"🖼️  Ingesting image: {file_path.name} ({size_mb:.1f}MB)")

        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["ingest"],
            user_message=msg,
            tools=TOOL_MAP["ingest"],
            content_blocks=content_blocks,
        )

    def ingest_document(self, file_path: Path) -> str:
        """Ingest a PDF document."""
        doc_bytes = file_path.read_bytes()
        size_mb = len(doc_bytes) / (1024 * 1024)
        if size_mb > self._settings.max_document_mb:
            log.warning(f"Skipping {file_path.name} ({size_mb:.1f}MB) - exceeds limit")
            return f"Skipped: document too large ({size_mb:.1f}MB)"

        content_blocks = [
            {"document": {"format": "pdf", "name": file_path.stem, "source": {"bytes": doc_bytes}}}
        ]
        msg = f"Analyze this PDF and extract all meaningful information (source: {file_path.name})."
        log.info(f"📄 Ingesting document: {file_path.name} ({size_mb:.1f}MB)")

        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["ingest"],
            user_message=msg,
            tools=TOOL_MAP["ingest"],
            content_blocks=content_blocks,
        )

    def consolidate(self) -> str:
        """Run memory consolidation."""
        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["consolidate"],
            user_message="Consolidate unconsolidated memories. Find connections and patterns.",
            tools=TOOL_MAP["consolidate"],
        )

    def query(self, question: str) -> str:
        """Query the memory store."""
        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["query"],
            user_message=f"Based on my memories, answer: {question}",
            tools=TOOL_MAP["query"],
        )

    def status(self) -> str:
        """Get a human-readable status report."""
        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["status"],
            user_message="Give me a status report on my memory system.",
            tools=TOOL_MAP["status"],
        )

    # ─── Direct Data Operations (bypass LLM) ──────────────────

    def get_stats(self) -> dict:
        """Get raw memory statistics."""
        return self._repo.get_stats()

    def get_all_memories(self) -> dict:
        """Get all memories as structured data."""
        return self._repo.get_all_memories()

    def delete_memory(self, memory_id: int) -> dict:
        """Delete a specific memory."""
        return self._repo.delete_memory(memory_id)

    def clear_all(self) -> dict:
        """Delete all memories and reset."""
        return self._repo.clear_all(inbox_path=self._settings.watch_dir)
