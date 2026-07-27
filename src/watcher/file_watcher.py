"""
File watcher - monitors a folder for new files and auto-ingests them.
"""

import asyncio
import logging
from pathlib import Path

from src.agents.memory_agent import MemoryAgent
from src.config import get_settings
from src.config.constants import (
    TEXT_EXTENSIONS,
    IMAGE_EXTENSIONS,
    DOCUMENT_EXTENSIONS,
    ALL_SUPPORTED_EXTENSIONS,
)
from src.db.repository import MemoryRepository

log = logging.getLogger("memory-agent")


async def watch_folder(agent: MemoryAgent) -> None:
    """
    Watch the configured folder for new files and ingest them.

    Runs as a background asyncio task. Polls at the configured interval.
    """
    settings = get_settings()
    repo = MemoryRepository()
    folder = settings.watch_path
    folder.mkdir(parents=True, exist_ok=True)

    log.info(f"👁️  Watching: {folder}/ (text, images, PDFs)")

    while True:
        try:
            for f in sorted(folder.iterdir()):
                if f.name.startswith("."):
                    continue

                suffix = f.suffix.lower()
                if suffix not in ALL_SUPPORTED_EXTENSIONS:
                    continue

                if repo.is_file_processed(str(f)):
                    continue

                try:
                    _ingest_file(agent, f, suffix)
                except Exception as e:
                    log.error(f"Error ingesting {f.name}: {e}")

                repo.mark_file_processed(str(f))

        except Exception as e:
            log.error(f"Watch error: {e}")

        await asyncio.sleep(settings.watch_poll_interval)


def _ingest_file(agent: MemoryAgent, file_path: Path, suffix: str) -> None:
    """Route a file to the appropriate ingestion method."""
    settings = get_settings()

    if suffix in TEXT_EXTENSIONS:
        log.info(f"📄 New text file: {file_path.name}")
        text = file_path.read_text(encoding="utf-8", errors="replace")[: settings.max_text_chars]
        if text.strip():
            agent.ingest(text, source=file_path.name)

    elif suffix in IMAGE_EXTENSIONS:
        agent.ingest_image(file_path)

    elif suffix in DOCUMENT_EXTENSIONS:
        agent.ingest_document(file_path)
