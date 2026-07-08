"""End-to-end RAG pipeline: retrieve -> prompt -> generate -> trace."""

import time
import uuid
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import get_settings
from app.observability.tracing import record_trace
from app.rag import vectorstore

SYSTEM_PROMPT = """You are a careful document Q&A assistant. Answer the user's \
question using ONLY the numbered context excerpts provided below. \
Cite the excerpt number(s) you used in square brackets, e.g. [1] or [1][3]. \
If the excerpts don't contain the answer, say so plainly instead of guessing."""


@lru_cache
def _client() -> genai.Client:
    # Cached rather than constructed per call: genai.Client's Models accessor
    # only keeps a reference to the internal API client, not to this wrapper
    # object, so a throwaway Client() gets garbage-collected (and its __del__
    # closes the underlying HTTP client) before the request actually completes.
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key or None)


def _build_prompt(question: str, sources: list[dict]) -> str:
    if not sources:
        context = "(no documents have been uploaded yet)"
    else:
        context = "\n\n".join(
            f"[{i + 1}] (from {s['document']}):\n{s['text']}"
            for i, s in enumerate(sources)
        )
    return f"Context excerpts:\n\n{context}\n\nQuestion: {question}"


def answer_question(question: str, top_k: int | None = None, kind: str = "query") -> dict:
    settings = get_settings()
    top_k = top_k or settings.top_k
    trace_id = str(uuid.uuid4())

    t0 = time.perf_counter()
    sources = vectorstore.query(question, top_k)
    t1 = time.perf_counter()
    retrieval_ms = (t1 - t0) * 1000

    error = None
    answer = ""
    input_tokens = output_tokens = 0
    generation_ms = 0.0

    try:
        response = _client().models.generate_content(
            model=settings.gemini_model,
            contents=_build_prompt(question, sources),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=1024,
            ),
        )
        t2 = time.perf_counter()
        generation_ms = (t2 - t1) * 1000

        answer = response.text or ""
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count or 0
        output_tokens = usage.candidates_token_count or 0
    except Exception as exc:  # noqa: BLE001 - surfaced to caller & trace log
        error = str(exc)
        t2 = time.perf_counter()
        generation_ms = (t2 - t1) * 1000

    total_ms = retrieval_ms + generation_ms

    trace = record_trace(
        trace_id=trace_id,
        kind=kind,
        question=question,
        answer=answer,
        sources=sources,
        model=settings.gemini_model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        retrieval_ms=retrieval_ms,
        generation_ms=generation_ms,
        total_ms=total_ms,
        error=error,
    )

    if error:
        raise RuntimeError(f"Generation failed: {error}")

    return {
        "trace_id": trace_id,
        "answer": answer,
        "sources": sources,
        "model": settings.gemini_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": trace["cost_usd"],
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "total_ms": total_ms,
    }
