"""
PostgreSQL database connection and schema management.

Used when DATABASE_URL is set to a PostgreSQL connection string.
Requires: pip install psycopg2-binary
"""

import logging

import psycopg2
import psycopg2.extras

from src.config import get_settings

log = logging.getLogger("memory-agent")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memories (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL DEFAULT '',
    raw_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    entities JSONB NOT NULL DEFAULT '[]',
    topics JSONB NOT NULL DEFAULT '[]',
    connections JSONB NOT NULL DEFAULT '[]',
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    consolidated BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS consolidations (
    id SERIAL PRIMARY KEY,
    source_ids JSONB NOT NULL,
    summary TEXT NOT NULL,
    insight TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS processed_files (
    path TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_hashes (
    hash TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Full-text search index
CREATE INDEX IF NOT EXISTS idx_memories_fts
    ON memories USING GIN (to_tsvector('english', summary || ' ' || source));
"""


def get_pg_connection():
    """Get a PostgreSQL connection."""
    settings = get_settings()
    conn = psycopg2.connect(settings.database_url)
    conn.autocommit = False
    return conn


def init_pg_db() -> None:
    """Initialize the PostgreSQL schema."""
    conn = get_pg_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()
        log.info("📦 PostgreSQL schema initialized")
    finally:
        conn.close()
