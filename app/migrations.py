from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


IST = timezone(timedelta(hours=5, minutes=30))


# Ordered list of (name, sql). Names must sort in application order.
# Each entry is one SQL statement. Multi-statement migrations require a
# custom apply function — do not add semicolons to split statements here.
MIGRATIONS: list[tuple[str, str]] = [
    (
        "001_create_applications",
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY,
            company TEXT NOT NULL,
            role_title TEXT NOT NULL,
            location TEXT,
            work_mode TEXT DEFAULT 'unknown',
            source TEXT DEFAULT 'other',
            jd_url TEXT,
            salary_min REAL,
            salary_max REAL,
            status TEXT DEFAULT 'saved',
            resume_version TEXT,
            applied_date TEXT,
            follow_up_date TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "002_idx_applications_follow_up_date",
        "CREATE INDEX IF NOT EXISTS idx_applications_follow_up_date ON applications (follow_up_date)",
    ),
    (
        "003_idx_applications_status",
        "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications (status)",
    ),
    (
        "004_idx_applications_source",
        "CREATE INDEX IF NOT EXISTS idx_applications_source ON applications (source)",
    ),
    (
        "005_idx_applications_work_mode",
        "CREATE INDEX IF NOT EXISTS idx_applications_work_mode ON applications (work_mode)",
    ),
    (
        "006_idx_applications_applied_date",
        "CREATE INDEX IF NOT EXISTS idx_applications_applied_date ON applications (applied_date)",
    ),
    (
        "007_create_resumes",
        """
        CREATE TABLE IF NOT EXISTS resumes (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            notes TEXT,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    ),
    (
        "008_create_application_events",
        """
        CREATE TABLE IF NOT EXISTS application_events (
            id INTEGER PRIMARY KEY,
            application_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            note TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "009_idx_application_events_application_id",
        "CREATE INDEX IF NOT EXISTS idx_application_events_application_id ON application_events (application_id, occurred_at DESC)",
    ),
    (
        "010_idx_application_events_event_type",
        "CREATE INDEX IF NOT EXISTS idx_application_events_event_type ON application_events (event_type, occurred_at DESC)",
    ),
    (
        "011_create_application_images",
        """
        CREATE TABLE IF NOT EXISTS application_images (
            id INTEGER PRIMARY KEY,
            application_id INTEGER NOT NULL,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL UNIQUE,
            content_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            caption TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (application_id) REFERENCES applications (id) ON DELETE CASCADE
        )
        """,
    ),
    (
        "012_idx_application_images_application_id",
        "CREATE INDEX IF NOT EXISTS idx_application_images_application_id ON application_images (application_id, created_at DESC)",
    ),
    (
        "013_add_application_job_description",
        "ALTER TABLE applications ADD COLUMN job_description TEXT",
    ),
    (
        "014_drop_application_resume_version",
        "ALTER TABLE applications DROP COLUMN resume_version",
    ),
    (
        "015_drop_resumes",
        "DROP TABLE IF EXISTS resumes",
    ),
    (
        "016_drop_applications_follow_up_date_index",
        "DROP INDEX IF EXISTS idx_applications_follow_up_date",
    ),
    (
        "017_drop_application_follow_up_date",
        "ALTER TABLE applications DROP COLUMN follow_up_date",
    ),
]


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    conn.commit()


def _applied_migrations(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM migrations").fetchall()}


def _apply_migration(conn: sqlite3.Connection, name: str, sql: str) -> None:
    """Apply one migration and record it. Rolls back the record on failure."""
    try:
        conn.execute(sql.strip())
        conn.execute(
            "INSERT INTO migrations (name, applied_at) VALUES (?, ?)",
            (name, datetime.now(IST).isoformat()),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise RuntimeError(f"Migration {name!r} failed: {exc}") from exc


def run_migrations(conn: sqlite3.Connection) -> None:
    _ensure_migrations_table(conn)
    applied = _applied_migrations(conn)
    for name, sql in sorted(MIGRATIONS, key=lambda m: m[0]):
        if name not in applied:
            _apply_migration(conn, name, sql)
