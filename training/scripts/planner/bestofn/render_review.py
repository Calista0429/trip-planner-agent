#!/usr/bin/env python3
"""Render a human-readable Best-of-N review Markdown."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LEGACY_SCRIPTS_DIR = PROJECT_ROOT / "training/scripts/eval"
if not LEGACY_SCRIPTS_DIR.exists():
    LEGACY_SCRIPTS_DIR = PROJECT_ROOT / "training/scripts/eval"
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(LEGACY_SCRIPTS_DIR))

from eval_utils import read_jsonl  # noqa: E402


DEFAULT_PROMPTS = PROJECT_ROOT / "training/data/planner/bestofn/260511_smoke20_vllm10/prompts.jsonl"
DEFAULT_CANDIDATES = PROJECT_ROOT / "training/data/planner/bestofn/260511_smoke20_vllm10/candidates.jsonl"
DEFAULT_SELECTED = PROJECT_ROOT / "training/data/planner/bestofn/260511_smoke20_vllm10/selected.jsonl"
DEFAULT_SUMMARY = PROJECT_ROOT / "training/data/planner/bestofn/260511_smoke20_vllm10/bestofn_summary.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "training/data/planner/bestofn/260511_smoke20_vllm10/review.md"


CORE_METRICS = [
    "sft_hard_pass",
    "dpo_soft_pass",
    "dpo_soft_recomputed_budget_pass",
    "recomputed_budget_fit_ok",
    "budget_preference_aligned",
    "budget_relationship_ok",
    "meal_cost_scale_ok",
    "meal_diversity_ok",
    "attraction_diversity_ok",
    "meal_grounding_ok",
    "attraction_grounding_ok",
    "hotel_grounding_ok",
]


def load_json(path: Path) -> Any:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def truncate(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def yes(value: Any) -> str:
    if value is True:
        return "Y"
    if value is False:
        return "N"
    return "-"


def error_text(candidate: dict[str, Any], limit: int = 5) -> str:
    errors = []
    for item in candidate.get("rule_errors") or []:
        kind = item.get("type") or item.get("stage") or "unknown"
        errors.append(str(kind))
    if not errors:
        return ""
    counts: dict[str, int] = {}
    for kind in errors:
        counts[kind] = counts.get(kind, 0) + 1
    parts = [f"{kind}x{count}" if count > 1 else kind for kind, count in counts.items()]
    return ", ".join(parts[:limit])


def selected_error_text(row: dict[str, Any], limit: int = 6) -> str:
    errors = []
    for item in row.get("selected_errors") or []:
        errors.append(str(item.get("type") or item.get("stage") or "unknown"))
    return ", ".join(errors[:limit])


def candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    metrics = candidate.get("rule_metrics") or {}
    generation = candidate.get("generation_meta") or {}
    return {
        "id": candidate.get("candidate_id", ""),
        "temp": candidate.get("temperature"),
        "score": candidate.get("bestofn_score"),
        "hard": metrics.get("sft_hard_pass"),
        "soft": metrics.get("dpo_soft_pass"),
        "budget_fit": metrics.get("recomputed_budget_fit_ok"),
        "budget_pref": metrics.get("budget_preference_aligned"),
        "budget_rel": metrics.get("budget_relationship_ok"),
        "meal_scale": metrics.get("meal_cost_scale_ok"),
        "meal_div": metrics.get("meal_diversity_ok"),
        "attr_div": metrics.get("attraction_diversity_ok"),
        "schema": metrics.get("schema_ok"),
        "finish": generation.get("finish_reason", ""),
        "chars": generation.get("output_chars", 0),
        "errors": error_text(candidate),
    }


def make_request_text(prompt_row: dict[str, Any]) -> str:
    request = prompt_row.get("request") or {}
    metadata = prompt_row.get("metadata") or {}
    bits = [
        f"{request.get('city')} {request.get('start_date')}->{request.get('end_date')}",
        f"{request.get('travel_days')}天",
        f"{metadata.get('budget_level')}",
        f"{metadata.get('companion_type')}",
        f"{metadata.get('city_tier')}",
        f"{metadata.get('weather_bucket')}",
    ]
    free_text = truncate(request.get("free_text_input", ""), 180)
    return " / ".join(str(bit) for bit in bits if bit) + f"\n\n> {free_text}"


def render(args: argparse.Namespace) -> str:
    prompt_map = {row["prompt_id"]: row for row in read_jsonl(args.prompts)}
    candidate_map = {row["prompt_id"]: row for row in read_jsonl(args.candidates)}
    selected_rows = read_jsonl(args.selected)
    summary = load_json(args.summary)

    lines = [
        "# Best-of-N Review\n\n",
        "## Summary\n\n",
        "```json\n",
        json.dumps(summary, ensure_ascii=False, indent=2),
        "\n```\n\n",
        "Core columns: hard=`sft_hard_pass`, soft=`dpo_soft_pass`, fit=`recomputed_budget_fit_ok`, "
        "pref=`budget_preference_aligned`, rel=`budget_relationship_ok`, meal_scale=`meal_cost_scale_ok`, "
        "meal_div/attr_div are diversity checks.\n\n",
    ]

    for index, selected in enumerate(selected_rows, start=1):
        prompt_id = selected.get("prompt_id")
        prompt_row = prompt_map.get(prompt_id, {})
        candidate_row = candidate_map.get(prompt_id, {})
        candidates_by_id = {item.get("candidate_id"): item for item in candidate_row.get("candidates") or []}
        selected_id = selected.get("selected_candidate_id")
        rejected_id = selected.get("rejected_candidate_id")

        for item in candidates_by_id.values():
            score_row = next((row for row in selected.get("candidate_scores") or [] if row.get("candidate_id") == item.get("candidate_id")), {})
            item["bestofn_score"] = score_row.get("score")

        lines.append(f"## {index}. {prompt_id}\n\n")
        lines.append(make_request_text(prompt_row) + "\n\n")
        lines.append(
            f"- selected: `{selected_id}` score={selected.get('selected_score')} "
            f"hard={yes(selected.get('selected_hard_pass'))}\n"
        )
        if rejected_id:
            lines.append(f"- rejected: `{rejected_id}` score={selected.get('rejected_score')}\n")
        if selected.get("selected_hard_pass") is not True:
            lines.append(f"- selected errors: {selected_error_text(selected)}\n")
        lines.append("\n")

        lines.append("| candidate | score | temp | hard | soft | fit | pref | rel | meal_scale | meal_div | attr_div | schema | errors |\n")
        lines.append("| --- | ---: | ---: | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n")
        sorted_candidates = sorted(candidates_by_id.values(), key=lambda item: item.get("bestofn_score") or -9999, reverse=True)
        for candidate in sorted_candidates:
            row = candidate_summary(candidate)
            label = row["id"]
            if label == selected_id:
                label = f"**{label}**"
            elif label == rejected_id:
                label = f"{label} (rej)"
            lines.append(
                f"| `{label}` | {row['score']} | {row['temp']} | {yes(row['hard'])} | {yes(row['soft'])} | "
                f"{yes(row['budget_fit'])} | {yes(row['budget_pref'])} | {yes(row['budget_rel'])} | "
                f"{yes(row['meal_scale'])} | {yes(row['meal_div'])} | {yes(row['attr_div'])} | "
                f"{yes(row['schema'])} | {truncate(row['errors'], 90)} |\n"
            )

        selected_candidate = candidates_by_id.get(selected_id, {})
        output = selected_candidate.get("output_text") or selected.get("selected_output") or ""
        lines.append("\n<details><summary>Selected output preview</summary>\n\n")
        lines.append("```json\n")
        lines.append(truncate(output, args.preview_chars))
        lines.append("\n```\n\n</details>\n\n")

    return "".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render Best-of-N review Markdown.")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--selected", type=Path, default=DEFAULT_SELECTED)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--preview-chars", type=int, default=1800)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    text = render(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
