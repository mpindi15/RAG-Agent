from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    chunk_size: int = 1000
    chunk_overlap: int = 150
    top_k: int = 4

    data_dir: str = "./data"
    chroma_dir: str = "./data/chroma"
    uploads_dir: str = "./data/uploads"
    sqlite_path: str = "./data/app.db"

    app_host: str = "0.0.0.0"
    app_port: int = 8000

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.chroma_dir, self.uploads_dir):
            Path(d).mkdir(parents=True, exist_ok=True)
        Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
