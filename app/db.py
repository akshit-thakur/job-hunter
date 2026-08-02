import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path


DEFAULT_DATABASE_PATH = "./db/job_tracker.db"
# Increment when the base schema changes in a way that requires migration.
SCHEMA_VERSION = "1"
IST = timezone(timedelta(hours=5, minutes=30))


def database_path() -> str:
    return os.getenv("DATABASE_PATH", DEFAULT_DATABASE_PATH)


def get_connection() -> sqlite3.Connection:
    path = Path(database_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    # WAL mode improves read/write concurrency and provides atomic crash recovery.
    conn.execute("PRAGMA journal_mode=WAL")
    # NORMAL sync is safe with WAL: commits are atomic without full-fsync per write.
    conn.execute("PRAGMA synchronous=NORMAL")
    # Wait up to 5 s when a lock is held before raising OperationalError.
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_metadata(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    row = conn.execute(
        "SELECT value FROM app_metadata WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, ?)",
            ("schema_version", SCHEMA_VERSION, datetime.now(IST).isoformat()),
        )
        conn.commit()
    elif row[0] != SCHEMA_VERSION:
        raise RuntimeError(
            f"Database schema_version {row[0]!r} does not match "
            f"expected {SCHEMA_VERSION!r}. Manual migration required."
        )


def init_db() -> None:
    from app.migrations import run_migrations

    with closing(get_connection()) as conn:
        _ensure_metadata(conn)
        run_migrations(conn)
