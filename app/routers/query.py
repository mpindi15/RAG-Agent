import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.models import QueryRequest, QueryResponse
from app.rag.pipeline import answer_question, stream_answer_question

router = APIRouter(prefix="/api/query", tags=["query"])


@router.post("", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")
    try:
        result = answer_question(request.question, top_k=request.top_k, kind="query")
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return QueryResponse(**result)


def _sse_encode(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.post("/stream")
def query_stream(request: QueryRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    def event_source():
        try:
            for event in stream_answer_question(request.question, top_k=request.top_k, kind="query"):
                yield _sse_encode(event)
        except Exception as exc:  # noqa: BLE001 - last-resort guard so the stream ends cleanly
            yield _sse_encode({"type": "error", "detail": str(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
