"""Aggregate queries over the traces table for the Monitoring dashboard."""

import json
from datetime import datetime, timedelta, timezone

from app.db import get_conn


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(int(len(values) * pct), len(values) - 1)
    return round(values[idx], 1)


def summary() -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT total_ms, cost_usd, input_tokens, output_tokens, error, kind "
            "FROM traces WHERE kind = 'query'"
        ).fetchall()
        doc_count = conn.execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
        chunk_count = conn.execute(
            "SELECT COALESCE(SUM(num_chunks), 0) AS c FROM documents"
        ).fetchone()["c"]

    latencies = [r["total_ms"] for r in rows]
    errors = [r for r in rows if r["error"]]

    return {
        "total_queries": len(rows),
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(rows), 4) if rows else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "total_cost_usd": round(sum(r["cost_usd"] or 0 for r in rows), 6),
        "total_input_tokens": sum(r["input_tokens"] or 0 for r in rows),
        "total_output_tokens": sum(r["output_tokens"] or 0 for r in rows),
        "document_count": doc_count,
        "chunk_count": chunk_count,
    }


def queries_over_time(hours: int = 24) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT created_at, total_ms, error FROM traces "
            "WHERE kind = 'query' AND created_at >= ? ORDER BY created_at",
            (since.isoformat(),),
        ).fetchall()

    buckets: dict[str, dict] = {}
    for r in rows:
        ts = datetime.fromisoformat(r["created_at"])
        bucket_key = ts.strftime("%Y-%m-%dT%H:00")
        b = buckets.setdefault(bucket_key, {"hour": bucket_key, "count": 0, "errors": 0, "latency_sum": 0.0})
        b["count"] += 1
        b["latency_sum"] += r["total_ms"] or 0
        if r["error"]:
            b["errors"] += 1

    out = []
    for b in sorted(buckets.values(), key=lambda x: x["hour"]):
        out.append(
            {
                "hour": b["hour"],
                "count": b["count"],
                "errors": b["errors"],
                "avg_latency_ms": round(b["latency_sum"] / b["count"], 1) if b["count"] else 0,
            }
        )
    return out


def recent_traces(limit: int = 25, offset: int = 0, kind: str | None = None) -> dict:
    with get_conn() as conn:
        if kind:
            rows = conn.execute(
                "SELECT * FROM traces WHERE kind = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (kind, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) AS c FROM traces WHERE kind = ?", (kind,)
            ).fetchone()["c"]
        else:
            rows = conn.execute(
                "SELECT * FROM traces ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS c FROM traces").fetchone()["c"]

    items = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"]) if d["sources"] else []
        items.append(d)

    return {"items": items, "total": total, "limit": limit, "offset": offset}
