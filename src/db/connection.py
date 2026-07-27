"""
Database connection and schema management.
"""

import sqlite3
from pathlib import Path

from src.config import get_settings

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    entities TEXT NOT NULL DEFAULT '[]',
    topics TEXT NOT NULL DEFAULT '[]',
    connections TEXT NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS consolidations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_ids TEXT NOT NULL,
    summary TEXT NOT NULL,
    insight TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS processed_files (
    path TEXT PRIMARY KEY,
    processed_at TEXT NOT NULL
);
"""


def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    settings = get_settings()
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    return db


def init_db() -> None:
    """Initialize the database schema."""
    db = get_db()
    db.executescript(SCHEMA_SQL)
    db.close()
