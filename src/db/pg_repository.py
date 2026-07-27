"""
PostgreSQL memory repository - all CRUD operations for managed databases.

Used when DATABASE_URL is set. Provides the same interface as the SQLite
MemoryRepository but uses PostgreSQL-native features (JSONB, tsvector).
"""

import json
from datetime import datetime, timezone

from src.db.postgres import get_pg_connection


class PostgresRepository:
    """PostgreSQL data access layer. Same interface as MemoryRepository."""

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
        """Store a new memory."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO memories (source, raw_text, summary, entities, topics, importance)
                       VALUES (%s, %s, %s, %s, %s, %s) RETURNING id""",
                    (source, raw_text, summary, json.dumps(entities), json.dumps(topics), importance),
                )
                memory_id = cur.fetchone()[0]
            conn.commit()
            return {"memory_id": memory_id, "status": "stored", "summary": summary}
        finally:
            conn.close()

    def get_all_memories(self, limit: int = 50) -> dict:
        """Get all memories, most recent first."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT %s", (limit,)
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            memories = [self._row_to_memory(r) for r in rows]
            return {"memories": memories, "count": len(memories)}
        finally:
            conn.close()

    def get_unconsolidated_memories(self, limit: int = 10) -> dict:
        """Get memories not yet consolidated."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, summary, entities, topics, importance, created_at "
                    "FROM memories WHERE consolidated = FALSE ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]
            memories = [
                {
                    "id": r["id"],
                    "summary": r["summary"],
                    "entities": r["entities"] if isinstance(r["entities"], list) else json.loads(r["entities"]),
                    "topics": r["topics"] if isinstance(r["topics"], list) else json.loads(r["topics"]),
                    "importance": r["importance"],
                    "created_at": str(r["created_at"]),
                }
                for r in rows
            ]
            return {"memories": memories, "count": len(memories)}
        finally:
            conn.close()

    def delete_memory(self, memory_id: int) -> dict:
        """Delete a memory by ID."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memories WHERE id = %s RETURNING id", (memory_id,))
                deleted = cur.fetchone()
            conn.commit()
            if deleted:
                return {"status": "deleted", "memory_id": memory_id}
            return {"status": "not_found", "memory_id": memory_id}
        finally:
            conn.close()

    # ─── Full-Text Search ──────────────────────────────────────

    def search_memories(self, query: str, limit: int = 20) -> dict:
        """Search memories using PostgreSQL full-text search."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                # Use plainto_tsquery for safe user input
                cur.execute(
                    """SELECT * FROM memories
                       WHERE to_tsvector('english', summary || ' ' || source)
                             @@ plainto_tsquery('english', %s)
                       ORDER BY ts_rank(
                           to_tsvector('english', summary || ' ' || source),
                           plainto_tsquery('english', %s)
                       ) DESC
                       LIMIT %s""",
                    (query, query, limit),
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, row)) for row in cur.fetchall()]

            # Fallback to ILIKE if FTS returns nothing
            if not rows:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT * FROM memories WHERE summary ILIKE %s ORDER BY importance DESC LIMIT %s",
                        (f"%{query}%", limit),
                    )
                    columns = [desc[0] for desc in cur.description]
                    rows = [dict(zip(columns, row)) for row in cur.fetchall()]

            memories = [self._row_to_memory(r) for r in rows]
            return {"memories": memories, "count": len(memories)}
        finally:
            conn.close()

    # ─── Consolidations ────────────────────────────────────────

    def store_consolidation(
        self,
        source_ids: list[int],
        summary: str,
        insight: str,
        connections: list[dict],
    ) -> dict:
        """Store consolidation and mark source memories."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO consolidations (source_ids, summary, insight) VALUES (%s, %s, %s)",
                    (json.dumps(source_ids), summary, insight),
                )

                # Update connections
                for conn_item in connections:
                    from_id, to_id = conn_item.get("from_id"), conn_item.get("to_id")
                    rel = conn_item.get("relationship", "")
                    if from_id and to_id:
                        for mid in [from_id, to_id]:
                            cur.execute("SELECT connections FROM memories WHERE id = %s", (mid,))
                            row = cur.fetchone()
                            if row:
                                existing = row[0] if isinstance(row[0], list) else json.loads(row[0])
                                existing.append({
                                    "linked_to": to_id if mid == from_id else from_id,
                                    "relationship": rel,
                                })
                                cur.execute(
                                    "UPDATE memories SET connections = %s WHERE id = %s",
                                    (json.dumps(existing), mid),
                                )

                # Mark consolidated
                if source_ids:
                    cur.execute(
                        "UPDATE memories SET consolidated = TRUE WHERE id = ANY(%s)",
                        (source_ids,),
                    )

            conn.commit()
            return {"status": "consolidated", "memories_processed": len(source_ids), "insight": insight}
        finally:
            conn.close()

    def get_consolidation_history(self, limit: int = 10) -> dict:
        """Get past consolidation insights."""
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT summary, insight, source_ids FROM consolidations ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = cur.fetchall()
            result = [
                {
                    "summary": r[0],
                    "insight": r[1],
                    "source_ids": r[2] if isinstance(r[2], list) else json.loads(r[2]),
                }
                for r in rows
            ]
            return {"consolidations": result, "count": len(result)}
        finally:
            conn.close()

    # ─── Deduplication ─────────────────────────────────────────

    def is_duplicate(self, text_hash: str) -> bool:
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM content_hashes WHERE hash = %s", (text_hash,))
                return cur.fetchone() is not None
        finally:
            conn.close()

    def record_hash(self, text_hash: str) -> None:
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO content_hashes (hash) VALUES (%s) ON CONFLICT DO NOTHING",
                    (text_hash,),
                )
            conn.commit()
        finally:
            conn.close()

    # ─── Stats & Management ────────────────────────────────────

    def get_stats(self) -> dict:
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM memories")
                total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM memories WHERE consolidated = FALSE")
                unconsolidated = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM consolidations")
                consolidations = cur.fetchone()[0]
            return {"total_memories": total, "unconsolidated": unconsolidated, "consolidations": consolidations}
        finally:
            conn.close()

    def clear_all(self, inbox_path: str = None) -> dict:
        from pathlib import Path

        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM memories")
                mem_count = cur.fetchone()[0]
                cur.execute("DELETE FROM memories")
                cur.execute("DELETE FROM consolidations")
                cur.execute("DELETE FROM processed_files")
                cur.execute("DELETE FROM content_hashes")
            conn.commit()
        finally:
            conn.close()

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
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM processed_files WHERE path = %s", (path,))
                return cur.fetchone() is not None
        finally:
            conn.close()

    def mark_file_processed(self, path: str) -> None:
        conn = get_pg_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO processed_files (path) VALUES (%s) ON CONFLICT DO NOTHING",
                    (path,),
                )
            conn.commit()
        finally:
            conn.close()

    # ─── Private ───────────────────────────────────────────────

    @staticmethod
    def _row_to_memory(row: dict) -> dict:
        """Convert a row dict to a memory dict."""
        entities = row.get("entities", [])
        topics = row.get("topics", [])
        connections = row.get("connections", [])

        return {
            "id": row["id"],
            "source": row.get("source", ""),
            "summary": row["summary"],
            "entities": entities if isinstance(entities, list) else json.loads(entities),
            "topics": topics if isinstance(topics, list) else json.loads(topics),
            "importance": row.get("importance", 0.5),
            "connections": connections if isinstance(connections, list) else json.loads(connections),
            "created_at": str(row.get("created_at", "")),
            "consolidated": bool(row.get("consolidated", False)),
        }
