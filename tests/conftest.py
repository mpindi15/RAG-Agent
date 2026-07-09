import pytest

from app.config import get_settings
from app.db import init_db


@pytest.fixture(autouse=True)
def isolate_data_dir(tmp_path, monkeypatch):
    """Every test gets its own scratch data dir so tests never touch (or are
    affected by) the real ./data used during manual runs."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()
