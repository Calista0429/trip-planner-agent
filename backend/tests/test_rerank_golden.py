"""Golden + invariant tests for planner.rerank.

rerank is the project's hand-built reward function (grounding, budget fit, meal
diversity ...). It is exactly the logic the LangGraph refactor must preserve
byte-for-byte, so we pin both the raw metrics and the final scores.
"""

from app.planner.rerank import (
    recompute_budget_from_selected_items,
    rerank_trip_plan_candidates,
    score_rerank_metrics,
    score_trip_plan_candidate,
)

from .builders import (
    bad_ungrounded_plan,
    good_grounded_plan,
    make_context,
    make_request,
)


# Candidate pools used by the grounded plan; names match exactly.
GROUNDED_CONTEXT = make_context(
    attraction_names=["故宫博物院"],
    hotel_names=["如家酒店"],
    food_names=["庆丰包子铺", "四季民福烤鸭", "南门涮肉"],
)


def test_recompute_budget_arithmetic():
    """Recompute must multiply unit prices by party size / room count."""
    request = make_request(adults=2)  # party.total = 2 -> room_count = 1
    plan = good_grounded_plan(request)

    result = recompute_budget_from_selected_items(plan, request)

    assert result["total_attractions"] == 120  # 60 * 2 people
    assert result["total_hotels"] == 400  # 400 * 1 room
    assert result["total_meals"] == 410  # (25 + 80 + 100) * 2 people
    assert result["total_transportation"] == 100  # reported as-is
    assert result["total"] == 1030


def test_recompute_budget_scales_with_party_size():
    """Four guests -> 2 rooms, and per-person costs double vs the 2-person case."""
    request = make_request(adults=4)  # party.total = 4 -> room_count = 2
    plan = good_grounded_plan(request)

    result = recompute_budget_from_selected_items(plan, request)

    assert result["total_attractions"] == 240  # 60 * 4
    assert result["total_hotels"] == 800  # 400 * 2 rooms
    assert result["total_meals"] == 820  # (25 + 80 + 100) * 4
    assert result["total"] == 1960


def test_recompute_budget_golden(golden):
    request = make_request(adults=2)
    plan = good_grounded_plan(request)
    golden("recompute_budget_two_adults", recompute_budget_from_selected_items(plan, request))


def test_score_metrics_grounded_plan(golden):
    """A fully grounded, within-budget plan should pass the key gates."""
    request = make_request(adults=2, budget_amount=2000, strictness="hard")
    plan = good_grounded_plan(request)

    metrics = score_trip_plan_candidate(plan, request, GROUNDED_CONTEXT)

    assert metrics["attraction_grounding_ok"] is True
    assert metrics["hotel_grounding_ok"] is True
    assert metrics["budget_hard_constraint_ok"] is True  # 1030 <= 2000
    assert metrics["attraction_grounding_rate"] == 1.0
    golden("metrics_grounded_plan", metrics)


def test_score_metrics_ungrounded_over_budget_plan(golden):
    """Invented POIs + blown budget should fail grounding and the hard gate."""
    request = make_request(adults=2, budget_amount=2000, strictness="hard")
    plan = bad_ungrounded_plan(request)

    metrics = score_trip_plan_candidate(plan, request, GROUNDED_CONTEXT)

    assert metrics["attraction_grounding_ok"] is False
    assert metrics["hotel_grounding_ok"] is False
    assert metrics["budget_hard_constraint_ok"] is False  # 6700 > 2000
    golden("metrics_ungrounded_plan", metrics)


def test_score_rerank_metrics_prefers_compliant_plan():
    """The weighting must score a compliant plan strictly above a broken one."""
    good = {
        "budget_hard_constraint_ok": True,
        "recomputed_budget_fit_ok": True,
        "budget_relationship_ok": True,
        "meal_cost_scale_ok": True,
        "meal_diversity_ok": True,
        "attraction_diversity_ok": True,
        "meal_grounding_rate": 1.0,
        "attraction_grounding_rate": 1.0,
        "hotel_grounding_rate": 1.0,
        "budget_arithmetic_consistent": True,
        "budget_fit_closeness": 1.0,
    }
    bad = {
        "budget_hard_constraint_ok": False,
        "recomputed_budget_fit_ok": False,
        "budget_fit_distance_ratio": 1.0,
        "budget_relationship_ok": False,
        "meal_cost_scale_ok": False,
        "meal_diversity_ok": False,
        "attraction_diversity_ok": False,
        "meal_grounding_rate": 0.0,
        "attraction_grounding_rate": 0.0,
        "hotel_grounding_rate": 0.0,
        "budget_arithmetic_consistent": False,
        "budget_fit_closeness": 0.0,
    }
    assert score_rerank_metrics(good) > score_rerank_metrics(bad)
    # The hard-constraint failure alone is a -40 swing, so bad must go negative.
    assert score_rerank_metrics(bad) < 0


def test_score_rerank_metrics_golden(golden):
    good = {
        "budget_hard_constraint_ok": True,
        "recomputed_budget_fit_ok": True,
        "budget_relationship_ok": True,
        "meal_cost_scale_ok": True,
        "meal_diversity_ok": True,
        "attraction_diversity_ok": True,
        "meal_grounding_rate": 1.0,
        "attraction_grounding_rate": 1.0,
        "hotel_grounding_rate": 1.0,
        "budget_arithmetic_consistent": True,
        "budget_fit_closeness": 1.0,
    }
    golden("rerank_score_compliant", {"score": score_rerank_metrics(good)})


def test_rerank_orders_good_above_bad(golden):
    """End-to-end: the grounded candidate must win regardless of attempt order."""
    request = make_request(adults=2, budget_amount=2000, strictness="hard")
    good = good_grounded_plan(request)
    bad = bad_ungrounded_plan(request)

    # Feed the bad plan first to prove ordering is by score, not by attempt.
    ranked = rerank_trip_plan_candidates(
        [(1, bad), (2, good)], request, GROUNDED_CONTEXT
    )

    assert [c.attempt for c in ranked] == [2, 1]
    assert ranked[0].score > ranked[1].score
    golden(
        "rerank_ranked_attempts",
        [{"attempt": c.attempt, "score": c.score} for c in ranked],
    )
