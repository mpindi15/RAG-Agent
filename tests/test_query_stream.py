from fastapi.testclient import TestClient

from app.main import app


def test_stream_endpoint_shape_with_no_documents():
    """Exercises the full HTTP path for /api/query/stream without touching
    the network — the vector store is empty in this test's isolated data
    dir, so the pipeline short-circuits before calling Gemini."""
    with TestClient(app) as client:
        res = client.post("/api/query/stream", json={"question": "anything"})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

        body = res.text
        assert "event: sources" in body
        assert "event: delta" in body
        assert "event: done" in body
        assert "No documents have been uploaded yet" in body


def test_stream_endpoint_rejects_empty_question():
    with TestClient(app) as client:
        res = client.post("/api/query/stream", json={"question": "   "})
        assert res.status_code == 400
