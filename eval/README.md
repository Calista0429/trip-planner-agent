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
