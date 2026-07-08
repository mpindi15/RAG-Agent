from fastapi import APIRouter, HTTPException

from app.models import QueryRequest, QueryResponse
from app.rag.pipeline import answer_question

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
