# backend/tests/eval/test_llm_judge.py
import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))

from app.models.schemas import TripRequest
from app.planner.output import create_fallback_plan


def _req():
    return TripRequest(
        city="北京", start_date="2026-07-01", end_date="2026-07-03", travel_days=3,
        party={"adults": 2, "children": 0, "seniors": 0, "total": 2},
        budget_constraint={"amount": 6000, "strictness": "soft"},
        preferences=[], transportation="public", accommodation="hotel", free_text_input="",
    )


def test_parse_judge_reads_score_and_reason():
    import llm_judge
    raw = '这里是分析。\n```json\n{"reasoning": "节奏不错", "score": 4}\n```'
    score, reason = llm_judge.parse_judge(raw)
    assert score == 4.0 and "节奏" in reason


def test_llm_judge_normalizes_to_unit_interval():
    import llm_judge
    req = _req()
    plan = create_fallback_plan(req)
    run = SimpleNamespace(outputs={"plan": plan.model_dump(mode="json"), "status": "llm_success",
                                   "planner_context": {}})
    example = SimpleNamespace(inputs={"request": req.model_dump(mode="json")}, outputs={})

    judge = llm_judge.make_llm_judge(invoke_fn=lambda messages: '{"reasoning": "ok", "score": 5}')
    res = judge(run, example)
    assert res["key"] == "llm_judge" and res["score"] == 1.0 and res["comment"] == "ok"
