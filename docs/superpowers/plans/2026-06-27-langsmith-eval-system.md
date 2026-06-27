# LangSmith Eval System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an env-gated LangSmith observability layer (latency, tokens/cost, errors) plus a product-level `eval/` package that runs the live planner graph over a ~30-request curated dataset and scores delivered-plan quality with deterministic evaluators (reusing `rerank.py`/`critic.py` logic) and an optional LLM-as-judge.

**Architecture:** A single tracing seam (`backend/app/observability/tracing.py`) provides safe no-op-when-off helpers (`traceable`, `wrap_client`, `attach_run_metadata`). The planner graph is instrumented only through that seam, so the default flow is byte-for-byte unchanged when `LANGSMITH_TRACING` is unset. A standalone repo-root `eval/` package uses `langsmith.evaluate()` with a target that calls a new `generate_trip_plan_detailed()` entry point (returns plan + `planner_context` so evaluators can ground against the Amap snapshot).

**Tech Stack:** Python 3.11, LangGraph, LangSmith SDK, pytest, Pydantic v2, OpenAI client (inside `HelloAgentsLLM`).

## Global Constraints

- Python 3.11; run backend tests with `pytest` from `backend/` (see `backend/tests/conftest.py`).
- Validate Python changes with `python -m py_compile` (no separate lint step).
- All new behavior is **off by default**, gated on env vars: `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` (default `trip-planner`), `LANGSMITH_ENDPOINT` (optional), `EVAL_ENABLE_LLM_JUDGE`.
- When tracing env is off OR the `langsmith` package is missing, the product MUST run identically with zero added latency.
- Do NOT change `HelloAgentsLLM`/`hello_agents` source. Token capture is done by wrapping its inner OpenAI client (`llm._client`).
- Backend import style from repo-root scripts/tests: `BACKEND = ROOT / "backend"; sys.path.insert(0, str(BACKEND))`, then `from app.models.schemas import TripRequest` etc. (mirrors `scripts/gen_human_eval_plans.py`).
- The repo-root directory is named `eval/` (per spec). To avoid shadowing the Python builtin `eval`, **never `import eval`**; scripts/tests add the relevant `eval/...` subdir to `sys.path` and import submodules directly (e.g. `import deterministic`).
- `hotel_distance_ok` is intentionally OUT of scope for this version.

---

### Task 1: Tracing seam (`observability/tracing.py`) + dependency

**Files:**
- Create: `backend/app/observability/__init__.py`
- Create: `backend/app/observability/tracing.py`
- Modify: `backend/requirements.txt` (add `langsmith`)
- Test: `backend/tests/observability/test_tracing.py`

**Interfaces:**
- Produces:
  - `tracing_enabled() -> bool`
  - `init_tracing() -> None`
  - `traceable(*dargs, **dkwargs)` — decorator; identity pass-through when disabled
  - `wrap_client(client: Any) -> Any` — returns client unchanged when disabled
  - `attach_run_metadata(metadata: Mapping[str, Any]) -> None` — no-op when disabled

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/observability/test_tracing.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/observability/test_tracing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.observability'`.

- [ ] **Step 3: Create the package and module**

```python
# backend/app/observability/__init__.py
```

```python
# backend/app/observability/tracing.py
"""LangSmith tracing seam.

A complete no-op unless ``LANGSMITH_TRACING`` is truthy AND the ``langsmith``
package is importable. Decorators degrade to identity pass-throughs so the
default planner flow is unchanged with zero added latency.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_warned = False


def _env_on() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() in _TRUTHY


def tracing_enabled() -> bool:
    """True only when the env switch is on and langsmith can be imported."""
    if not _env_on():
        return False
    try:
        import langsmith  # noqa: F401
    except Exception:
        return False
    return True


def init_tracing() -> None:
    """Call once at startup. Warns once if env is on but langsmith is missing."""
    global _warned
    if _env_on() and not tracing_enabled() and not _warned:
        logger.warning(
            "LANGSMITH_TRACING is set but the 'langsmith' package is not "
            "importable; tracing disabled."
        )
        _warned = True


def traceable(*dargs: Any, **dkwargs: Any) -> Callable:
    """Safe @traceable. Identity decorator when tracing is disabled."""

    def _decorator(func: Callable) -> Callable:
        if not tracing_enabled():
            return func
        from langsmith import traceable as _ls_traceable

        return _ls_traceable(*dargs, **dkwargs)(func)

    if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
        return _decorator(dargs[0])
    return _decorator


def wrap_client(client: Any) -> Any:
    """Wrap an OpenAI client with langsmith.wrap_openai when enabled."""
    if not tracing_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:
        logger.warning(
            "Failed to wrap OpenAI client for LangSmith; tokens will not be "
            "traced.",
            exc_info=True,
        )
        return client


def attach_run_metadata(metadata: Mapping[str, Any]) -> None:
    """Attach metadata to the current run tree (e.g. failures, status)."""
    if not tracing_enabled():
        return
    try:
        from langsmith.run_helpers import get_current_run_tree

        rt = get_current_run_tree()
        if rt is not None:
            rt.add_metadata(dict(metadata))
    except Exception:
        pass
```

