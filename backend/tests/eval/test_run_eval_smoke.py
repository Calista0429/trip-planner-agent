# backend/tests/eval/test_run_eval_smoke.py
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval"))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))


def test_run_target_safely_wraps_errors():
    import run_eval

    def boom(inputs):
        raise RuntimeError("amap down")

    out = run_eval.run_target_safely(boom, {"request": {"city": "北京"}})
    assert out["status"] == "error"
    assert out["plan"] is None
    assert "amap down" in out["error"]


def test_summarize_reports_means():
    import run_eval
    results = [
        {"scores": {"grounding_rate": 1.0, "plan_success": 1.0}},
        {"scores": {"grounding_rate": 0.0, "plan_success": 1.0}},
    ]
    md = run_eval.summarize(results)
    assert "grounding_rate" in md and "0.5" in md
    assert "plan_success" in md and "1.0" in md
