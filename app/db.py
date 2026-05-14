import sqlite3
import os
from pathlib import Path

def _db_path() -> str:
    return os.getenv("DATABASE_PATH", "data/db.sqlite")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('schulleitung', 'lehrer')),
    must_change_password INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS surveys (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    survey_type TEXT NOT NULL CHECK(survey_type IN ('eltern_kl4', 'kinder_kl4')),
    questionnaire_id TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('draft','active','closed')),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classes (
    id INTEGER PRIMARY KEY,
    survey_id INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    UNIQUE(survey_id, name)
);

CREATE TABLE IF NOT EXISTS tans (
    id INTEGER PRIMARY KEY,
    code TEXT UNIQUE NOT NULL,
    class_id INTEGER NOT NULL REFERENCES classes(id),
    survey_id INTEGER NOT NULL REFERENCES surveys(id),
    used_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS responses (
    id INTEGER PRIMARY KEY,
    survey_id INTEGER NOT NULL REFERENCES surveys(id),
    class_name TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_responses_survey ON responses(survey_id);
CREATE INDEX IF NOT EXISTS idx_responses_class ON responses(class_name);
CREATE INDEX IF NOT EXISTS idx_tans_code ON tans(code);
"""


def get_db() -> sqlite3.Connection:
    path = _db_path()
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = get_db()
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    migrate_db()


def migrate_db() -> None:
    """Idempotent schema migrations for existing databases."""
    conn = get_db()
    try:
        # 1. Allow 'lehrer' role: rebuild users table if constraint is outdated
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone()
        if row and "lehrer" not in row["sql"]:
            conn.executescript("""
                CREATE TABLE users_new (
                    id INTEGER PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('schulleitung', 'lehrer')),
                    must_change_password INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL
                );
                INSERT INTO users_new SELECT * FROM users;
                DROP TABLE users;
                ALTER TABLE users_new RENAME TO users;
            """)
            conn.commit()

        # 2. Add share_token to surveys (nullable, unique)
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(surveys)")]
        if "share_token" not in cols:
            conn.execute("ALTER TABLE surveys ADD COLUMN share_token TEXT")
            conn.commit()
    finally:
        conn.close()
