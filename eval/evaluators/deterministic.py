# eval/evaluators/deterministic.py
"""Deterministic LangSmith evaluators that reuse the planner's own metrics.

Each evaluator takes (run, example) and returns {"key", "score", "comment"}.
`run.outputs` is the target output dict from generate_trip_plan_detailed:
  {"plan": <dict|None>, "status": str, "planner_context": dict, "failures": list}
`example.inputs["request"]` is the TripRequest dict.
"""
from __future__ import annotations

from typing import Any

from app.models.schemas import TripPlan, TripRequest
from app.planner.rerank import score_trip_plan_candidate


def request_from_example(example: Any) -> TripRequest:
    return TripRequest(**example.inputs["request"])


def plan_from_run(run: Any) -> TripPlan | None:
    out = getattr(run, "outputs", None) or {}
    raw = out.get("plan")
    return TripPlan(**raw) if raw else None


def context_from_run(run: Any) -> dict:
    out = getattr(run, "outputs", None) or {}
    return out.get("planner_context") or {}


def _metrics(run: Any, example: Any) -> dict | None:
    plan = plan_from_run(run)
    if plan is None:
        return None
    return score_trip_plan_candidate(plan, request_from_example(example), context_from_run(run))


def grounding_rate(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "grounding_rate", "score": 0.0, "comment": "no plan"}
    rates = [m["attraction_grounding_rate"], m["hotel_grounding_rate"], m["meal_grounding_rate"]]
    score = round(sum(rates) / len(rates), 4)
    return {"key": "grounding_rate", "score": score,
            "comment": f"attr={rates[0]} hotel={rates[1]} meal={rates[2]}"}


def budget_fit(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_fit", "score": 0.0, "comment": "no plan"}
    score = 1.0 if m["recomputed_budget_fit_ok"] else 0.0
    return {"key": "budget_fit", "score": score,
            "comment": f"total={m['recomputed_budget_total']} "
                       f"target=[{m['budget_target_min_total']},{m['budget_target_max_total']}] "
                       f"distance_ratio={m['budget_fit_distance_ratio']}"}


def budget_hard_ok(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_hard_ok", "score": 0.0, "comment": "no plan"}
    return {"key": "budget_hard_ok", "score": 1.0 if m["budget_hard_constraint_ok"] else 0.0}


def budget_arithmetic_ok(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_arithmetic_ok", "score": 0.0, "comment": "no plan"}
    return {"key": "budget_arithmetic_ok", "score": 1.0 if m["budget_arithmetic_consistent"] else 0.0}


def plan_success(run: Any, example: Any) -> dict:
    status = (getattr(run, "outputs", None) or {}).get("status")
    return {"key": "plan_success", "score": 1.0 if status == "llm_success" else 0.0,
            "comment": f"status={status}"}


METRIC_EVALUATORS = [grounding_rate, budget_fit, budget_hard_ok, budget_arithmetic_ok, plan_success]
