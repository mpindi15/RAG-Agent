import sqlite3
from contextlib import contextmanager

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    num_chunks INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 'query' | 'eval'
    question TEXT NOT NULL,
    answer TEXT,
    sources TEXT,                    -- JSON list of {document, chunk_id, score}
    model TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    retrieval_ms REAL,
    generation_ms REAL,
    total_ms REAL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_traces_created_at ON traces(created_at);
"""


@contextmanager
def get_conn():
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(SCHEMA)
