from src.db.connection import get_db, init_db
from src.db.repository import MemoryRepository


def get_repository():
    """
    Factory that returns the correct repository based on config.

    - If DATABASE_URL is set (starts with 'postgresql'): uses PostgreSQL
    - Otherwise: uses SQLite (default)
    """
    from src.config import get_settings
    settings = get_settings()

    if settings.use_postgres:
        from src.db.pg_repository import PostgresRepository
        return PostgresRepository()
    else:
        return MemoryRepository()


def init_database() -> None:
    """Initialize the correct database based on config."""
    from src.config import get_settings
    settings = get_settings()

    if settings.use_postgres:
        from src.db.postgres import init_pg_db
        init_pg_db()
    else:
        init_db()


__all__ = ["get_db", "init_db", "init_database", "get_repository", "MemoryRepository"]
