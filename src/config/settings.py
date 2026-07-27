"""
Application settings with environment variable support.

All configuration is centralized here. Values come from:
1. Environment variables
2. .env file (via python-dotenv)
3. Defaults defined below
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Immutable application configuration."""

    # ─── AWS / Bedrock ─────────────────────────────────────────
    bedrock_model_id: str = field(
        default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
    )
    aws_region: str = field(
        default_factory=lambda: os.getenv("AWS_REGION", "us-east-1")
    )
    max_tokens: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOKENS", "2048"))
    )
    max_tool_rounds: int = field(
        default_factory=lambda: int(os.getenv("MAX_TOOL_ROUNDS", "5"))
    )

    # ─── Database ──────────────────────────────────────────────
    db_path: str = field(
        default_factory=lambda: os.getenv("MEMORY_DB", "data/memory.db")
    )
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "")
    )

    @property
    def use_postgres(self) -> bool:
        """True if a PostgreSQL DATABASE_URL is configured."""
        return self.database_url.startswith("postgresql")

    # ─── Server ────────────────────────────────────────────────
    host: str = field(
        default_factory=lambda: os.getenv("HOST", "0.0.0.0")
    )
    port: int = field(
        default_factory=lambda: int(os.getenv("PORT", "8888"))
    )

    # ─── File Watcher ──────────────────────────────────────────
    watch_dir: str = field(
        default_factory=lambda: os.getenv("WATCH_DIR", "./inbox")
    )
    watch_poll_interval: int = field(
        default_factory=lambda: int(os.getenv("WATCH_POLL_INTERVAL", "5"))
    )

    # ─── Consolidation ─────────────────────────────────────────
    consolidate_interval_minutes: int = field(
        default_factory=lambda: int(os.getenv("CONSOLIDATE_INTERVAL", "30"))
    )
    consolidate_min_memories: int = field(
        default_factory=lambda: int(os.getenv("CONSOLIDATE_MIN_MEMORIES", "2"))
    )

    # ─── File Size Limits ──────────────────────────────────────
    max_text_chars: int = field(
        default_factory=lambda: int(os.getenv("MAX_TEXT_CHARS", "10000"))
    )
    max_image_mb: float = field(
        default_factory=lambda: float(os.getenv("MAX_IMAGE_MB", "5.0"))
    )
    max_document_mb: float = field(
        default_factory=lambda: float(os.getenv("MAX_DOCUMENT_MB", "5.0"))
    )

    # ─── Dashboard ─────────────────────────────────────────────
    agent_url: str = field(
        default_factory=lambda: os.getenv("AGENT_URL", "http://localhost:8888")
    )

    @property
    def watch_path(self) -> Path:
        return Path(self.watch_dir)

    @property
    def db_file(self) -> Path:
        return Path(self.db_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings (singleton)."""
    return Settings()
