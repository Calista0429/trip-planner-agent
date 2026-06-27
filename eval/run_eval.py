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
