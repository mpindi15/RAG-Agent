from fastapi import APIRouter, Query

from app.observability import metrics

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/summary")
def get_summary() -> dict:
    return metrics.summary()


@router.get("/timeseries")
def get_timeseries(hours: int = Query(24, ge=1, le=24 * 30)) -> list[dict]:
    return metrics.queries_over_time(hours=hours)


@router.get("/traces")
def get_traces(
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kind: str | None = Query(None, pattern="^(query|eval)$"),
) -> dict:
    return metrics.recent_traces(limit=limit, offset=offset, kind=kind)
