"""Thin wrapper around a persistent Chroma collection.

Uses Chroma's bundled default embedding function (a small ONNX MiniLM model,
downloaded once on first use) so the project needs no separate embeddings
API key and no heavyweight ML framework — good enough for a demo-scale RAG
corpus and keeps the Docker image small.
"""

from functools import lru_cache

import chromadb

from app.config import get_settings

COLLECTION_NAME = "documents"


@lru_cache
def get_collection():
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def add_chunks(document_id: str, filename: str, chunks: list[str]) -> None:
    if not chunks:
        return
    collection = get_collection()
    ids = [f"{document_id}::{i}" for i in range(len(chunks))]
    metadatas = [
        {"document_id": document_id, "filename": filename, "chunk_index": i}
        for i in range(len(chunks))
    ]
    collection.add(ids=ids, documents=chunks, metadatas=metadatas)


def query(question: str, top_k: int) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    top_k = min(top_k, collection.count())
    result = collection.query(query_texts=[question], n_results=top_k)

    hits = []
    docs = result.get("documents", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    dists = result.get("distances", [[]])[0]
    ids = result.get("ids", [[]])[0]
    for doc_text, meta, dist, chunk_id in zip(docs, metas, dists, ids):
        # Chroma returns squared-L2 distance by default; convert to a
        # similarity-ish score in (0, 1] for display purposes.
        score = 1.0 / (1.0 + dist)
        hits.append(
            {
                "chunk_id": chunk_id,
                "document": meta.get("filename", "unknown"),
                "document_id": meta.get("document_id"),
                "text": doc_text,
                "score": round(score, 4),
            }
        )
    return hits


def delete_document(document_id: str) -> None:
    collection = get_collection()
    collection.delete(where={"document_id": document_id})


def reset() -> None:
    """Used by tests / eval seeding to start from an empty collection."""
    settings = get_settings()
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass
    get_collection.cache_clear()
