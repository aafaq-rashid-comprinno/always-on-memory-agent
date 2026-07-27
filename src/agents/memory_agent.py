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
from src.agents.chunking import chunk_text, compute_text_hash

log = logging.getLogger("memory-agent")

# Max chars per chunk for ingestion
CHUNK_SIZE = 3000


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
        """Ingest text into memory. Auto-chunks large inputs."""
        # Deduplication check
        text_hash = compute_text_hash(text)
        if self._repo.is_duplicate(text_hash):
            log.info(f"⏭️  Skipping duplicate: {source or 'unknown'}")
            return "Skipped: duplicate content already stored."

        # Chunk large inputs
        chunks = chunk_text(text, max_chars=CHUNK_SIZE)

        if len(chunks) == 1:
            # Single chunk - normal ingest
            result = self._ingest_single(chunks[0], source, text_hash)
        else:
            # Multi-chunk - ingest each with part indicator
            log.info(f"📄 Chunking input into {len(chunks)} parts ({len(text)} chars)")
            results = []
            for i, chunk in enumerate(chunks, 1):
                chunk_source = f"{source} (part {i}/{len(chunks)})"
                chunk_hash = compute_text_hash(chunk)
                if not self._repo.is_duplicate(chunk_hash):
                    r = self._ingest_single(chunk, chunk_source, chunk_hash)
                    results.append(r)
            result = f"Stored {len(results)} chunks from {source}."

        return result

    def _ingest_single(self, text: str, source: str, text_hash: str) -> str:
        """Ingest a single chunk of text."""
        msg = (
            f"Remember this information (source: {source}):\n\n{text}"
            if source
            else f"Remember this:\n\n{text}"
        )
        response = self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["ingest"],
            user_message=msg,
            tools=TOOL_MAP["ingest"],
        )

        # Store the hash for dedup tracking (even if model didn't call store_memory)
        self._repo.record_hash(text_hash)

        return response

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
        """Query the memory store with FTS pre-filtering."""
        prompt = self._build_query_prompt(question)
        return self._client.invoke(
            system_prompt=SYSTEM_PROMPTS["query"],
            user_message=prompt,
            tools=TOOL_MAP["query"],
        )

    def query_stream(self, question: str):
        """Query with streaming response. Yields text chunks."""
        prompt = self._build_query_prompt(question)
        return self._client.invoke_stream(
            system_prompt=SYSTEM_PROMPTS["query"],
            user_message=prompt,
            tools=TOOL_MAP["query"],
        )

    def _build_query_prompt(self, question: str) -> str:
        """Build the query prompt with FTS pre-filtering."""
        relevant = self._repo.search_memories(question, limit=20)

        if relevant["count"] > 0:
            context = "\n".join(
                f"[Memory {m['id']}] {m['summary']} (entities: {', '.join(m.get('entities', []))})"
                for m in relevant["memories"]
            )
            return (
                f"Based on these relevant memories, answer: {question}\n\n"
                f"Relevant memories:\n{context}"
            )
        return f"Based on my memories, answer: {question}"

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
