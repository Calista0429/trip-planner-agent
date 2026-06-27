# backend/tests/eval/test_deterministic_evaluators.py
import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))

from app.models.schemas import TripRequest
from app.planner.output import create_fallback_plan


def _example():
    req = TripRequest(
        city="北京", start_date="2026-07-01", end_date="2026-07-03", travel_days=3,
        party={"adults": 2, "children": 0, "seniors": 0, "total": 2},
        budget_constraint={"amount": 6000, "strictness": "soft"},
        preferences=[], transportation="public", accommodation="hotel", free_text_input="",
    )
    return SimpleNamespace(inputs={"request": req.model_dump(mode="json")}, outputs={})


def _run(status="llm_success"):
    req = _example().inputs["request"]
    plan = create_fallback_plan(TripRequest(**req))
    return SimpleNamespace(
        outputs={"plan": plan.model_dump(mode="json"), "status": status, "planner_context": {"tool_snapshot": {}}}
    )


def test_plan_success_scores_one_for_llm_success():
    import deterministic
    res = deterministic.plan_success(_run("llm_success"), _example())
    assert res["key"] == "plan_success" and res["score"] == 1.0


def test_plan_success_scores_zero_for_fallback():
    import deterministic
    res = deterministic.plan_success(_run("fallback_success"), _example())
    assert res["score"] == 0.0


def test_budget_arithmetic_detects_consistency_and_mismatch():
    import deterministic
    run = _run()
    plan = run.outputs["plan"]
    plan["budget"] = {
        "total_attractions": 20,
        "total_hotels": 40,
        "total_meals": 30,
        "total_transportation": 10,
        "total": 100,  # 20+40+30+10 == 100  -> consistent
    }
    assert deterministic.budget_arithmetic_ok(run, _example())["score"] == 1.0

    plan["budget"]["total"] = plan["budget"]["total"] + 999  # 1099 != 100 -> inconsistent
    assert deterministic.budget_arithmetic_ok(run, _example())["score"] == 0.0


def test_grounding_rate_returns_float_between_0_and_1():
    import deterministic
    res = deterministic.grounding_rate(_run(), _example())
    assert 0.0 <= res["score"] <= 1.0
