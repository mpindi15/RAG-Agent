"""End-to-end RAG pipeline: retrieve -> prompt -> generate -> trace."""

import time
import uuid
from collections.abc import Iterator
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

NO_DOCUMENTS_MESSAGE = "No documents have been uploaded yet. Upload one in the Documents tab, then ask again."


class GenerationError(RuntimeError):
    """Raised when retrieval succeeded but generation failed. Carries the
    retrieved sources so callers (e.g. eval scoring) can still judge
    retrieval quality independently of the generation failure, instead of
    conflating the two."""

    def __init__(self, message: str, sources: list[dict]):
        super().__init__(message)
        self.sources = sources


@lru_cache
def _client() -> genai.Client:
    # Cached rather than constructed per call: genai.Client's Models accessor
    # only keeps a reference to the internal API client, not to this wrapper
    # object, so a throwaway Client() gets garbage-collected (and its __del__
    # closes the underlying HTTP client) before the request actually completes.
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key or None)


def _generation_config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=1024,
        # Gemini 2.5+ models think by default, and thinking tokens are drawn
        # from the same max_output_tokens budget as the visible answer — left
        # enabled, a 1024-token budget can be almost entirely consumed by
        # thinking, cutting the actual answer off mid-sentence
        # (finish_reason: MAX_TOKENS with ~30 visible tokens, empirically).
        # This task is contextual extraction, not multi-step reasoning, so
        # thinking buys nothing here; disabling it also uses fewer tokens per
        # request, which helps against free-tier rate limits.
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )


def _build_prompt(question: str, sources: list[dict]) -> str:
    context = "\n\n".join(
        f"[{i + 1}] (from {s['document']}):\n{s['text']}" for i, s in enumerate(sources)
    )
    return f"Context excerpts:\n\n{context}\n\nQuestion: {question}"


def _retrieve(question: str, top_k: int | None) -> tuple[list[dict], float]:
    settings = get_settings()
    top_k = top_k or settings.top_k
    t0 = time.perf_counter()
    sources = vectorstore.query(question, top_k)
    retrieval_ms = (time.perf_counter() - t0) * 1000
    return sources, retrieval_ms


def answer_question(question: str, top_k: int | None = None, kind: str = "query") -> dict:
    settings = get_settings()
    trace_id = str(uuid.uuid4())

    sources, retrieval_ms = _retrieve(question, top_k)

    if not vectorstore.has_documents():
        total_ms = retrieval_ms
        trace = record_trace(
            trace_id=trace_id,
            kind=kind,
            question=question,
            answer=NO_DOCUMENTS_MESSAGE,
            sources=sources,
            model=settings.gemini_model,
            input_tokens=0,
            output_tokens=0,
            retrieval_ms=retrieval_ms,
            generation_ms=0.0,
            total_ms=total_ms,
            error=None,
        )
        return {
            "trace_id": trace_id,
            "answer": NO_DOCUMENTS_MESSAGE,
            "sources": sources,
            "model": settings.gemini_model,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": trace["cost_usd"],
            "retrieval_ms": retrieval_ms,
            "generation_ms": 0.0,
            "total_ms": total_ms,
        }

    error = None
    answer = ""
    input_tokens = output_tokens = 0
    generation_ms = 0.0

    t1 = time.perf_counter()
    try:
        response = _client().models.generate_content(
            model=settings.gemini_model,
            contents=_build_prompt(question, sources),
            config=_generation_config(),
        )
        generation_ms = (time.perf_counter() - t1) * 1000

        answer = response.text or ""
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count or 0
        output_tokens = usage.candidates_token_count or 0
    except Exception as exc:  # noqa: BLE001 - surfaced to caller & trace log
        error = str(exc)
        generation_ms = (time.perf_counter() - t1) * 1000

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
        raise GenerationError(f"Generation failed: {error}", sources)

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


def stream_answer_question(question: str, top_k: int | None = None, kind: str = "query") -> Iterator[dict]:
    """Generator version of answer_question for the Chat UI's SSE endpoint.

    Yields envelope dicts: {"type": "sources", ...}, {"type": "delta", ...},
    {"type": "done", ...} on success, or {"type": "error", ...}. Errors are
    yielded rather than raised because by the time generation fails we may
    already have streamed partial text to the client — there's no clean way
    to turn that into an HTTP error response at that point.
    """
    settings = get_settings()
    trace_id = str(uuid.uuid4())

    sources, retrieval_ms = _retrieve(question, top_k)
    yield {"type": "sources", "sources": sources}

    if not vectorstore.has_documents():
        total_ms = retrieval_ms
        trace = record_trace(
            trace_id=trace_id,
            kind=kind,
            question=question,
            answer=NO_DOCUMENTS_MESSAGE,
            sources=sources,
            model=settings.gemini_model,
            input_tokens=0,
            output_tokens=0,
            retrieval_ms=retrieval_ms,
            generation_ms=0.0,
            total_ms=total_ms,
            error=None,
        )
        yield {"type": "delta", "text": NO_DOCUMENTS_MESSAGE}
        yield {
            "type": "done",
            "trace_id": trace_id,
            "model": settings.gemini_model,
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": trace["cost_usd"],
            "retrieval_ms": retrieval_ms,
            "generation_ms": 0.0,
            "total_ms": total_ms,
        }
        return

    answer_parts: list[str] = []
    input_tokens = output_tokens = 0
    error = None
    t1 = time.perf_counter()
    try:
        stream = _client().models.generate_content_stream(
            model=settings.gemini_model,
            contents=_build_prompt(question, sources),
            config=_generation_config(),
        )
        for chunk in stream:
            if chunk.text:
                answer_parts.append(chunk.text)
                yield {"type": "delta", "text": chunk.text}
            if chunk.usage_metadata is not None:
                usage = chunk.usage_metadata
                if usage.prompt_token_count is not None:
                    input_tokens = usage.prompt_token_count
                if usage.candidates_token_count is not None:
                    output_tokens = usage.candidates_token_count
    except Exception as exc:  # noqa: BLE001 - surfaced to caller & trace log
        error = str(exc)
    generation_ms = (time.perf_counter() - t1) * 1000

    answer = "".join(answer_parts)
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
        yield {"type": "error", "detail": f"Generation failed: {error}"}
        return

    yield {
        "type": "done",
        "trace_id": trace_id,
        "model": settings.gemini_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": trace["cost_usd"],
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "total_ms": total_ms,
    }
