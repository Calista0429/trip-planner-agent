import importlib


def _reload(monkeypatch, env_value=None):
    if env_value is None:
        monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    else:
        monkeypatch.setenv("LANGSMITH_TRACING", env_value)
    import app.observability.tracing as t
    return importlib.reload(t)


def test_disabled_when_env_unset(monkeypatch):
    t = _reload(monkeypatch, None)
    assert t.tracing_enabled() is False


def test_traceable_is_identity_when_disabled(monkeypatch):
    t = _reload(monkeypatch, None)

    def f(x):
        return x + 1

    assert t.traceable(f) is f
    assert t.traceable(name="x")(f) is f


def test_wrap_client_returns_same_object_when_disabled(monkeypatch):
    t = _reload(monkeypatch, None)
    sentinel = object()
    assert t.wrap_client(sentinel) is sentinel


def test_attach_run_metadata_noop_when_disabled(monkeypatch):
    t = _reload(monkeypatch, None)
    # Must not raise.
    t.attach_run_metadata({"k": "v"})
