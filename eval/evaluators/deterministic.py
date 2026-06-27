# eval/evaluators/deterministic.py
"""Deterministic LangSmith evaluators that reuse the planner's own metrics.

Each evaluator takes (run, example) and returns {"key", "score", "comment"}.
`run.outputs` is the target output dict from generate_trip_plan_detailed:
  {"plan": <dict|None>, "status": str, "planner_context": dict, "failures": list}
`example.inputs["request"]` is the TripRequest dict.
"""
from __future__ import annotations

import functools
from typing import Any

from app.models.schemas import TripPlan, TripRequest
from app.planner.pricing import FREE_ATTRACTION_KEYWORDS, MUSEUM_TYPE_KEYWORDS
from app.planner.rerank import score_trip_plan_candidate


def safe_evaluator(func):
    """Wrap an evaluator so any exception becomes {key, score=None, comment} instead of raising into the experiment (spec §8)."""
    @functools.wraps(func)
    def _wrapped(run, example):
        try:
            return func(run, example)
        except Exception as exc:  # noqa: BLE001 - evaluators must never raise into evaluate()
            return {"key": func.__name__, "score": None, "comment": f"evaluator error: {exc}"}
    return _wrapped


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


@safe_evaluator
def grounding_rate(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "grounding_rate", "score": 0.0, "comment": "no plan"}
    rates = [m["attraction_grounding_rate"], m["hotel_grounding_rate"], m["meal_grounding_rate"]]
    score = round(sum(rates) / len(rates), 4)
    return {"key": "grounding_rate", "score": score,
            "comment": f"attr={rates[0]} hotel={rates[1]} meal={rates[2]}"}


@safe_evaluator
def budget_fit(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_fit", "score": 0.0, "comment": "no plan"}
    score = 1.0 if m["recomputed_budget_fit_ok"] else 0.0
    return {"key": "budget_fit", "score": score,
            "comment": f"total={m['recomputed_budget_total']} "
                       f"target=[{m['budget_target_min_total']},{m['budget_target_max_total']}] "
                       f"distance_ratio={m['budget_fit_distance_ratio']}"}


@safe_evaluator
def budget_hard_ok(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_hard_ok", "score": 0.0, "comment": "no plan"}
    return {"key": "budget_hard_ok", "score": 1.0 if m["budget_hard_constraint_ok"] else 0.0,
            "comment": f"hard_constraint_ok={m['budget_hard_constraint_ok']}"}


@safe_evaluator
def budget_arithmetic_ok(run: Any, example: Any) -> dict:
    m = _metrics(run, example)
    if m is None:
        return {"key": "budget_arithmetic_ok", "score": 0.0, "comment": "no plan"}
    return {"key": "budget_arithmetic_ok", "score": 1.0 if m["budget_arithmetic_consistent"] else 0.0}


@safe_evaluator
def plan_success(run: Any, example: Any) -> dict:
    status = (getattr(run, "outputs", None) or {}).get("status")
    return {"key": "plan_success", "score": 1.0 if status == "llm_success" else 0.0,
            "comment": f"status={status}"}


_FREE_KEYWORDS = list(FREE_ATTRACTION_KEYWORDS) + list(MUSEUM_TYPE_KEYWORDS)
_PORK_DISH_KEYWORDS = ["猪", "排骨", "小面", "烧腊", "叉烧", "回锅肉", "红烧肉",
                       "锅包肉", "火腿", "培根", "香肠", "腊肠", "卤肉"]
_NO_PORK_TRIGGERS = ["不吃猪", "无猪", "忌猪", "清真", "no pork", "不要猪", "穆斯林"]


@safe_evaluator
def free_ticket_violations(run: Any, example: Any) -> dict:
    plan = plan_from_run(run)
    if plan is None:
        return {"key": "free_ticket_violations", "score": 0.0, "comment": "no plan"}
    total = 0
    violations = 0
    bad = []
    for day in plan.days:
        for a in day.attractions:
            total += 1
            name = str(a.name or "")
            if any(k in name for k in _FREE_KEYWORDS) and int(a.ticket_price or 0) > 0:
                violations += 1
                bad.append(f"{name}=¥{a.ticket_price}")
    score = 1.0 if violations == 0 else round(max(0.0, 1.0 - violations / max(total, 1)), 4)
    return {"key": "free_ticket_violations", "score": score,
            "comment": f"{violations}/{total} fabricated free-POI tickets: {', '.join(bad)}" if bad else "0 violations"}


@safe_evaluator
def hotel_nights_ok(run: Any, example: Any) -> dict:
    plan = plan_from_run(run)
    req = request_from_example(example)
    if plan is None or not plan.days:
        return {"key": "hotel_nights_ok", "score": 0.0, "comment": "no plan"}
    expected_nights = max(0, int(req.travel_days) - 1)
    hotel_days = sum(1 for d in plan.days if d.hotel is not None)
    last_day_has_hotel = plan.days[-1].hotel is not None
    ok = (hotel_days == expected_nights) and not last_day_has_hotel
    return {"key": "hotel_nights_ok", "score": 1.0 if ok else 0.0,
            "comment": f"hotel_days={hotel_days} expected_nights={expected_nights} "
                       f"last_day_hotel={last_day_has_hotel}"}


def _wants_no_pork(req: TripRequest) -> bool:
    prefs = " ".join(req.preferences or []) if isinstance(req.preferences, list) else str(req.preferences or "")
    text = f"{req.free_text_input or ''} {prefs}".lower()
    return any(trigger.lower() in text for trigger in _NO_PORK_TRIGGERS)


@safe_evaluator
def hard_constraint_ok(run: Any, example: Any) -> dict:
    plan = plan_from_run(run)
    req = request_from_example(example)
    if plan is None:
        return {"key": "hard_constraint_ok", "score": 0.0, "comment": "no plan"}
    problems = []
    if len(plan.days) != int(req.travel_days):
        problems.append(f"day_count={len(plan.days)}!={req.travel_days}")
    if plan.start_date != req.start_date or plan.end_date != req.end_date:
        problems.append("dates_mismatch")
    if _wants_no_pork(req):
        for day in plan.days:
            for meal in day.meals:
                if any(k in str(meal.name or "") for k in _PORK_DISH_KEYWORDS):
                    problems.append(f"pork:{meal.name}")
                    break
    return {"key": "hard_constraint_ok", "score": 1.0 if not problems else 0.0,
            "comment": "; ".join(problems) or "ok"}


METRIC_EVALUATORS = [
    grounding_rate, budget_fit, budget_hard_ok, budget_arithmetic_ok, plan_success,
    free_ticket_violations, hotel_nights_ok, hard_constraint_ok,
]
