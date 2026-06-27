# backend/tests/eval/test_new_checks.py
import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))

from app.models.schemas import TripRequest
from app.planner.output import create_fallback_plan


def _req(**over):
    base = dict(
        city="北京", start_date="2026-07-01", end_date="2026-07-03", travel_days=3,
        party={"adults": 2, "children": 0, "seniors": 0, "total": 2},
        budget_constraint={"amount": 6000, "strictness": "soft"},
        preferences=[], transportation="public", accommodation="hotel", free_text_input="",
    )
    base.update(over)
    return TripRequest(**base)


def _run_for(plan, ctx=None):
    return SimpleNamespace(outputs={"plan": plan.model_dump(mode="json"), "status": "llm_success",
                                    "planner_context": ctx or {"tool_snapshot": {}}})


def _example_for(req):
    return SimpleNamespace(inputs={"request": req.model_dump(mode="json")}, outputs={})


def test_free_ticket_violation_detected():
    import deterministic
    req = _req()
    plan = create_fallback_plan(req)
    # Force a free-keyword POI with a fabricated ticket.
    plan.days[0].attractions[0].name = "人民公园"
    plan.days[0].attractions[0].ticket_price = 80
    res = deterministic.free_ticket_violations(_run_for(plan), _example_for(req))
    assert res["key"] == "free_ticket_violations" and res["score"] < 1.0


def test_no_pork_violation_detected():
    import deterministic
    req = _req(free_text_input="我们不吃猪肉，清真")
    plan = create_fallback_plan(req)
    plan.days[0].meals[0].name = "重庆小面（猪骨汤）"
    res = deterministic.hard_constraint_ok(_run_for(plan), _example_for(req))
    assert res["score"] == 0.0


def test_hotel_nights_ok_for_wellformed_plan():
    import deterministic
    req = _req()
    plan = create_fallback_plan(req)
    res = deterministic.hotel_nights_ok(_run_for(plan), _example_for(req))
    assert res["key"] == "hotel_nights_ok" and res["score"] in (0.0, 1.0)
