"""Golden + invariant tests for planner.pricing.

These pure rules drive every budget number the user eventually sees. They are
stable by design (no live prices), which makes them ideal golden targets: any
drift during the LangGraph refactor must be deliberate.
"""

from app.planner import pricing

from .builders import make_request


# ---------------------------------------------------------------------------
# Scalar helpers: explicit asserts document the intended contract.
# ---------------------------------------------------------------------------

def test_round_to_50():
    assert pricing.round_to_50(0) == 0
    assert pricing.round_to_50(24) == 0
    # NOTE: round_to_50 relies on Python's round(), which uses banker's rounding
    # (round half to even). round(25/50)=round(0.5)=0, so 25 rounds *down* to 0,
    # not up to 50. A refactor must preserve this quirk to keep budgets stable.
    assert pricing.round_to_50(25) == 0
    assert pricing.round_to_50(75) == 100  # round(1.5)=2
    assert pricing.round_to_50(420) == 400
    assert pricing.round_to_50(430) == 450


def test_meal_price_level_buckets():
    assert pricing.meal_price_level(40) == "budget"
    assert pricing.meal_price_level(100) == "standard"
    assert pricing.meal_price_level(180) == "premium"
    assert pricing.meal_price_level(181) == "luxury"


def test_ticket_price_season_by_month():
    assert pricing.ticket_price_season(make_request(start_date="2025-01-15")) == "off_season"
    assert pricing.ticket_price_season(make_request(start_date="2025-06-01")) == "normal_season"
    assert pricing.ticket_price_season(make_request(start_date="2025-08-01")) == "peak_season"


def test_parse_float():
    assert pricing.parse_float(None) is None
    assert pricing.parse_float("") is None
    assert pricing.parse_float([]) is None
    assert pricing.parse_float("4.7") == 4.7
    assert pricing.parse_float("abc") is None


# ---------------------------------------------------------------------------
# Rule-based ticket estimation across keyword branches.
# ---------------------------------------------------------------------------

TICKET_ROWS = [
    {"name": "上海迪士尼乐园", "type": "主题公园"},
    {"name": "古北水镇温泉", "type": "温泉"},
    {"name": "王府井步行街", "type": "商业街"},
    {"name": "欢乐谷", "type": "游乐园"},
    {"name": "北京海洋馆", "type": "海洋馆"},
    {"name": "颐和园", "type": "公园"},
    {"name": "国家博物馆", "type": "博物馆"},
    {"name": "某不知名小馆", "type": "其他"},
]


def test_estimate_ticket_price_branches():
    """Spot-check the most important keyword routes."""
    by_name = {row["name"]: pricing.estimate_ticket_price(row) for row in TICKET_ROWS}
    assert by_name["上海迪士尼乐园"] == 280  # premium keyword
    assert by_name["王府井步行街"] == 0  # free-attraction keyword
    assert by_name["国家博物馆"] == 0  # museum keyword
    assert by_name["某不知名小馆"] == 60  # default


def test_estimate_ticket_price_golden(golden):
    golden(
        "ticket_price_by_row",
        {row["name"]: pricing.estimate_ticket_price(row) for row in TICKET_ROWS},
    )


# ---------------------------------------------------------------------------
# Hotel cost estimation: city factor + budget-level cap.
# ---------------------------------------------------------------------------

def test_estimate_hotel_cost_city_factor():
    """Beijing carries a 1.15 city factor; a comfort hotel base is 420."""
    request = make_request(city="北京", accommodation="舒适型酒店")
    # 420 * 1.15 = 483 -> round_to_50 -> 500
    assert pricing.estimate_hotel_cost(request, {"name": "某舒适酒店", "type": "舒适"}) == 500


def test_estimate_hotel_cost_comfortable_cap():
    """budget_level=comfortable caps rule-estimated hotel fallback at 700."""
    request = make_request(
        city="北京", accommodation="豪华酒店", budget_level="comfortable"
    )
    # luxury base 1200 * 1.15 = 1380 -> 1400, capped down to 700
    assert pricing.estimate_hotel_cost(request, {"name": "某豪华酒店", "type": "豪华"}) == 700


# ---------------------------------------------------------------------------
# Hint enrichment: prefers amap cost, falls back to rules.
# ---------------------------------------------------------------------------

HOTEL_ROWS = [
    {"name": "如家酒店", "type": "经济", "cost": "388"},  # amap_cost path
    {"name": "某舒适酒店", "type": "舒适"},  # rule path
]

MEAL_ROWS = [
    {"name": "庆丰包子铺", "type": "餐饮", "cost": "23", "meal_roles": ["breakfast"]},
    {"name": "某午餐馆", "type": "中餐厅"},  # no cost -> fallback lunch
]


def test_with_hotel_cost_hints_sources():
    request = make_request(city="北京")
    out = pricing.with_hotel_cost_hints(HOTEL_ROWS, request)
    assert out[0]["cost_source"] == "amap_cost"
    assert out[0]["estimated_cost_hint"] == pricing.round_to_50(388)  # 400
    assert out[1]["cost_source"] == "rule_estimated"


def test_with_meal_cost_hints_sources():
    request = make_request(city="北京")
    out = pricing.with_meal_cost_hints(MEAL_ROWS, request)
    assert out[0]["cost_source"] == "amap_cost"
    assert out[0]["meal_cost_hint"] == 23
    assert out[1]["cost_source"] == "rule_estimated"
    assert out[1]["meal_cost_hint"] == pricing.MEAL_FALLBACK_PER_PERSON["lunch"]


def test_hotel_hints_golden(golden):
    request = make_request(city="北京")
    out = pricing.with_hotel_cost_hints(HOTEL_ROWS, request)
    golden(
        "hotel_hints",
        [
            {
                "name": row["name"],
                "estimated_cost_hint": row["estimated_cost_hint"],
                "cost_source": row["cost_source"],
            }
            for row in out
        ],
    )


def test_meal_hints_golden(golden):
    request = make_request(city="北京")
    out = pricing.with_meal_cost_hints(MEAL_ROWS, request)
    golden(
        "meal_hints",
        [
            {
                "name": row["name"],
                "meal_cost_hint": row["meal_cost_hint"],
                "cost_source": row["cost_source"],
                "price_level": row["price_level"],
            }
            for row in out
        ],
    )
