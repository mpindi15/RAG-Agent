"""Structured trace logging for every RAG call.

Every query (interactive or eval) is persisted to SQLite with latency,
token usage, and an estimated dollar cost. This is the raw data the
Monitoring and Traces tabs read from.
"""

import json
from datetime import datetime, timezone

from app.db import get_conn

# USD per 1M tokens (input, output), paid-tier rates. Approximate, for
# observability/demo purposes only — check ai.google.dev/gemini-api/docs/pricing
# for current rates. The Gemini API's free tier bills these calls at $0; this
# table exists so the Monitoring/Eval tabs still demonstrate cost accounting
# the way they would against a paid deployment.
PRICING_PER_MTOK = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
}
DEFAULT_PRICING = (0.30, 2.50)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = PRICING_PER_MTOK.get(model, DEFAULT_PRICING)
    return round((input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price, 6)


def record_trace(
    trace_id: str,
    kind: str,
    question: str,
    answer: str,
    sources: list[dict],
    model: str,
    input_tokens: int,
    output_tokens: int,
    retrieval_ms: float,
    generation_ms: float,
    total_ms: float,
    error: str | None = None,
) -> dict:
    cost_usd = estimate_cost(model, input_tokens, output_tokens)
    created_at = datetime.now(timezone.utc).isoformat()

    slim_sources = [
        {"document": s["document"], "chunk_id": s["chunk_id"], "score": s["score"]}
        for s in sources
    ]

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO traces (
                id, created_at, kind, question, answer, sources, model,
                input_tokens, output_tokens, cost_usd,
                retrieval_ms, generation_ms, total_ms, error
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trace_id,
                created_at,
                kind,
                question,
                answer,
                json.dumps(slim_sources),
                model,
                input_tokens,
                output_tokens,
                cost_usd,
                retrieval_ms,
                generation_ms,
                total_ms,
                error,
            ),
        )

    return {
        "trace_id": trace_id,
        "created_at": created_at,
        "cost_usd": cost_usd,
    }
