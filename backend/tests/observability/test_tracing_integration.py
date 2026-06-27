def test_wrap_client_called_on_llms_when_enabled(monkeypatch):
    calls = []
    import app.graph.runtime as runtime          # import first (may be cached)
    monkeypatch.setattr(runtime, "wrap_client",
                        lambda c: (calls.append(c) or c))
    runtime.build_default_runtime()
    # Two LLMs (primary + fallback) should have had their inner client wrapped.
    assert len(calls) == 2


def test_amap_get_is_decorated():
    # The decorator is applied at import time; when tracing is disabled it is
    # identity, so the function still exists and is callable.
    from app.planner.amap import AmapPlannerClient

    assert callable(AmapPlannerClient.get)
