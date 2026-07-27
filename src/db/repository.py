"""
Memory repository - all database CRUD operations.
Includes deduplication and full-text search (FTS5).
"""

import json
from datetime import datetime, timezone

from src.db.connection import get_db


class MemoryRepository:
    """Clean data access layer for the memory store."""

    # ─── Memories ──────────────────────────────────────────────

    def store_memory(
        self,
        raw_text: str,
        summary: str,
        entities: list[str],
        topics: list[str],
        importance: float,
        source: str = "",
    ) -> dict:
        """Store a new memory and return its ID."""
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        cursor = db.execute(
            "INSERT INTO memories (source, raw_text, summary, entities, topics, importance, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (source, raw_text, summary, json.dumps(entities), json.dumps(topics), importance, now),
        )
        memory_id = cursor.lastrowid

        # Update FTS index
        db.execute(
            "INSERT INTO memories_fts (rowid, summary, entities, topics) VALUES (?, ?, ?, ?)",
            (memory_id, summary, " ".join(entities), " ".join(topics)),
        )

        db.commit()
        db.close()
        return {"memory_id": memory_id, "status": "stored", "summary": summary}

    def get_all_memories(self, limit: int = 50) -> dict:
        """Get all memories, most recent first."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        memories = [self._row_to_memory(r) for r in rows]
        db.close()
        return {"memories": memories, "count": len(memories)}

    def get_unconsolidated_memories(self, limit: int = 10) -> dict:
        """Get memories that haven't been consolidated yet."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM memories WHERE consolidated = 0 ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        memories = [
            {
                "id": r["id"],
                "summary": r["summary"],
                "entities": json.loads(r["entities"]),
                "topics": json.loads(r["topics"]),
                "importance": r["importance"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
        db.close()
        return {"memories": memories, "count": len(memories)}

    def delete_memory(self, memory_id: int) -> dict:
        """Delete a memory by ID."""
        db = get_db()
        row = db.execute("SELECT 1 FROM memories WHERE id = ?", (memory_id,)).fetchone()
        if not row:
            db.close()
            return {"status": "not_found", "memory_id": memory_id}
        db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        db.execute("DELETE FROM memories_fts WHERE rowid = ?", (memory_id,))
        db.commit()
        db.close()
        return {"status": "deleted", "memory_id": memory_id}

    # ─── Full-Text Search ──────────────────────────────────────

    def search_memories(self, query: str, limit: int = 20) -> dict:
        """
        Search memories using FTS5 full-text search.
        Falls back to LIKE if FTS returns no results.
        """
        db = get_db()

        # Build FTS query - split into terms, join with OR
        terms = [t.strip() for t in query.split() if len(t.strip()) > 2]
        if not terms:
            # No useful search terms, return recent memories
            rows = db.execute(
                "SELECT * FROM memories ORDER BY importance DESC, created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            fts_query = " OR ".join(terms)
            try:
                rows = db.execute(
                    """
                    SELECT m.* FROM memories m
                    JOIN memories_fts fts ON m.id = fts.rowid
                    WHERE memories_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (fts_query, limit),
                ).fetchall()
            except Exception:
                # FTS failed (malformed query), fall back to LIKE
                like_pattern = f"%{terms[0]}%"
                rows = db.execute(
                    "SELECT * FROM memories WHERE summary LIKE ? OR entities LIKE ? OR topics LIKE ? "
                    "ORDER BY importance DESC LIMIT ?",
                    (like_pattern, like_pattern, like_pattern, limit),
                ).fetchall()

        memories = [self._row_to_memory(r) for r in rows]
        db.close()
        return {"memories": memories, "count": len(memories)}

    # ─── Consolidations ────────────────────────────────────────

    def store_consolidation(
        self,
        source_ids: list[int],
        summary: str,
        insight: str,
        connections: list[dict],
    ) -> dict:
        """Store consolidation and mark source memories as processed."""
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()

        db.execute(
            "INSERT INTO consolidations (source_ids, summary, insight, created_at) VALUES (?, ?, ?, ?)",
            (json.dumps(source_ids), summary, insight, now),
        )

        # Update connections on linked memories
        for conn in connections:
            from_id, to_id = conn.get("from_id"), conn.get("to_id")
            rel = conn.get("relationship", "")
            if from_id and to_id:
                for mid in [from_id, to_id]:
                    row = db.execute("SELECT connections FROM memories WHERE id = ?", (mid,)).fetchone()
                    if row:
                        existing = json.loads(row["connections"])
                        existing.append({
                            "linked_to": to_id if mid == from_id else from_id,
                            "relationship": rel,
                        })
                        db.execute(
                            "UPDATE memories SET connections = ? WHERE id = ?",
                            (json.dumps(existing), mid),
                        )

        # Mark as consolidated
        if source_ids:
            placeholders = ",".join("?" * len(source_ids))
            db.execute(
                f"UPDATE memories SET consolidated = 1 WHERE id IN ({placeholders})",
                source_ids,
            )

        db.commit()
        db.close()
        return {
            "status": "consolidated",
            "memories_processed": len(source_ids),
            "insight": insight,
        }

    def get_consolidation_history(self, limit: int = 10) -> dict:
        """Get past consolidation insights."""
        db = get_db()
        rows = db.execute(
            "SELECT * FROM consolidations ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result = [
            {"summary": r["summary"], "insight": r["insight"], "source_ids": json.loads(r["source_ids"])}
            for r in rows
        ]
        db.close()
        return {"consolidations": result, "count": len(result)}

    # ─── Deduplication ─────────────────────────────────────────

    def is_duplicate(self, text_hash: str) -> bool:
        """Check if content with this hash has already been ingested."""
        db = get_db()
        row = db.execute("SELECT 1 FROM content_hashes WHERE hash = ?", (text_hash,)).fetchone()
        db.close()
        return row is not None

    def record_hash(self, text_hash: str) -> None:
        """Record a content hash to prevent future duplicates."""
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR IGNORE INTO content_hashes (hash, created_at) VALUES (?, ?)",
            (text_hash, now),
        )
        db.commit()
        db.close()

    # ─── Stats & Management ────────────────────────────────────

    def get_stats(self) -> dict:
        """Get memory statistics."""
        db = get_db()
        total = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        unconsolidated = db.execute(
            "SELECT COUNT(*) as c FROM memories WHERE consolidated = 0"
        ).fetchone()["c"]
        consolidations = db.execute("SELECT COUNT(*) as c FROM consolidations").fetchone()["c"]
        db.close()
        return {
            "total_memories": total,
            "unconsolidated": unconsolidated,
            "consolidations": consolidations,
        }

    def clear_all(self, inbox_path: str = None) -> dict:
        """Delete all memories and reset the database."""
        from pathlib import Path

        db = get_db()
        mem_count = db.execute("SELECT COUNT(*) as c FROM memories").fetchone()["c"]
        db.execute("DELETE FROM memories")
        db.execute("DELETE FROM consolidations")
        db.execute("DELETE FROM processed_files")
        db.execute("DELETE FROM content_hashes")
        # Rebuild FTS index (can't DELETE from contentless FTS5)
        db.execute("DROP TABLE IF EXISTS memories_fts")
        db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(summary, entities, topics, content='')")
        db.commit()
        db.close()

        files_deleted = 0
        if inbox_path:
            folder = Path(inbox_path)
            if folder.is_dir():
                for f in folder.iterdir():
                    if f.name.startswith("."):
                        continue
                    try:
                        if f.is_file():
                            f.unlink()
                            files_deleted += 1
                    except OSError:
                        pass

        return {"status": "cleared", "memories_deleted": mem_count, "files_deleted": files_deleted}

    # ─── File Tracking ─────────────────────────────────────────

    def is_file_processed(self, path: str) -> bool:
        """Check if a file has already been processed."""
        db = get_db()
        row = db.execute("SELECT 1 FROM processed_files WHERE path = ?", (path,)).fetchone()
        db.close()
        return row is not None

    def mark_file_processed(self, path: str) -> None:
        """Mark a file as processed."""
        db = get_db()
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT OR REPLACE INTO processed_files (path, processed_at) VALUES (?, ?)",
            (path, now),
        )
        db.commit()
        db.close()

    # ─── Private ───────────────────────────────────────────────

    @staticmethod
    def _row_to_memory(row) -> dict:
        """Convert a database row to a memory dict."""
        return {
            "id": row["id"],
            "source": row["source"],
            "summary": row["summary"],
            "entities": json.loads(row["entities"]),
            "topics": json.loads(row["topics"]),
            "importance": row["importance"],
            "connections": json.loads(row["connections"]),
            "created_at": row["created_at"],
            "consolidated": bool(row["consolidated"]),
        }
