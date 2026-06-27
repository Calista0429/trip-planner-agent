# LangSmith Eval System — Design

- **Date:** 2026-06-27
- **Status:** Approved (design); pending spec review
- **Author:** brainstormed with Claude Code
- **Scope:** Add a LangSmith-based observability + evaluation system to the trip planner.

## 1. Goal & Motivation

Use **LangSmith** to (a) **observe** the live planner — latency, errors, token/cost
per run — and (b) **evaluate** plan quality on a fixed dataset with repeatable,
comparable scores.

Both internal evaluation reports (`EVALUATION_REPORT.md`, `HUMAN_EVAL_REPORT.md`)
named the same #1 gap: there is no repeatable **product-level plan-quality** eval.
The frozen sets `training/data/planner/eval{,_hard}` store only **inputs** and their
`summary.json` measures *context-assembly* success, not delivered-plan quality. The
existing `training/scripts/eval/` machinery is checkpoint/DPO-focused, not a
product-quality harness. This system fills that gap and adds live observability.

Non-goals: replacing the training-side eval; redefining metric thresholds (we reuse
current ones and tighten later); changing planner behavior in the default flow.

## 2. Approach (selected: A — Native LangSmith, thin integration)

- **Tracing/observability**: fully env-gated (`LANGSMITH_TRACING=true`). LangGraph
  nodes auto-trace; we add `langsmith.wrappers.wrap_openai()` on the wrapper's inner
  OpenAI client to capture tokens/cost/latency, and `@traceable` on the Amap
  collectors + LLM call sites + rerank so spans show with detail. Zero behavior
  change when the env var is off — same philosophy as the existing RAG/Critic gates.
- **Evaluation**: a standalone `eval/` package using `langsmith.evaluate()`. Target =
  the live `generate_trip_plan` over a curated dataset; evaluators are thin adapters
  over metrics **already** in `rerank.py`/`critic.py` (phase 1, deterministic) plus an
  LLM-as-judge (phase 2). Latency/tokens/errors come for free from the traced runs.

Rejected: **B** (offline-only eval, no live tracing) — loses the "观测" half of the
goal. **C** (custom callback/tracer) — redundant with native LangSmith, overkill.

## 3. Components & File Layout

Nothing in the default product path changes; all additions are env-gated.

```
backend/app/
  graph/runtime.py          # MODIFY: wrap inner OpenAI client with wrap_openai() when tracing on
  graph/graph.py            # MODIFY: @traceable on llm.invoke call sites (generate/revise)
  planner/context.py        # MODIFY: @traceable on the 3 Amap collectors
  observability/
    __init__.py
    tracing.py              # NEW: init_tracing() — reads env, sets up LangSmith, no-op if off

eval/                       # NEW top-level package (product-level; distinct from training/scripts/eval)
  __init__.py
  datasets/
    human_eval_30.jsonl     # NEW: ~30 curated requests (frozen from the human-eval set)
  upload_dataset.py         # NEW: push dataset to LangSmith (idempotent, by name)
  evaluators/
    __init__.py
    deterministic.py        # NEW: thin adapters over rerank.py/critic.py metrics
    llm_judge.py            # NEW: LLM-as-judge rubric evaluator (phase 2)
  run_eval.py               # NEW: langsmith.evaluate() runner — CLI entrypoint
  README.md                 # NEW: setup + how to run

backend/requirements.txt    # MODIFY: add `langsmith`
```

### Boundaries

- `observability/tracing.py` — the single seam that knows LangSmith env config.
  Everything else just calls `init_tracing()` and uses `@traceable`. When
  `LANGSMITH_TRACING` is unset/false it is a **complete no-op**: decorators pass
  through, no client is created, `wrap_openai` is skipped.
- `eval/evaluators/deterministic.py` — pure functions `(run, example) -> {key, score, comment}`.
  They import and reuse `recompute_budget_from_selected_items`, the rerank metrics
  dict, and the critic deterministic checks. **No new scoring logic** — only adaptation
  to the LangSmith evaluator signature.
- `eval/run_eval.py` — the only orchestrator: wires dataset + target + evaluators.

