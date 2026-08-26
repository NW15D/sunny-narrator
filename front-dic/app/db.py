import sqlite3
from contextlib import contextmanager

from app.config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    login TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    email_verified_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    series_name TEXT,
    series_index INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dictionary_files (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(id),
    uploader_id TEXT NOT NULL REFERENCES users(id),
    source_lang TEXT NOT NULL,
    target_lang TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    entries_count INTEGER NOT NULL,
    description TEXT,
    downloads_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'approved',
    uploaded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dict_langs ON dictionary_files(source_lang, target_lang);
CREATE INDEX IF NOT EXISTS idx_dict_book ON dictionary_files(book_id);
CREATE INDEX IF NOT EXISTS idx_dict_uploader ON dictionary_files(uploader_id);

CREATE TABLE IF NOT EXISTS email_verifications (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    code_hash TEXT NOT NULL,
    purpose TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL допускает параллельные читатели во время записи, busy_timeout не
    # даёт сразу падать с "database is locked" под конкурентной нагрузкой
    # (эндпоинты — обычные def, FastAPI гоняет их в threadpool одного
    # процесса, так что конкурентность внутри SQLite реальна уже при
    # --workers 1).
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
