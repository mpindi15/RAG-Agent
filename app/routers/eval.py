import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.eval_runner import run_eval

router = APIRouter(prefix="/api/eval", tags=["eval"])

EVAL_SET_PATH = Path("eval/eval_set.json")
RESULTS_DIR = Path("eval/results")


@router.post("/run")
def trigger_eval() -> dict:
    if not EVAL_SET_PATH.exists():
        raise HTTPException(status_code=500, detail=f"Eval set not found at {EVAL_SET_PATH}")

    report = run_eval(EVAL_SET_PATH)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"eval_report_{stamp}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    report["saved_to"] = str(out_path)
    return report


@router.get("/latest")
def latest_eval() -> dict:
    if not RESULTS_DIR.exists():
        return {"available": False}
    reports = sorted(RESULTS_DIR.glob("eval_report_*.json"))
    if not reports:
        return {"available": False}
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    report["available"] = True
    report["saved_to"] = str(reports[-1])
    return report