Add to `backend/requirements.txt` (below the existing `langgraph>=1.2.0` line):

```
# LangSmith observability + evaluation
langsmith>=0.1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/observability/test_tracing.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/observability/__init__.py backend/app/observability/tracing.py backend/requirements.txt backend/tests/observability/test_tracing.py
git commit -m "feat(observability): add env-gated LangSmith tracing seam"
```

---

### Task 2: Wire tracing into the live graph (token + tool + node spans)

**Files:**
- Modify: `backend/app/graph/runtime.py` (around lines 118-119, after `primary_llm`/`fallback_llm` creation)
- Modify: `backend/app/planner/amap.py` (decorate `AmapClient.get`, line 65)
- Modify: `backend/app/main.py` or app startup (call `init_tracing()` once) — see Step 3 for exact location
- Test: `backend/tests/observability/test_tracing_integration.py`

**Interfaces:**
- Consumes: `wrap_client`, `traceable`, `init_tracing` from Task 1.
- Produces: no new public symbols; instrumentation side-effects only.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/observability/test_tracing_integration.py
import app.observability.tracing as tracing


def test_wrap_client_called_on_llms_when_enabled(monkeypatch):
    calls = []
    monkeypatch.setattr(tracing, "wrap_client", lambda c: (calls.append(c) or c))

    import app.graph.runtime as runtime

    runtime.build_default_runtime()
    # Two LLMs (primary + fallback) should have had their inner client wrapped.
    assert len(calls) == 2


def test_amap_get_is_decorated():
    # The decorator is applied at import time; when tracing is disabled it is
    # identity, so the function still exists and is callable.
    from app.planner.amap import AmapClient

    assert callable(AmapClient.get)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/observability/test_tracing_integration.py -v`
Expected: FAIL — `test_wrap_client_called_on_llms_when_enabled` asserts 2 calls but instrumentation is not wired yet (0 calls).

- [ ] **Step 3: Wire `wrap_client` in `runtime.py`**

In `backend/app/graph/runtime.py`, add the import near the other imports:

```python
from ..observability.tracing import wrap_client
```

Immediately after the LLMs are created (currently lines 118-119):

```python
    primary_llm = get_planner_llm()
    fallback_llm = get_llm()
    # Capture tokens/cost/latency in LangSmith without forking hello_agents:
    # wrap the inner OpenAI client. No-op when tracing is disabled.
    try:
        primary_llm._client = wrap_client(primary_llm._client)
        fallback_llm._client = wrap_client(fallback_llm._client)
    except AttributeError:
        pass
