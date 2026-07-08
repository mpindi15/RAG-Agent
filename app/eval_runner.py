"""LLM-as-judge evaluation harness.

Runs a fixed set of gold Q&A pairs through the RAG pipeline, then asks Gemini
to grade each answer against the expected answer (faithfulness + correctness,
1-5) using structured output so scores are always machine-parseable. Also
checks a cheap retrieval signal: did the expected source document show up in
the retrieved chunks at all.
"""

import json
import time
import uuid
from pathlib import Path

from app.config import get_settings
from app.rag.pipeline import GenerationError, _client, answer_question

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "description": "1 (wrong/unsupported) to 5 (fully correct and grounded)"},
        "reasoning": {"type": "string", "description": "One or two sentences explaining the score"},
    },
    "required": ["score", "reasoning"],
}


def _judge(question: str, expected_answer: str, actual_answer: str) -> dict:
    settings = get_settings()
    client = _client()
    prompt = (
        "You are grading a RAG system's answer against a reference answer.\n\n"
        f"Question: {question}\n\n"
        f"Reference answer: {expected_answer}\n\n"
        f"System's answer: {actual_answer}\n\n"
        "Score how well the system's answer matches the reference in factual content "
        "(wording may differ). 5 = fully correct and grounded, 3 = partially correct "
        "or missing detail, 1 = wrong or fabricated."
    )
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config={
            "max_output_tokens": 300,
            "response_mime_type": "application/json",
            "response_json_schema": JUDGE_SCHEMA,
        },
    )
    return json.loads(response.text)


def run_eval(eval_set_path: str | Path) -> dict:
    eval_set_path = Path(eval_set_path)
    cases = json.loads(eval_set_path.read_text(encoding="utf-8"))

    results = []
    for i, case in enumerate(cases):
        if i > 0:
            # Each case makes two API calls (generation + judge) back to back;
            # a short gap keeps a 5-case run under free-tier per-minute limits.
            time.sleep(1.5)
        t0 = time.perf_counter()
        try:
            outcome = answer_question(case["question"], kind="eval")
            error = None
        except RuntimeError as exc:
            # GenerationError (raised when retrieval succeeded but generation
            # didn't) carries the real retrieved sources; a bare RuntimeError
            # (e.g. from some other failure) won't, so fall back to [].
            outcome = {
                "answer": "",
                "sources": getattr(exc, "sources", []) if isinstance(exc, GenerationError) else [],
                "trace_id": str(uuid.uuid4()),
                "model": get_settings().gemini_model,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "total_ms": (time.perf_counter() - t0) * 1000,
            }
            error = str(exc)

        expected_source = case.get("expected_source")
        retrieved_docs = {s["document"] for s in outcome["sources"]}
        retrieval_hit = expected_source is None or expected_source in retrieved_docs

        judge = {"score": 0, "reasoning": "skipped (generation failed)"}
        if not error:
            try:
                judge = _judge(case["question"], case["expected_answer"], outcome["answer"])
            except Exception as exc:  # noqa: BLE001
                judge = {"score": 0, "reasoning": f"judge call failed: {exc}"}

        results.append(
            {
                "question": case["question"],
                "expected_answer": case["expected_answer"],
                "actual_answer": outcome["answer"],
                "retrieval_hit": retrieval_hit,
                "score": judge["score"],
                "judge_reasoning": judge["reasoning"],
                "latency_ms": round(outcome["total_ms"], 1),
                "sources": sorted(retrieved_docs),
                "error": error,
            }
        )
        # Note: no record_trace() call here — answer_question() (called with
        # kind="eval" above) already records the trace itself, on both the
        # success and RuntimeError paths. Recording it again with the same
        # trace_id violates the traces.id primary key.

    error_count = sum(1 for r in results if r["error"])
    report = {
        "num_cases": len(results),
        "error_count": error_count,
        # Averaged over ALL cases, not just the ones that got a real score —
        # a generation/judge failure counts as 0, not "not counted". Otherwise
        # a run where 4/5 cases errored out can still report avg_score: 5.0,
        # which is actively misleading about system health.
        "avg_score": round(sum(r["score"] for r in results) / len(results), 2) if results else 0.0,
        "retrieval_hit_rate": round(sum(r["retrieval_hit"] for r in results) / len(results), 2)
        if results
        else 0.0,
        "pass_rate_at_4": round(sum(1 for r in results if r["score"] >= 4) / len(results), 2)
        if results
        else 0.0,
        "avg_latency_ms": round(sum(r["latency_ms"] for r in results) / len(results), 1)
        if results
        else 0.0,
        "results": results,
    }
    return report
