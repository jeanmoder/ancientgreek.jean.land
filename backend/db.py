from datetime import datetime, timezone

import aiosqlite

from backend.config import get_settings

DATABASE_PATH = get_settings().DATABASE_PATH

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Return the shared database connection, creating it if needed."""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DATABASE_PATH)
        _db.row_factory = aiosqlite.Row
    return _db


async def init_db() -> None:
    """Create tables if they don't exist."""
    db = await get_db()
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key TEXT PRIMARY KEY,
            value TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    await db.execute(
        "DROP INDEX IF EXISTS idx_chat_session"
    )
    await db.execute("DROP TABLE IF EXISTS chat_history")
    await db.commit()


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


async def get_cache(key: str) -> str | None:
    """Retrieve a cached value by key, or None if not found."""
    db = await get_db()
    cursor = await db.execute("SELECT value FROM cache WHERE key = ?", (key,))
    row = await cursor.fetchone()
    if row is None:
        return None
    return row[0]


async def set_cache(key: str, value: str) -> None:
    """Insert or replace a cache entry."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO cache (key, value, created_at) VALUES (?, ?, ?)",
        (key, value, now),
    )
    await db.commit()