Placement: `eval/` lives at **repo root** (a first-class product concern),
deliberately separate from the checkpoint/DPO-focused `training/scripts/eval/`.

## 4. Tracing / Observability Data Flow

```
POST /trip/plan(/stream)
  └─ generate_trip_plan()                    # root trace (LangGraph run, auto-traced)
       ├─ collect: attractions  @traceable   # span: latency, Amap call detail
       ├─ collect: weather      @traceable
       ├─ collect: hotels       @traceable
       ├─ collect: rag_notes    @traceable   # if RAG on
       ├─ merge_context / build_query        # auto span
       ├─ generate (llm.invoke) @traceable   # span + wrap_openai child = tokens/cost/latency
       │     └─ retry/temperature bumps = sibling spans
       ├─ rerank                @traceable   # scores attached as metadata
       └─ critic/revise         @traceable   # if critic on
```

### Token capture

`HelloAgentsLLM.invoke()` (`hello_agents/core/llm.py:320`) returns only
`response.choices[0].message.content` and **discards `response.usage`**. So tokens are
not surfaced today. Fix: patch the **inner OpenAI client** once at runtime
construction, gated:

```python
# runtime.py, inside build_default_runtime():
if tracing_enabled():
    from langsmith.wrappers import wrap_openai
    primary_llm._client = wrap_openai(primary_llm._client)
    fallback_llm._client = wrap_openai(fallback_llm._client)
```

`wrap_openai` intercepts `chat.completions.create`, reporting prompt/completion/total
tokens, cost, and latency into the current trace — without forking `hello_agents` or
changing `invoke()`'s return value. The graph keeps reading `.content` unchanged.

### Operational metrics → LangSmith

| Metric | Source | Where in LangSmith |
|---|---|---|
| Plan-generation latency (end-to-end) | root run duration | run latency |
| Per-node latency | `@traceable` spans | child span durations |
| Errors / failures | exceptions + existing `planner_failures` rows as run metadata/tags | run status = error + tags |
| Tokens (prompt/completion/total) | `wrap_openai` | per-LLM-call usage, summed on root |
| Cost | `wrap_openai` (model pricing) | run cost |
| Retry count / fallback used / preference_reason | final state → run metadata | run metadata (filterable) |

**Failure rows**: the data currently written to `planner_failures.jsonl` is attached
to the run as metadata/tags so errors are queryable in LangSmith alongside
latency/tokens.

**Failsafe**: `init_tracing()` is called once at app startup. If `langsmith` is not
installed or env is off, `@traceable` degrades to a transparent pass-through and
`wrap_openai` is skipped — the product runs identically with zero added latency.

## 5. Evaluators & Dataset

### Dataset schema (`eval/datasets/human_eval_30.jsonl`, one row per example)

```jsonc
{
  "inputs":   { "request": { /* full TripRequest: city, dates, party, budget_constraint, preferences, free_text_input ... */ } },
  "outputs":  { "budget_amount": 9800, "budget_strictness": "hard", "travel_days": 3 },
  "metadata": { "city": "昆明", "persona": "2友人", "tier": "premium", "source": "human_eval_30" }
}
```

`request` is the source of truth; `outputs`/`metadata` carry just enough for
evaluators to judge against (budget target, day count) and for slice reports
(`tier`/`persona`). The ~30 rows are frozen from the existing human-eval requests.

### Target function (`run_eval.py`)

```python
lambda inputs: generate_trip_plan(TripRequest(**inputs["request"]))  # -> {plan, status, message}
```

Runs the real graph (real Amap + LLM), so each eval example also produces a live trace.

### Phase 1 — deterministic evaluators (`evaluators/deterministic.py`)

Each `(run, example) -> {key, score, comment}`, reusing existing code. No new
thresholds.

