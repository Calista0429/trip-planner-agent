#!/usr/bin/env python3
"""Prepare anti-leak Best-of-N record pools from existing training records."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_SOURCES = [
    "training/data/planner/sft/260509/main_clean/records_train.jsonl",
    "training/data/planner/sft/260511_mimo_realbudget_usage_comfortable500_w50/records.jsonl",
    "training/data/planner/sft/260511_mimo_realbudget_usage_premium200_w50/records.jsonl",
    "training/data/planner/sft/260511_mimo_budget_usage_validate100_w50_dedup100/records.jsonl",
    "training/data/planner/dpo/prompt_source/records.jsonl",
    "training/data/planner/sft_realbudget_runs/260508_main1000_w20_gate1_thinking_off/records.jsonl",
    "training/data/planner/sft_realbudget_runs/260509_supplement_standard520_w50_no_none/records.jsonl",
    "training/data/planner/sft_realbudget_runs/260509_supplement_comfortable245_w50_no_none/records.jsonl",
    "training/data/planner/sft_realbudget_runs/260509_supplement_premium157_w50_no_none/records.jsonl",
]

DEFAULT_EVAL_SOURCES = [
    "training/data/planner/eval/records.jsonl",
    "training/data/planner/eval_hard/records.jsonl",
]

DEFAULT_QUOTAS = {
    "budget_preference_recomputed": 500,
    "hard_complex_budget": 300,
    "meal_attraction_diversity": 250,
    "budget_arithmetic_ledger": 150,
}


def project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid json") from exc
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_signature(row: dict[str, Any]) -> str:
    request = row.get("request") or (row.get("planner_context") or {}).get("request") or {}
    stable = {
        "city": request.get("city"),
        "start_date": request.get("start_date"),
        "end_date": request.get("end_date"),
        "travel_days": request.get("travel_days"),
        "transportation": request.get("transportation"),
        "accommodation": request.get("accommodation"),
        "preferences": request.get("preferences") or [],
        "free_text_input": request.get("free_text_input"),
        "party": request.get("party") or {},
        "budget_constraint": request.get("budget_constraint") or {},
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def control(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("control_spec") or {}


def request(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("request") or {}


def budget_level(row: dict[str, Any]) -> str:
    req = request(row)
    return str(control(row).get("budget_level") or (req.get("budget_constraint") or {}).get("budget_level") or "unknown")


def strictness(row: dict[str, Any]) -> str:
    req = request(row)
    return str(control(row).get("budget_strictness") or (req.get("budget_constraint") or {}).get("strictness") or "none")


def party_total(row: dict[str, Any]) -> int:
    party = request(row).get("party") or {}
    try:
        return int(party.get("total") or 1)
    except (TypeError, ValueError):
        return 1


def travel_days(row: dict[str, Any]) -> int:
    try:
        return int(request(row).get("travel_days") or 0)
    except (TypeError, ValueError):
        return 0


def city_tier(row: dict[str, Any]) -> str:
    return str(control(row).get("city_tier") or "unknown")


def diet(row: dict[str, Any]) -> str:
    return str(control(row).get("diet") or "无")


def text_blob(row: dict[str, Any]) -> str:
    req = request(row)
    values: list[str] = []
    for key in ("accommodation", "free_text_input", "transportation"):
        if req.get(key):
            values.append(str(req[key]))
    values.extend(str(item) for item in (req.get("preferences") or []))
    values.extend(str(item) for item in (control(row).get("positive_preferences") or []))
    values.extend(str(item) for item in (control(row).get("negative_constraints") or []))
    values.append(diet(row))
    return " ".join(values)


def has_budget(row: dict[str, Any]) -> bool:
    budget = request(row).get("budget_constraint") or {}
    return budget.get("amount") is not None and budget_level(row) != "unknown"


def has_budget_fit_override(row: dict[str, Any]) -> bool:
    return bool(control(row).get("budget_fit_policy_override"))


def category_match(row: dict[str, Any], category: str) -> bool:
    level = budget_level(row)
    strict = strictness(row)
    days = travel_days(row)
    party = party_total(row)
    text = text_blob(row)

    if category == "budget_preference_recomputed":
        return (
            has_budget(row)
            and strict == "soft"
            and level in {"standard", "comfortable", "premium", "luxury"}
            and (has_budget_fit_override(row) or "预算" in text or "用足" in text or "低配" in text)
        )

    if category == "hard_complex_budget":
        return has_budget(row) and (
            strict == "hard"
            or (party >= 3 and days >= 4)
            or (level in {"comfortable", "premium", "luxury"} and days >= 4)
        )

    if category == "meal_attraction_diversity":
        food_terms = ("美食", "特色餐厅", "小吃", "本地菜", "素食", "清真", "海鲜", "少辣", "清淡")
        return has_budget(row) and (
            days >= 4
            or city_tier(row) == "long_tail"
            or diet(row) not in {"", "无", "none", "unknown"}
            or any(term in text for term in food_terms)
        )

    if category == "budget_arithmetic_ledger":
        accommodation = str(request(row).get("accommodation") or "")
        lodging = any(term in accommodation for term in ("酒店", "民宿", "客栈", "住宿"))
        return has_budget(row) and (party >= 2 or days >= 3 or lodging)

    raise KeyError(category)


def load_pool(source_paths: list[Path], eval_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eval_signatures = set()
    for path in eval_paths:
        if not path.exists():
            continue
        for row in read_jsonl(path):
            eval_signatures.add(request_signature(row))

    pool: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    source_seen = Counter()
    source_selected = Counter()
    skipped = Counter()

    for source_path in source_paths:
        if not source_path.exists():
            skipped[f"missing_source:{source_path}"] += 1
            continue
        rows = read_jsonl(source_path)
        source_seen[str(source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path)] += len(rows)
        for row in rows:
            if not row.get("record_id") or not row.get("planner_query"):
                skipped["missing_prompt_or_record_id"] += 1
                continue
            signature = request_signature(row)
            if signature in eval_signatures:
                skipped["eval_exact_request_overlap"] += 1
                continue
            if signature in seen_signatures:
                skipped["duplicate_request"] += 1
                continue
            seen_signatures.add(signature)
            item = dict(row)
            item["_bestofn_source_path"] = str(
                source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path
            )
            pool.append(item)
            source_selected[item["_bestofn_source_path"]] += 1

    summary = {
        "pool_after_dedup": len(pool),
        "source_rows": dict(source_seen),
        "source_pool_after_dedup": dict(source_selected),
        "skipped": dict(skipped),
    }
    return pool, summary


def choose_records(pool: list[dict[str, Any]], quotas: dict[str, int], seed: int, limit: int) -> tuple[list[dict[str, Any]], Counter]:
    rng = random.Random(seed)
    remaining = list(pool)
    rng.shuffle(remaining)
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    category_counts: Counter = Counter()

    def take(category: str, quota: int) -> None:
        nonlocal remaining
        matches = [row for row in remaining if category_match(row, category)]
        rng.shuffle(matches)
        chosen = matches[: max(0, quota)]
        chosen_keys = {request_signature(row) for row in chosen}
        for row in chosen:
            if request_signature(row) in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(request_signature(row))
            category_counts[category] += 1
        remaining = [row for row in remaining if request_signature(row) not in chosen_keys]

    for category, quota in quotas.items():
        if len(selected) >= limit:
            break
        take(category, min(quota, limit - len(selected)))

    if len(selected) < limit:
        for row in remaining:
            if request_signature(row) in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(request_signature(row))
            category_counts["fill_other"] += 1
            if len(selected) >= limit:
                break

    return selected[:limit], category_counts


def distribution(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    keys = {
        "budget_level": budget_level,
        "strictness": strictness,
        "party_total": lambda row: str(party_total(row)),
        "travel_days": lambda row: str(travel_days(row)),
        "city_tier": city_tier,
        "diet": diet,
        "accommodation": lambda row: str(request(row).get("accommodation") or "unknown"),
    }
    result: dict[str, dict[str, int]] = {}
    for key, getter in keys.items():
        result[key] = dict(Counter(getter(row) for row in rows))
    return result


def parse_quota(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("quota must be CATEGORY=COUNT")
    key, count = value.split("=", 1)
    try:
        return key, int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quota count must be an integer") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare anti-leak Best-of-N records.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=1200)
    parser.add_argument("--seed", type=int, default=20260512)
    parser.add_argument("--id-prefix", default="bestofn_anti_leak1200")
    parser.add_argument("--source", action="append", default=None, help="Record source jsonl. Can be repeated.")
    parser.add_argument("--eval-source", action="append", default=None, help="Frozen eval jsonl to exclude. Can be repeated.")
    parser.add_argument("--quota", type=parse_quota, action="append", default=None, help="CATEGORY=COUNT. Can be repeated.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = [project_path(path) for path in (args.source or DEFAULT_SOURCES)]
    eval_sources = [project_path(path) for path in (args.eval_source or DEFAULT_EVAL_SOURCES)]
    quotas = dict(DEFAULT_QUOTAS)
    if args.quota:
        quotas = dict(args.quota)

    pool, pool_summary = load_pool(sources, eval_sources)
    selected, category_counts = choose_records(pool, quotas, args.seed, args.limit)

    output_rows: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        original_record_id = row.get("record_id")
        source_path = row.pop("_bestofn_source_path", None)
        item = dict(row)
        item["record_id"] = f"{args.id_prefix}_{index:06d}__{original_record_id}"
        metadata = dict(item.get("metadata") or {})
        metadata["bestofn_source_record_id"] = original_record_id
        if source_path:
            metadata["bestofn_source_path"] = source_path
        item["metadata"] = metadata
        output_rows.append(item)

    write_jsonl(args.output, output_rows)
    summary = {
        "output": str(args.output),
        "selected": len(output_rows),
        "limit": args.limit,
        "seed": args.seed,
        "id_prefix": args.id_prefix,
        "quotas": quotas,
        "category_counts": dict(category_counts),
        "distribution": distribution(output_rows),
        **pool_summary,
    }
    summary_path = args.summary_output or (args.output.parent / "records_selection_summary.json")
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
