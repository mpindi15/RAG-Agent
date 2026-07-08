"""CLI entry point for the eval harness.

Usage: python -m eval.run_eval
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.db import init_db
from app.eval_runner import run_eval

EVAL_SET_PATH = Path("eval/eval_set.json")
RESULTS_DIR = Path("eval/results")


def main() -> None:
    init_db()
    report = run_eval(EVAL_SET_PATH)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"eval_report_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{'Question':<70} {'Score':<6} {'Retrieval':<10} {'Latency (ms)'}")
    print("-" * 105)
    for r in report["results"]:
        q = (r["question"][:67] + "...") if len(r["question"]) > 70 else r["question"]
        print(f"{q:<70} {r['score']:<6} {str(r['retrieval_hit']):<10} {r['latency_ms']}")

    print("\n=== Summary ===")
    print(f"Cases:              {report['num_cases']}")
    print(f"Avg score (1-5):    {report['avg_score']}")
    print(f"Pass rate (>=4):    {report['pass_rate_at_4'] * 100:.0f}%")
    print(f"Retrieval hit rate: {report['retrieval_hit_rate'] * 100:.0f}%")
    print(f"Avg latency:        {report['avg_latency_ms']} ms")
    print(f"\nSaved report to {out_path}")


if __name__ == "__main__":
    main()
