"""Ingest sample_docs/ into the vector store + documents table directly,
bypassing HTTP — handy for local eval runs and CI.

Usage: python -m eval.seed_sample_docs
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.db import get_conn, init_db
from app.rag import vectorstore
from app.rag.chunking import chunk_text
from app.rag.loaders import load_text

SAMPLE_DOCS_DIR = Path("sample_docs")


def seed() -> None:
    settings = get_settings()
    init_db()

    for path in sorted(SAMPLE_DOCS_DIR.glob("*")):
        if path.suffix.lower() not in {".pdf", ".docx", ".txt", ".md"}:
            continue

        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM documents WHERE filename = ?", (path.name,)
            ).fetchone()
        if existing:
            print(f"skip (already seeded): {path.name}")
            continue

        text = load_text(path)
        chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
        document_id = str(uuid.uuid4())
        vectorstore.add_chunks(document_id, path.name, chunks)

        with get_conn() as conn:
            conn.execute(
                "INSERT INTO documents (id, filename, uploaded_at, size_bytes, num_chunks) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    document_id,
                    path.name,
                    datetime.now(timezone.utc).isoformat(),
                    path.stat().st_size,
                    len(chunks),
                ),
            )
        print(f"seeded: {path.name} ({len(chunks)} chunks)")


if __name__ == "__main__":
    seed()
