"""Tests for the memory repository."""

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch):
    """Use a temporary database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        monkeypatch.setenv("MEMORY_DB", f.name)
        # Clear cached settings
        from src.config.settings import get_settings
        get_settings.cache_clear()

        from src.db import init_db
        init_db()
        yield f.name

    os.unlink(f.name)


def test_store_and_retrieve_memory():
    from src.db.repository import MemoryRepository

    repo = MemoryRepository()
    result = repo.store_memory(
        raw_text="AI is transforming software development",
        summary="AI transforms software dev",
        entities=["AI"],
        topics=["technology", "software"],
        importance=0.8,
        source="test",
    )

    assert result["status"] == "stored"
    assert result["memory_id"] == 1

    memories = repo.get_all_memories()
    assert memories["count"] == 1
    assert memories["memories"][0]["summary"] == "AI transforms software dev"


def test_get_stats():
    from src.db.repository import MemoryRepository

    repo = MemoryRepository()
    repo.store_memory("text", "summary", ["e"], ["t"], 0.5)
    repo.store_memory("text2", "summary2", ["e2"], ["t2"], 0.7)

    stats = repo.get_stats()
    assert stats["total_memories"] == 2
    assert stats["unconsolidated"] == 2
    assert stats["consolidations"] == 0


def test_delete_memory():
    from src.db.repository import MemoryRepository

    repo = MemoryRepository()
    result = repo.store_memory("text", "summary", [], [], 0.5)
    mid = result["memory_id"]

    delete_result = repo.delete_memory(mid)
    assert delete_result["status"] == "deleted"

    stats = repo.get_stats()
    assert stats["total_memories"] == 0


def test_consolidation():
    from src.db.repository import MemoryRepository

    repo = MemoryRepository()
    repo.store_memory("text1", "summary1", ["AI"], ["tech"], 0.5)
    repo.store_memory("text2", "summary2", ["ML"], ["tech"], 0.7)

    result = repo.store_consolidation(
        source_ids=[1, 2],
        summary="AI and ML are related",
        insight="Both are subfields of computer science",
        connections=[{"from_id": 1, "to_id": 2, "relationship": "related field"}],
    )

    assert result["status"] == "consolidated"
    assert result["memories_processed"] == 2

    # Memories should now be marked consolidated
    unconsolidated = repo.get_unconsolidated_memories()
    assert unconsolidated["count"] == 0


def test_file_tracking():
    from src.db.repository import MemoryRepository

    repo = MemoryRepository()
    assert not repo.is_file_processed("/tmp/test.txt")

    repo.mark_file_processed("/tmp/test.txt")
    assert repo.is_file_processed("/tmp/test.txt")
