from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


def test_index_serves_html():
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "RAG Agent" in res.text


def test_documents_list_starts_empty():
    with TestClient(app) as client:
        res = client.get("/api/documents")
        assert res.status_code == 200
        assert res.json() == []


def test_metrics_summary_on_empty_db():
    with TestClient(app) as client:
        res = client.get("/api/metrics/summary")
        assert res.status_code == 200
        body = res.json()
        assert body["total_queries"] == 0
        assert body["error_rate"] == 0.0


def test_upload_rejects_unsupported_extension():
    with TestClient(app) as client:
        res = client.post(
            "/api/documents/upload",
            files={"file": ("notes.exe", b"binary junk", "application/octet-stream")},
        )
        assert res.status_code == 400
