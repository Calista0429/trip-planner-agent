# backend/tests/test_service_detailed.py
from app.graph import service
from app.models.schemas import TripRequest


def _make_request() -> TripRequest:
    # Mirror the shape used by tests/test_graph_smoke.py fixtures.
    return TripRequest(
        city="北京",
        start_date="2026-07-01",
        end_date="2026-07-03",
        travel_days=3,
        party={"adults": 2, "children": 0, "seniors": 0, "total": 2},
        budget_constraint={"amount": 6000, "strictness": "soft"},
        preferences=[],
        transportation="public",
        accommodation="hotel",
        free_text_input="",
    )


def test_generate_trip_plan_detailed_returns_context(monkeypatch):
    # Patch the compiled graph to return a controlled final_state.
    class _FakeCompiled:
        def invoke(self, state, config=None):
            from app.planner.output import create_fallback_plan

            req = state["request"]
            return {
                "final_plan": create_fallback_plan(req),
                "status": "llm_success",
                "planner_context": {"tool_snapshot": {"classic_pois": []}},
                "failures": [{"preference_reason": "x"}],
            }

    monkeypatch.setattr(service, "_get_compiled", lambda: _FakeCompiled())

    out = service.generate_trip_plan_detailed(_make_request())
    assert out["status"] == "llm_success"
    assert "planner_context" in out and "tool_snapshot" in out["planner_context"]
    assert isinstance(out["plan"], dict)
    assert out["failures"] == [{"preference_reason": "x"}]