```

Decorate the Amap HTTP method in `backend/app/planner/amap.py`. Add the import near the top:

```python
from ..observability.tracing import traceable
```

And decorate `AmapClient.get` (line 65):

```python
    @traceable(name="amap_request", run_type="tool")
    def get(
        self,
        ...
```

Add `init_tracing()` at app startup. In `backend/app/main.py`, after the FastAPI `app` is created and other startup wiring runs, add:

```python
from app.observability.tracing import init_tracing

init_tracing()
```

(If `main.py` uses a lifespan/startup hook, call `init_tracing()` there instead. The call is idempotent and safe to place at module import.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/observability/test_tracing_integration.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Verify the default flow still compiles and graph tests pass**

Run: `cd backend && python -m py_compile app/graph/runtime.py app/planner/amap.py app/main.py && pytest tests/test_graph_smoke.py -q`
Expected: compile OK; graph smoke tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/runtime.py backend/app/planner/amap.py backend/app/main.py backend/tests/observability/test_tracing_integration.py
git commit -m "feat(observability): trace tokens via wrap_openai + amap tool spans"
```

---

### Task 3: Eval-facing entry point with run metadata (`generate_trip_plan_detailed`)

**Files:**
- Modify: `backend/app/graph/service.py` (lines 43-51 region)
- Test: `backend/tests/test_service_detailed.py`

**Interfaces:**
- Consumes: `traceable`, `attach_run_metadata` from Task 1.
- Produces:
  - `generate_trip_plan_detailed(request: TripRequest) -> dict` returning
    `{"plan": <dict|None>, "status": str, "planner_context": dict, "failures": list[dict]}`
  - Behavior of existing `generate_trip_plan(request) -> PlanResult` is unchanged.

- [ ] **Step 1: Write the failing test**

```python
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
    fake_state = {
        "final_plan": service.generate_trip_plan.__globals__  # placeholder, replaced below
    }

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
```

(Delete the unused `fake_state` placeholder line when implementing; it is shown only to keep the diff minimal — the real assertion is via the patched `_get_compiled`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_service_detailed.py -v`
Expected: FAIL with `AttributeError: module 'app.graph.service' has no attribute 'generate_trip_plan_detailed'`.

- [ ] **Step 3: Implement the entry point**

In `backend/app/graph/service.py` add the import:

```python
from ..observability.tracing import attach_run_metadata, traceable
```

Refactor the run into a shared traced helper and add the detailed entry point:

```python
@traceable(name="planner_graph", run_type="chain")
def _run_graph(request: TripRequest) -> dict:
    compiled = _get_compiled()
    final_state = compiled.invoke(
        initial_state(request), config={"recursion_limit": GRAPH_RECURSION_LIMIT}
    )
    failures = final_state.get("failures", []) or []
    attach_run_metadata(
        {
            "status": final_state.get("status", "unknown"),
            "failure_count": len(failures),
            "planner_failures": failures[:20],
            "use_fallback_llm": bool(final_state.get("use_fallback_llm")),
            "attempt": final_state.get("attempt"),
            "city": request.city,
            "party_total": request.party.total,
            "budget_amount": request.budget_constraint.amount,
            "budget_strictness": request.budget_constraint.strictness,
        }
    )
    return final_state


def generate_trip_plan(request: TripRequest) -> PlanResult:
    """Run the planning graph and adapt its final state for the API."""
    final_state = _run_graph(request)
    status = final_state.get("status", "unknown")
    message = _STATUS_MESSAGES.get(status, "旅行计划生成完成")
    return PlanResult(plan=final_state["final_plan"], status=status, message=message)


def generate_trip_plan_detailed(request: TripRequest) -> dict:
    """Eval-facing entry point: returns plan + planner_context + status + failures."""
    final_state = _run_graph(request)
    plan = final_state.get("final_plan")
    return {
        "plan": plan.model_dump(mode="json") if plan is not None else None,
        "status": final_state.get("status", "unknown"),
        "planner_context": final_state.get("planner_context") or {},
        "failures": final_state.get("failures", []) or [],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_service_detailed.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/service.py backend/tests/test_service_detailed.py
git commit -m "feat(graph): add generate_trip_plan_detailed eval entry point + run metadata"
```

---

### Task 4: Curated dataset file + LangSmith upload script

**Files:**
- Create: `eval/__init__.py`
- Create: `eval/datasets/human_eval_30.jsonl` (generated, then committed)
- Create: `eval/upload_dataset.py`
- Create: `eval/build_dataset.py` (one-shot generator from `out/human_eval/plan_*.json`)
- Test: `backend/tests/eval/test_dataset.py`

**Interfaces:**
- Produces (in `eval/upload_dataset.py`):
  - `load_examples(path: str) -> list[dict]` — each `{"inputs", "outputs", "metadata"}`
  - `upload(dataset_name: str = "human_eval_30", path: str = ...) -> None`

- [ ] **Step 1: Generate the dataset file**

Create `eval/build_dataset.py`:

```python
"""Freeze the ~30 human-eval requests into a LangSmith dataset jsonl.

Source: out/human_eval/plan_*.json (each has a full 'request'). Run once;
commit the resulting eval/datasets/human_eval_30.jsonl.
"""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "eval", "datasets", "human_eval_30.jsonl")


def main() -> None:
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "human_eval", "plan_*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        req = data["request"]
        bc = req.get("budget_constraint") or {}
        party = req.get("party") or {}
        rows.append(
            {
                "inputs": {"request": req},
                "outputs": {
                    "budget_amount": bc.get("amount"),
                    "budget_strictness": bc.get("strictness"),
                    "travel_days": req.get("travel_days"),
                },
                "metadata": {
                    "city": req.get("city"),
                    "travel_days": req.get("travel_days"),
                    "party_total": party.get("total"),
                    "tier": bc.get("strictness"),
                    "source": "human_eval_30",
                },
            }
        )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
```

Create `eval/__init__.py` (empty file).

Run: `cd /Users/huangbaoxi/Code/Trip-planner-agent && python eval/build_dataset.py`
Expected: `wrote 30 rows -> .../eval/datasets/human_eval_30.jsonl`

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/eval/test_dataset.py
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval"))

DATASET = os.path.join(ROOT, "eval", "datasets", "human_eval_30.jsonl")


def test_dataset_rows_have_required_shape():
    rows = [json.loads(line) for line in open(DATASET, encoding="utf-8") if line.strip()]
    assert len(rows) == 30
    for row in rows:
        assert "request" in row["inputs"]
        req = row["inputs"]["request"]
        assert req.get("city")
        assert req.get("travel_days")
        assert "budget_amount" in row["outputs"]
        assert row["metadata"]["source"] == "human_eval_30"


def test_load_examples_maps_rows():
    import upload_dataset  # eval/upload_dataset.py via sys.path

    examples = upload_dataset.load_examples(DATASET)
    assert len(examples) == 30
    assert examples[0]["inputs"]["request"]["city"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/eval/test_dataset.py -v`
Expected: FAIL — `test_load_examples_maps_rows` errors with `ModuleNotFoundError: No module named 'upload_dataset'`.

- [ ] **Step 4: Implement `eval/upload_dataset.py`**

```python
"""Push the curated dataset to LangSmith (idempotent by dataset name)."""
from __future__ import annotations

import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets", "human_eval_30.jsonl")


def load_examples(path: str = DEFAULT_PATH) -> list[dict]:
    examples = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                examples.append(json.loads(line))
    return examples


def upload(dataset_name: str = "human_eval_30", path: str = DEFAULT_PATH) -> None:
    from langsmith import Client

    client = Client()
    examples = load_examples(path)

    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(dataset_name=dataset_name)

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[e["inputs"] for e in examples],
        outputs=[e.get("outputs") for e in examples],
        metadata=[e.get("metadata") for e in examples],
    )
    print(f"uploaded {len(examples)} examples to dataset '{dataset_name}'")


if __name__ == "__main__":
    upload()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/eval/test_dataset.py -v`
Expected: PASS (2 tests). (The `upload()` function itself is exercised manually with a real key; only `load_examples` is unit-tested.)

- [ ] **Step 6: Commit**

```bash
git add eval/__init__.py eval/build_dataset.py eval/datasets/human_eval_30.jsonl eval/upload_dataset.py backend/tests/eval/test_dataset.py
git commit -m "feat(eval): curated human_eval_30 dataset + LangSmith upload script"
```

---

### Task 5: Deterministic evaluators — metrics-derived

**Files:**
- Create: `eval/evaluators/__init__.py`
- Create: `eval/evaluators/deterministic.py`
- Test: `backend/tests/eval/test_deterministic_evaluators.py`

**Interfaces:**
- Consumes: `score_trip_plan_candidate` from `app.planner.rerank`; `TripPlan`, `TripRequest` from `app.models.schemas`.
- Produces (each `(run, example) -> dict` with keys `key`, `score`, optional `comment`):
  - `grounding_rate`, `budget_fit`, `budget_hard_ok`, `budget_arithmetic_ok`, `plan_success`
  - Helpers: `plan_from_run(run) -> TripPlan | None`, `request_from_example(example) -> TripRequest`, `context_from_run(run) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/eval/test_deterministic_evaluators.py
import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))

from app.models.schemas import TripRequest
from app.planner.output import create_fallback_plan


def _example():
    req = TripRequest(
        city="北京", start_date="2026-07-01", end_date="2026-07-03", travel_days=3,
        party={"adults": 2, "children": 0, "seniors": 0, "total": 2},
        budget_constraint={"amount": 6000, "strictness": "soft"},
        preferences=[], transportation="public", accommodation="hotel", free_text_input="",
    )
    return SimpleNamespace(inputs={"request": req.model_dump(mode="json")}, outputs={})


def _run(status="llm_success"):
    req = _example().inputs["request"]
    plan = create_fallback_plan(TripRequest(**req))
    return SimpleNamespace(
        outputs={"plan": plan.model_dump(mode="json"), "status": status, "planner_context": {"tool_snapshot": {}}}
    )


def test_plan_success_scores_one_for_llm_success():
    import deterministic
    res = deterministic.plan_success(_run("llm_success"), _example())
    assert res["key"] == "plan_success" and res["score"] == 1.0


def test_plan_success_scores_zero_for_fallback():
    import deterministic
    res = deterministic.plan_success(_run("fallback_success"), _example())
    assert res["score"] == 0.0


def test_budget_arithmetic_detects_mismatch():
    import deterministic
    run = _run()
    plan = run.outputs["plan"]
    plan["budget"]["total"] = plan["budget"]["total"] + 999  # break the sum
    res = deterministic.budget_arithmetic_ok(run, _example())
    assert res["score"] == 0.0


def test_grounding_rate_returns_float_between_0_and_1():
    import deterministic
    res = deterministic.grounding_rate(_run(), _example())
    assert 0.0 <= res["score"] <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/eval/test_deterministic_evaluators.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deterministic'`.

- [ ] **Step 3: Implement `eval/evaluators/deterministic.py`**

Create `eval/evaluators/__init__.py` (empty), then:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/eval/test_deterministic_evaluators.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add eval/evaluators/__init__.py eval/evaluators/deterministic.py backend/tests/eval/test_deterministic_evaluators.py
git commit -m "feat(eval): metrics-derived deterministic evaluators"
```

---

### Task 6: New deterministic checks — free tickets, hotel nights, hard constraints

**Files:**
- Modify: `eval/evaluators/deterministic.py` (append three evaluators + extend `METRIC_EVALUATORS`)
- Test: `backend/tests/eval/test_new_checks.py`

**Interfaces:**
- Consumes: `FREE_ATTRACTION_KEYWORDS`, `MUSEUM_TYPE_KEYWORDS` from `app.planner.pricing`.
- Produces: `free_ticket_violations`, `hotel_nights_ok`, `hard_constraint_ok` (same `(run, example) -> dict` contract); `METRIC_EVALUATORS` now includes all eight.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/eval/test_new_checks.py -v`
Expected: FAIL — `AttributeError: module 'deterministic' has no attribute 'free_ticket_violations'`.

- [ ] **Step 3: Append the three evaluators to `eval/evaluators/deterministic.py`**

```python
from app.planner.pricing import FREE_ATTRACTION_KEYWORDS, MUSEUM_TYPE_KEYWORDS

_FREE_KEYWORDS = list(FREE_ATTRACTION_KEYWORDS) + list(MUSEUM_TYPE_KEYWORDS)
_PORK_DISH_KEYWORDS = ["猪", "排骨", "小面", "烧腊", "叉烧", "回锅肉", "红烧肉",
                       "锅包肉", "火腿", "培根", "香肠", "腊肠", "卤肉"]
_NO_PORK_TRIGGERS = ["不吃猪", "无猪", "忌猪", "清真", "no pork", "不要猪", "穆斯林"]


def free_ticket_violations(run, example):
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


def hotel_nights_ok(run, example):
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


def _wants_no_pork(req) -> bool:
    prefs = " ".join(req.preferences or []) if isinstance(req.preferences, list) else str(req.preferences or "")
    text = f"{req.free_text_input or ''} {prefs}".lower()
    return any(trigger.lower() in text for trigger in _NO_PORK_TRIGGERS)


def hard_constraint_ok(run, example):
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
```

Extend the registry line at the bottom of the file:

```python
METRIC_EVALUATORS = [
    grounding_rate, budget_fit, budget_hard_ok, budget_arithmetic_ok, plan_success,
    free_ticket_violations, hotel_nights_ok, hard_constraint_ok,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/eval/test_new_checks.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add eval/evaluators/deterministic.py backend/tests/eval/test_new_checks.py
git commit -m "feat(eval): free-ticket, hotel-nights, hard-constraint evaluators"
```

---

### Task 7: LLM-as-judge evaluator (phase 2)

**Files:**
- Create: `eval/evaluators/llm_judge.py`
- Test: `backend/tests/eval/test_llm_judge.py`

**Interfaces:**
- Consumes: `extract_json_object` from `app.planner.output`; `plan_from_run`, `request_from_example` from `deterministic`.
- Produces:
  - `parse_judge(raw: str) -> tuple[float, str]` — returns `(score_0_to_5, reasoning)`
  - `build_judge_prompt(req: TripRequest, plan: TripPlan) -> str`
  - `make_llm_judge(invoke_fn=None)` — returns an evaluator `(run, example) -> dict` with key `llm_judge`; `invoke_fn(messages) -> str` is injectable for tests, defaults to the product LLM.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/eval/test_llm_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'llm_judge'`.

- [ ] **Step 3: Implement `eval/evaluators/llm_judge.py`**

```python
# eval/evaluators/llm_judge.py
"""LLM-as-judge evaluator. Scores delivered plan 0-5, normalized to [0,1]."""
from __future__ import annotations

from typing import Any, Callable

from app.models.schemas import TripPlan, TripRequest
from app.planner.output import extract_json_object

from deterministic import plan_from_run, request_from_example

_RUBRIC = (
    "你是挑剔但公正的旅行者。请仅评估这份行程计划本身：如果你真要照它出门，好用吗？\n"
    "从任务完成度、动线/体验、节奏、偏好与自由文本诉求契合度综合判断。\n"
    "先用3-5句证据说理，再打分。锚定：0无用 1严重不可用 2低于预期 3基本合格 4良好 5卓越。\n"
    "只输出一个 JSON：{\"reasoning\": \"...\", \"score\": <0-5整数>}。"
)


def build_judge_prompt(req: TripRequest, plan: TripPlan) -> str:
    return (
        f"{_RUBRIC}\n\n"
        f"用户请求：\n{req.model_dump_json(exclude_none=True)}\n\n"
        f"行程计划：\n{plan.model_dump_json(exclude_none=True)}\n"
    )


def parse_judge(raw: str) -> tuple[float, str]:
    try:
        obj = extract_json_object(raw)
    except Exception:
        return 0.0, f"unparseable judge output: {raw[:200]}"
    score = float(obj.get("score", 0) or 0)
    score = max(0.0, min(5.0, score))
    return score, str(obj.get("reasoning", ""))


def make_llm_judge(invoke_fn: Callable[[list[dict]], str] | None = None):
    if invoke_fn is None:
        from app.services.llm_service import get_llm

        _llm = get_llm()

        def invoke_fn(messages: list[dict]) -> str:  # noqa: F811
            return _llm.invoke(messages)

    def llm_judge(run: Any, example: Any) -> dict:
        plan = plan_from_run(run)
        if plan is None:
            return {"key": "llm_judge", "score": 0.0, "comment": "no plan"}
        req = request_from_example(example)
        prompt = build_judge_prompt(req, plan)
        raw = invoke_fn([{"role": "user", "content": prompt}])
        score, reason = parse_judge(raw)
        return {"key": "llm_judge", "score": round(score / 5.0, 4), "comment": reason}

    return llm_judge
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/eval/test_llm_judge.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add eval/evaluators/llm_judge.py backend/tests/eval/test_llm_judge.py
git commit -m "feat(eval): LLM-as-judge evaluator (phase 2)"
```

---

### Task 8: Experiment runner (`run_eval.py`) + README

**Files:**
- Create: `eval/run_eval.py`
- Create: `eval/README.md`
- Test: `backend/tests/eval/test_run_eval_smoke.py`

**Interfaces:**
- Consumes: `generate_trip_plan_detailed` from `app.graph.service`; `METRIC_EVALUATORS` from `deterministic`; `make_llm_judge` from `llm_judge`.
- Produces:
  - `build_target() -> Callable[[dict], dict]` — `inputs -> outputs` for langsmith
  - `run_target_safely(target, inputs) -> dict` — per-example error guard
  - `summarize(results: list[dict]) -> str` — markdown summary text
  - `main(argv=None) -> None` — CLI entrypoint

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/eval/test_run_eval_smoke.py
import os
import sys
from types import SimpleNamespace

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval"))
sys.path.insert(0, os.path.join(ROOT, "eval", "evaluators"))


def test_run_target_safely_wraps_errors():
    import run_eval

    def boom(inputs):
        raise RuntimeError("amap down")

    out = run_eval.run_target_safely(boom, {"request": {"city": "北京"}})
    assert out["status"] == "error"
    assert out["plan"] is None
    assert "amap down" in out["error"]


def test_summarize_reports_means():
    import run_eval
    results = [
        {"scores": {"grounding_rate": 1.0, "plan_success": 1.0}},
        {"scores": {"grounding_rate": 0.0, "plan_success": 1.0}},
    ]
    md = run_eval.summarize(results)
    assert "grounding_rate" in md and "0.5" in md
    assert "plan_success" in md and "1.0" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/eval/test_run_eval_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'run_eval'`.

- [ ] **Step 3: Implement `eval/run_eval.py`**

```python
# eval/run_eval.py
"""Run the live planner graph over the curated dataset and score plan quality.

Usage (from repo root):
    python eval/upload_dataset.py
    python eval/run_eval.py
    EVAL_ENABLE_LLM_JUDGE=1 python eval/run_eval.py --judge
    python eval/run_eval.py --limit 3
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT / "eval" / "evaluators"))

try:
    from dotenv import load_dotenv

    load_dotenv(BACKEND / ".env")
except Exception:
    pass


def build_target():
    from app.graph.service import generate_trip_plan_detailed
    from app.models.schemas import TripRequest

    def target(inputs: dict) -> dict:
        return generate_trip_plan_detailed(TripRequest(**inputs["request"]))

    return target


def run_target_safely(target, inputs: dict) -> dict:
    try:
        return target(inputs)
    except Exception as exc:  # one bad example must not void the run
        return {"plan": None, "status": "error", "planner_context": {}, "failures": [], "error": str(exc)}


def _evaluators(use_judge: bool):
    from deterministic import METRIC_EVALUATORS

    evaluators = list(METRIC_EVALUATORS)
    if use_judge:
        from llm_judge import make_llm_judge

        evaluators.append(make_llm_judge())
    return evaluators


def summarize(results: list[dict]) -> str:
    keys: list[str] = []
    for r in results:
        for k in r.get("scores", {}):
            if k not in keys:
                keys.append(k)
    lines = ["# Eval summary", "", f"examples: {len(results)}", "", "| metric | mean |", "| --- | --- |"]
    for k in keys:
        vals = [r["scores"][k] for r in results if k in r.get("scores", {}) and r["scores"][k] is not None]
        mean = round(sum(vals) / len(vals), 4) if vals else 0.0
        lines.append(f"| {k} | {mean} |")
    return "\n".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="human_eval_30")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--judge", action="store_true",
                        help="enable LLM-as-judge (or set EVAL_ENABLE_LLM_JUDGE=1)")
    args = parser.parse_args(argv)

    use_judge = args.judge or os.getenv("EVAL_ENABLE_LLM_JUDGE", "").strip().lower() in {"1", "true", "yes"}

    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("LANGSMITH_API_KEY is required to run the experiment.")

    from langsmith import Client, evaluate

    client = Client()
    target = build_target()

    def _wrapped(inputs: dict) -> dict:
        return run_target_safely(target, inputs)

    experiment = evaluate(
        _wrapped,
        data=client.list_examples(dataset_name=args.dataset, limit=args.limit),
        evaluators=_evaluators(use_judge),
        experiment_prefix="trip-planner-eval",
    )

    # Persist a local markdown summary mirroring the report style.
    results = []
    for row in experiment:
        scores = {r.key: r.score for r in row["evaluation_results"]["results"]}
        results.append({"scores": scores})

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "out" / "eval" / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(summarize(results), encoding="utf-8")
    print(f"summary -> {out_dir / 'summary.md'}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write `eval/README.md`**

```markdown
# Trip Planner — LangSmith Eval System

Product-level observability + plan-quality evaluation. Separate from the
checkpoint/DPO-focused `training/scripts/eval/`.

## Setup

Add to `backend/.env`:

```
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=ls-...
LANGSMITH_PROJECT=trip-planner
# optional self-hosted: LANGSMITH_ENDPOINT=https://...
```

Real Amap + LLM keys are also required for live runs (the offline unit tests
under `backend/tests/eval/` and `backend/tests/observability/` are not).

## Observability

Once `LANGSMITH_TRACING=true`, every `/trip/plan` request traces automatically:
end-to-end latency, per-node spans, LLM tokens/cost (via `wrap_openai`), Amap
tool spans, plus run metadata (status, failure rows, attempt count).

## Evaluation

```bash
python eval/build_dataset.py        # one-time: freeze dataset from out/human_eval
python eval/upload_dataset.py       # push "human_eval_30" to LangSmith
python eval/run_eval.py             # phase-1 deterministic evaluators
EVAL_ENABLE_LLM_JUDGE=1 python eval/run_eval.py --judge   # + LLM judge
python eval/run_eval.py --limit 3   # smoke a few examples
```

Local markdown summary lands in `out/eval/<timestamp>/summary.md`; full
per-example scores live in the LangSmith experiment UI.

## Evaluators

Deterministic (phase 1, reuse `rerank.py`/`pricing.py`): `grounding_rate`,
`budget_fit`, `budget_hard_ok`, `budget_arithmetic_ok`, `plan_success`,
`free_ticket_violations`, `hotel_nights_ok`, `hard_constraint_ok`.
LLM-as-judge (phase 2, env-gated): `llm_judge`.
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/eval/test_run_eval_smoke.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Run the full backend suite + compile check**

Run: `cd backend && python -m py_compile $(git ls-files '../eval/*.py') && pytest -q`
Expected: compile OK; full suite PASS (69 existing + new tests).

- [ ] **Step 7: Commit**

```bash
git add eval/run_eval.py eval/README.md backend/tests/eval/test_run_eval_smoke.py
git commit -m "feat(eval): langsmith experiment runner + README"
```

---

## Notes & deviations from the spec

- **`@traceable` placement**: the spec mentioned decorating the 3 Amap collectors and the LLM call sites. Because those collectors already run as separate LangGraph fan-out nodes (auto-traced) and the LLM is captured via `wrap_openai`, this plan instruments the single low-level `AmapClient.get` (tool spans) and wraps the whole graph run in one `@traceable` chain (`_run_graph`) that also attaches failure metadata. All spec observability outcomes (per-node latency, tokens/cost, errors, failure rows) are met with less surface area.
- **`hard_constraint_ok`**: implemented as a self-contained dates/days/dietary scan rather than importing the critic layer, to avoid coupling the eval package to `agents/critic.py` internals. Same checks the spec listed.
- **Thresholds** are reused as-is from `rerank.py`; tightening is future work (per spec §11).

## Self-review

- **Spec coverage:** tracing seam (T1) ✓; wrap_openai tokens + tool spans + init (T2) ✓; eval entry point exposing planner_context + failure metadata (T3) ✓; curated ~30 dataset + upload (T4) ✓; deterministic evaluators reusing rerank/critic logic (T5, T6) ✓; LLM-judge phase 2, separately gated (T7) ✓; runner + per-example error guard + local summary + README + env config (T8) ✓; `hotel_distance_ok` excluded ✓.
- **Placeholder scan:** the one intentional placeholder line in T3 Step 1 is called out with removal instructions; no other TBD/TODO.
- **Type consistency:** `(run, example) -> {"key","score","comment"}` evaluator contract is uniform across T5–T7; `run.outputs` shape `{"plan","status","planner_context","failures"}` produced by `generate_trip_plan_detailed` (T3) matches every evaluator's reader; `METRIC_EVALUATORS` defined in T5 and extended in T6 is consumed in T8.
