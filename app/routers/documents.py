import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from app.config import get_settings
from app.db import get_conn
from app.models import DocumentInfo
from app.rag import vectorstore
from app.rag.chunking import chunk_text
from app.rag.loaders import SUPPORTED_EXTENSIONS, UnsupportedFileTypeError, load_text

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentInfo)
async def upload_document(file: UploadFile) -> DocumentInfo:
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}",
        )

    document_id = str(uuid.uuid4())
    dest = Path(settings.uploads_dir) / f"{document_id}{suffix}"
    content = await file.read()
    dest.write_bytes(content)

    try:
        text = load_text(dest)
    except UnsupportedFileTypeError as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not text.strip():
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="No extractable text found in file.")

    chunks = chunk_text(text, settings.chunk_size, settings.chunk_overlap)
    vectorstore.add_chunks(document_id, file.filename or dest.name, chunks)

    uploaded_at = datetime.now(timezone.utc).isoformat()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO documents (id, filename, uploaded_at, size_bytes, num_chunks) "
            "VALUES (?, ?, ?, ?, ?)",
            (document_id, file.filename or dest.name, uploaded_at, len(content), len(chunks)),
        )

    return DocumentInfo(
        id=document_id,
        filename=file.filename or dest.name,
        uploaded_at=uploaded_at,
        size_bytes=len(content),
        num_chunks=len(chunks),
    )


@router.get("", response_model=list[DocumentInfo])
def list_documents() -> list[DocumentInfo]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM documents ORDER BY uploaded_at DESC").fetchall()
    return [DocumentInfo(**dict(r)) for r in rows]


@router.delete("/{document_id}")
def delete_document(document_id: str) -> dict:
    settings = get_settings()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    vectorstore.delete_document(document_id)

    for p in Path(settings.uploads_dir).glob(f"{document_id}.*"):
        p.unlink(missing_ok=True)

    return {"status": "deleted", "id": document_id}