| Evaluator key | Reuses | Score 1.0 means |
|---|---|---|
| `grounding_rate` | rerank metrics `*_grounding_rate` | all POIs/hotels/meals exist in Amap snapshot |
| `budget_arithmetic_ok` | `budget_math_mismatch` check | `total == sum(4 parts)` |
| `budget_fit` | `budget_fit_details` | recomputed total lands in target band (catches underspend) |
| `budget_hard_ok` | `budget_hard_constraint_ok` | not over a hard cap |
| `free_ticket_violations` | new check vs `attraction_price_table.json` + free keywords | 0 fabricated tickets on free POIs |
| `hotel_nights_ok` | recompute hotels vs trip nights | `total_hotels == nightly×actual_nights`, no departure-day hotel |
| `hard_constraint_ok` | critic deterministic layer (dates/days/no-pork keyword scan) | all hard constraints met |
| `plan_success` | graph `status` | got an `llm_success` plan, not fallback |

These map 1:1 to the problems the two reports raised, so the eval directly tracks
whether those issues regress or improve. **`hotel_distance_ok` is intentionally
excluded from the first version.**

### Phase 2 — LLM-as-judge (`evaluators/llm_judge.py`)

One evaluator scoring 0–5 on the same rubric dimensions the human-eval used (task
completion, experience/routing, pacing, preference fit), "先说理后打分", returning
score + reasoning as comment. Env-gated separately (`EVAL_ENABLE_LLM_JUDGE=1`) so
phase-1 runs stay free/fast.

### Aggregate output

`evaluate()` produces per-example scores + experiment averages. `run_eval.py` also
dumps a local markdown summary (mean per evaluator, sliced by `tier`/`persona`) to
`out/eval/<timestamp>/`, echoing the existing report style.

## 6. Config

All env-gated, off by default.

| Env var | Purpose |
|---|---|
| `LANGSMITH_TRACING` | master switch for live tracing + `wrap_openai` |
| `LANGSMITH_API_KEY` | LangSmith cloud auth |
| `LANGSMITH_PROJECT` | project name for traces (default `trip-planner`) |
| `LANGSMITH_ENDPOINT` | optional, self-hosted endpoint |
| `EVAL_ENABLE_LLM_JUDGE` | turn on the phase-2 judge during `evaluate()` |

## 7. Invocation

```bash
python eval/upload_dataset.py                              # idempotent: create/update "human_eval_30"
python eval/run_eval.py                                    # phase-1 deterministic over the dataset
EVAL_ENABLE_LLM_JUDGE=1 python eval/run_eval.py --judge    # + LLM judge
python eval/run_eval.py --limit 3                          # smoke test a few examples
```

Live tracing needs no command — once `LANGSMITH_TRACING=true` in `.env`, every real
`/trip/plan` request traces automatically.

## 8. Error Handling

- Missing `langsmith` package or `LANGSMITH_API_KEY` → `init_tracing()` logs one
  warning and no-ops; product unaffected.
- `run_eval.py` with no key → fails fast with a clear message (cannot run without
  LangSmith).
- A single example erroring mid-experiment → caught per-example, recorded as
  `plan_success=0` + error comment, experiment continues (mirrors the graph's "always
  return a result" invariant).
- Evaluators never raise into the experiment: any exception → score `None` + comment,
  so one bad metric can't void the run.

## 9. Testing

- `backend/tests/` — unit tests per deterministic evaluator with synthetic
  `(run, example)` pairs (known-good plan → 1.0; planted budget mismatch / fabricated
  free ticket → <1.0). No network — canned plans.
- `init_tracing()` test: env off → decorators pass-through, `wrap_openai` not called
  (assert no client mutation).
- `run_eval.py` smoke: fake runtime (offline graph) + a 2-row dataset stub so wiring
  is tested without LangSmith/Amap. Real end-to-end run is manual (needs keys),
  documented in `eval/README.md`.
- No golden changes — this work is additive.

## 10. Prerequisites

- A LangSmith account + `LANGSMITH_API_KEY`.
- Real Amap + LLM keys for live `run_eval.py` (offline tests don't need them).

## 11. Open Questions / Future Work

- Tighten deterministic thresholds once a baseline run exists (currently reuse
  lenient existing ones).
- Add `hotel_distance_ok` evaluator in a later iteration (Amap coords available).
- Optional: a larger sampled dataset from `eval`/`eval_hard` for periodic deep runs.
- Optional: CI gate on phase-1 scores once the baseline is stable.
