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
from app.observability.tracing import record_trace
from app.rag.pipeline import _client, answer_question

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
    for case in cases:
        t0 = time.perf_counter()
        try:
            outcome = answer_question(case["question"], kind="eval")
            error = None
        except RuntimeError as exc:
            outcome = {
                "answer": "",
                "sources": [],
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

        record_trace(
            trace_id=outcome["trace_id"],
            kind="eval",
            question=case["question"],
            answer=outcome["answer"],
            sources=outcome["sources"],
            model=outcome["model"],
            input_tokens=outcome["input_tokens"],
            output_tokens=outcome["output_tokens"],
            retrieval_ms=0.0,
            generation_ms=0.0,
            total_ms=outcome["total_ms"],
            error=error,
        )

    scored = [r["score"] for r in results if r["score"] > 0]
    report = {
        "num_cases": len(results),
        "avg_score": round(sum(scored) / len(scored), 2) if scored else 0.0,
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
