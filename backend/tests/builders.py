"""Deterministic fixture builders for golden tests.

Kept separate from conftest so both the pricing and rerank suites can share the
exact same TripRequest / TripPlan / planner-context shapes.
"""

from typing import Any, Dict, List, Optional

from app.models.schemas import (
    Attraction,
    Budget,
    BudgetConstraint,
    DayPlan,
    Hotel,
    Location,
    Meal,
    PartyInfo,
    TripPlan,
    TripRequest,
)


def make_request(
    *,
    city: str = "北京",
    start_date: str = "2025-06-01",
    end_date: str = "2025-06-01",
    travel_days: int = 1,
    adults: int = 2,
    children: int = 0,
    elders: int = 0,
    accommodation: str = "舒适型酒店",
    budget_amount: Optional[int] = 2000,
    budget_level: str = "standard",
    strictness: str = "hard",
    preferences: Optional[List[str]] = None,
) -> TripRequest:
    """Build a TripRequest; party.total is derived to satisfy the validator."""
    total = adults + children + elders
    return TripRequest(
        city=city,
        start_date=start_date,
        end_date=end_date,
        travel_days=travel_days,
        transportation="公共交通",
        accommodation=accommodation,
        preferences=preferences or ["历史文化", "美食"],
        party=PartyInfo(
            adults=adults,
            children=children,
            elders=elders,
            total=total,
            companion_type="couple",
        ),
        budget_constraint=BudgetConstraint(
            amount=budget_amount,
            budget_level=budget_level,
            strictness=strictness,
        ),
    )


def _loc(lng: float = 116.4, lat: float = 39.9) -> Location:
    return Location(longitude=lng, latitude=lat)


def make_attraction(name: str, ticket_price: int) -> Attraction:
    return Attraction(
        name=name,
        address=f"{name}地址",
        location=_loc(),
        visit_duration=120,
        description=f"{name} description",
        ticket_price=ticket_price,
    )


def make_meal(meal_type: str, name: str, cost: int) -> Meal:
    return Meal(type=meal_type, name=name, location=_loc(), estimated_cost=cost)


def make_hotel(name: str, cost: int) -> Hotel:
    return Hotel(name=name, address=f"{name}地址", location=_loc(), estimated_cost=cost)


def make_day(
    *,
    date: str,
    day_index: int,
    attractions: List[Attraction],
    meals: List[Meal],
    hotel: Optional[Hotel],
) -> DayPlan:
    return DayPlan(
        date=date,
        day_index=day_index,
        description=f"day {day_index} plan",
        transportation="公共交通",
        accommodation="舒适型酒店",
        hotel=hotel,
        attractions=attractions,
        meals=meals,
    )


def make_plan(
    *,
    request: TripRequest,
    days: List[DayPlan],
    budget: Optional[Budget],
) -> TripPlan:
    return TripPlan(
        city=request.city,
        start_date=request.start_date,
        end_date=request.end_date,
        days=days,
        overall_suggestions="overall suggestions",
        budget=budget,
    )


def make_context(
    *,
    attraction_names: List[str],
    hotel_names: List[str],
    food_names: List[str],
    budget_policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a planner_context whose candidate pools drive grounding metrics."""

    def rows(names: List[str]) -> List[Dict[str, Any]]:
        return [{"name": n} for n in names]

    constraints: Dict[str, Any] = {}
    if budget_policy is not None:
        constraints["budget_fit_policy"] = budget_policy

    return {
        "tool_snapshot": {
            "classic_pois": rows(attraction_names),
            "preference_pois": [],
            "scenic_pois": [],
            "experience_pois": [],
            "hotel_pois": rows(hotel_names),
            "food_pois": rows(food_names),
        },
        "planner_constraints": constraints,
    }


# ---------------------------------------------------------------------------
# Ready-made scenarios shared across suites.
# ---------------------------------------------------------------------------

def good_grounded_plan(request: TripRequest) -> TripPlan:
    """A 1-day plan fully grounded in the candidate pools and within budget.

    party.total = 2, so hotel room_count = ceil(2/2) = 1.
    recomputed: attractions 60*2=120, hotels 400*1=400,
    meals (80+100)*2=360, transport 100 -> total 980.
    """
    day = make_day(
        date="2025-06-01",
        day_index=0,
        attractions=[make_attraction("故宫博物院", 60)],
        meals=[
            make_meal("breakfast", "庆丰包子铺", 25),
            make_meal("lunch", "四季民福烤鸭", 80),
            make_meal("dinner", "南门涮肉", 100),
        ],
        hotel=make_hotel("如家酒店", 400),
    )
    budget = Budget(
        total_attractions=120,
        total_hotels=400,
        total_meals=410,  # 25*2 + 80*2 + 100*2 = 410
        total_transportation=100,
        total=1030,
    )
    return make_plan(request=request, days=[day], budget=budget)


def bad_ungrounded_plan(request: TripRequest) -> TripPlan:
    """A plan with invented POIs and an over-budget total (hard constraint blown)."""
    day = make_day(
        date="2025-06-01",
        day_index=0,
        attractions=[make_attraction("上海迪士尼乐园", 600)],
        meals=[
            make_meal("lunch", "米其林三星法餐厅", 800),
            make_meal("dinner", "米其林三星法餐厅", 800),
        ],
        hotel=make_hotel("文华东方酒店", 2000),
    )
    budget = Budget(
        total_attractions=1200,
        total_hotels=2000,
        total_meals=3200,
        total_transportation=300,
        total=6700,
    )
    return make_plan(request=request, days=[day], budget=budget)
