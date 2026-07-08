import json
from pathlib import Path

EVAL_SET_PATH = Path("eval/eval_set.json")


def test_eval_set_is_well_formed():
    cases = json.loads(EVAL_SET_PATH.read_text(encoding="utf-8"))
    assert len(cases) >= 3
    for case in cases:
        assert case["question"].strip()
        assert case["expected_answer"].strip()
