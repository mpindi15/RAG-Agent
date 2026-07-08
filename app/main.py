import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import documents, metrics, query
from app.routers import eval as eval_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()  # also ensures data dirs exist
    init_db()
    yield


app = FastAPI(title="RAG Agent", version="1.0.0", lifespan=lifespan)

app.include_router(documents.router)
app.include_router(query.router)
app.include_router(metrics.router)
app.include_router(eval_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse("static/index.html")
