from typing import Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = None


class SourceChunk(BaseModel):
    document: str
    chunk_id: str
    score: float
    text: str


class QueryResponse(BaseModel):
    trace_id: str
    answer: str
    sources: list[SourceChunk]
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    retrieval_ms: float
    generation_ms: float
    total_ms: float


class DocumentInfo(BaseModel):
    id: str
    filename: str
    uploaded_at: str
    size_bytes: int
    num_chunks: int
