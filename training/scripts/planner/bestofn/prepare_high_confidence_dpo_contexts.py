#!/usr/bin/env python3
"""Prepare high-confidence DPO context records with a fixed issue mix.

This script only builds the prompt/context pool. Candidate generation, judging,
and chosen/rejected pair construction should happen in later steps against this
stable pool.
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[4]

DEFAULT_SOURCES = [
    "training/data/planner/sft/260509/main_clean/records_train.jsonl",
    "training/data/planner/sft/260511_mimo_realbudget_usage_comfortable500_w50/records.jsonl",
    "training/data/planner/sft/260511_mimo_realbudget_usage_premium200_w50/records.jsonl",
    "training/data/planner/sft/260511_mimo_realbudget_usage_validate100_w50/records.jsonl",
    "training/data/planner/sft/260511_mimo_budget_usage_validate100_w50_dedup100_budget_clean/records.jsonl",
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
    "budget_consistency": 240,
    "meal_scale": 150,
    "itinerary_structure": 90,
    "grounding": 60,
    "overall_experience": 60,
}

LOCAL_CANDIDATE_SPECS = [
    {"label": "local_t02", "temperature": 0.2, "count": 3},
    {"label": "local_t05", "temperature": 0.5, "count": 3},
    {"label": "local_t08", "temperature": 0.8, "count": 2},
]


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


def request(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("request") or (row.get("planner_context") or {}).get("request") or {}


def control(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("control_spec") or {}


def planner_context(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("planner_context") or {}


def request_signature(row: dict[str, Any]) -> str:
    req = request(row)
    stable = {
        "city": req.get("city"),
        "start_date": req.get("start_date"),
        "end_date": req.get("end_date"),
        "travel_days": req.get("travel_days"),
        "transportation": req.get("transportation"),
        "accommodation": req.get("accommodation"),
        "preferences": req.get("preferences") or [],
        "free_text_input": req.get("free_text_input"),
        "party": req.get("party") or {},
        "budget_constraint": req.get("budget_constraint") or {},
    }
    return json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def budget_level(row: dict[str, Any]) -> str:
    req = request(row)
    return str(control(row).get("budget_level") or (req.get("budget_constraint") or {}).get("budget_level") or "unknown")


def budget_amount(row: dict[str, Any]) -> int:
    req = request(row)
    amount = control(row).get("budget_amount") or (req.get("budget_constraint") or {}).get("amount")
    try:
        return int(amount or 0)
    except (TypeError, ValueError):
        return 0


def strictness(row: dict[str, Any]) -> str:
    req = request(row)
    return str(control(row).get("budget_strictness") or (req.get("budget_constraint") or {}).get("strictness") or "none")


def travel_days(row: dict[str, Any]) -> int:
    try:
        return int(request(row).get("travel_days") or 0)
    except (TypeError, ValueError):
        return 0


def party_total(row: dict[str, Any]) -> int:
    party = request(row).get("party") or {}
    try:
        return int(party.get("total") or 1)
    except (TypeError, ValueError):
        return 1


def companion_type(row: dict[str, Any]) -> str:
    return str(control(row).get("companion_type") or "unknown")


def city_tier(row: dict[str, Any]) -> str:
    return str(control(row).get("city_tier") or "unknown")


def diet(row: dict[str, Any]) -> str:
    return str(control(row).get("diet") or "无")


def pace(row: dict[str, Any]) -> str:
    return str(control(row).get("pace") or "unknown")


def text_blob(row: dict[str, Any]) -> str:
    req = request(row)
    ctrl = control(row)
    values: list[str] = []
    for key in ("city", "accommodation", "transportation", "free_text_input"):
        if req.get(key):
            values.append(str(req[key]))
    values.extend(str(item) for item in (req.get("preferences") or []))
    for key in (
        "positive_preferences",
        "negative_constraints",
        "traveler_constraints",
        "diet_positive",
        "diet_avoid",
        "avoid",
    ):
        value = ctrl.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(str(value))
    values.append(diet(row))
    return " ".join(values)


def has_budget(row: dict[str, Any]) -> bool:
    return budget_amount(row) > 0 and budget_level(row) != "unknown"


def has_budget_fit_override(row: dict[str, Any]) -> bool:
    return bool(control(row).get("budget_fit_policy_override"))


def tool_counts(row: dict[str, Any]) -> dict[str, int]:
    metadata_counts = (row.get("metadata") or {}).get("tool_counts")
    if isinstance(metadata_counts, dict):
        return {str(key): int(value or 0) for key, value in metadata_counts.items()}
    snapshot = (planner_context(row).get("tool_snapshot") or {})
    result: dict[str, int] = {}
    for key in ("hotels", "restaurants", "attractions", "transit_options", "weather"):
        value = snapshot.get(key)
        result[key] = len(value) if isinstance(value, list) else 0
    return result


def has_future_weather(row: dict[str, Any]) -> bool:
    snapshot = planner_context(row).get("tool_snapshot") or {}
    weather = snapshot.get("weather")
    if isinstance(weather, list) and weather:
        blob = json.dumps(weather, ensure_ascii=False)
        return any(term in blob for term in ("雨", "雪", "高温", "低温", "大风", "雷", "降水"))
    return False


def dining_signal(row: dict[str, Any]) -> bool:
    text = text_blob(row)
    terms = (
        "美食",
        "餐厅",
        "小吃",
        "本地菜",
        "海鲜",
        "素食",
        "清真",
        "少辣",
        "清淡",
        "火锅",
        "夜市",
        "早茶",
        "咖啡",
    )
    return diet(row) not in {"", "无", "none", "unknown"} or any(term in text for term in terms)


def family_or_special_party(row: dict[str, Any]) -> bool:
    companion = companion_type(row)
    text = text_blob(row)
    return companion in {"family_with_children", "family_with_elders"} or any(
        term in text for term in ("老人", "孩子", "儿童", "亲子", "孕", "轮椅", "少走路")
    )


def rich_constraints(row: dict[str, Any]) -> bool:
    ctrl = control(row)
    text = text_blob(row)
    count = 0
    for key in ("positive_preferences", "negative_constraints", "traveler_constraints", "diet_positive", "diet_avoid"):
        value = ctrl.get(key)
        if isinstance(value, list):
            count += len(value)
        elif value:
            count += 1
    return count >= 3 or len(text) >= 80


def category_reason(row: dict[str, Any], category: str) -> str:
    parts = [
        f"budget={budget_level(row)}/{strictness(row)}/{budget_amount(row)}",
        f"days={travel_days(row)}",
        f"party={party_total(row)}",
        f"city_tier={city_tier(row)}",
        f"diet={diet(row)}",
        f"pace={pace(row)}",
    ]
    if category == "budget_consistency":
        return "budget arithmetic and fit pressure: " + ", ".join(parts)
    if category == "meal_scale":
        return "meal price/scale pressure: " + ", ".join(parts)
    if category == "itinerary_structure":
        return "route density, rhythm, sequence, or weather pressure: " + ", ".join(parts)
    if category == "grounding":
        counts = tool_counts(row)
        return f"grounding pressure from candidate availability: {counts}, " + ", ".join(parts)
    if category == "overall_experience":
        return "naturalness trade-off under rich user preferences: " + ", ".join(parts)
    return ", ".join(parts)


def category_match(row: dict[str, Any], category: str) -> bool:
    level = budget_level(row)
    strict = strictness(row)
    days = travel_days(row)
    party = party_total(row)
    counts = tool_counts(row)
    text = text_blob(row)

    if category == "budget_consistency":
        return has_budget(row) and (
            strict == "hard"
            or has_budget_fit_override(row)
            or party >= 2
            or days >= 3
            or level in {"standard", "comfortable", "premium", "luxury"}
            or any(term in text for term in ("人均", "总价", "预算", "用足", "省钱", "性价比"))
        )

    if category == "meal_scale":
        return has_budget(row) and (
            dining_signal(row)
            or level in {"limited", "standard", "premium", "luxury"}
            or counts.get("restaurants", 0) >= 4
            or days >= 4
        )

    if category == "itinerary_structure":
        return (
            days >= 4
            or pace(row) in {"relaxed", "fast", "紧凑", "慢节奏"}
            or family_or_special_party(row)
            or has_future_weather(row)
            or any(term in text for term in ("休息", "少走路", "顺路", "雨天", "室内", "不要太赶", "轻松"))
        )

    if category == "grounding":
        scarce = (
            0 < counts.get("hotels", 0) <= 3
            or 0 < counts.get("restaurants", 0) <= 4
            or 0 < counts.get("attractions", 0) <= 5
        )
        return (
            city_tier(row) == "long_tail"
            or scarce
            or any(term in text for term in ("冷门", "小众", "当地", "不要编", "真实", "地铁", "机场", "高铁"))
        )

    if category == "overall_experience":
        return (
            rich_constraints(row)
            or family_or_special_party(row)
            or level in {"comfortable", "premium", "luxury"}
            or companion_type(row) in {"couple", "friends", "business"}
            or any(term in text for term in ("纪念日", "拍照", "文化", "轻松", "不踩雷", "体验"))
        )

    raise KeyError(category)


def load_pool(source_paths: list[Path], eval_paths: list[Path]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    eval_signatures: set[str] = set()
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
        rel_source = str(source_path.relative_to(PROJECT_ROOT) if source_path.is_relative_to(PROJECT_ROOT) else source_path)
        if not source_path.exists():
            skipped[f"missing_source:{rel_source}"] += 1
            continue
        rows = read_jsonl(source_path)
        source_seen[rel_source] += len(rows)
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
            item["_high_conf_dpo_source_path"] = rel_source
            pool.append(item)
            source_selected[rel_source] += 1

    return pool, {
        "pool_after_dedup": len(pool),
        "eval_signatures": len(eval_signatures),
        "source_rows": dict(source_seen),
        "source_pool_after_dedup": dict(source_selected),
        "skipped": dict(skipped),
    }


def bucket_candidates(pool: list[dict[str, Any]], quotas: dict[str, int], seed: int) -> dict[str, list[dict[str, Any]]]:
    rng = random.Random(seed)
    result: dict[str, list[dict[str, Any]]] = {}
    for category in quotas:
        rows = [row for row in pool if category_match(row, category)]
        rng.shuffle(rows)
        result[category] = rows
    return result


def choose_records(pool: list[dict[str, Any]], quotas: dict[str, int], seed: int) -> tuple[list[dict[str, Any]], Counter]:
    selected: list[dict[str, Any]] = []
    selected_keys: set[str] = set()
    counts: Counter = Counter()
    candidates = bucket_candidates(pool, quotas, seed)

    for category, quota in quotas.items():
        for row in candidates[category]:
            if counts[category] >= quota:
                break
            signature = request_signature(row)
            if signature in selected_keys:
                continue
            selected.append(row)
            selected_keys.add(signature)
            counts[category] += 1

    limit = sum(quotas.values())
    if len(selected) < limit:
        rng = random.Random(seed + 17)
        remaining = [row for row in pool if request_signature(row) not in selected_keys]
        rng.shuffle(remaining)
        for row in remaining:
            selected.append(row)
            selected_keys.add(request_signature(row))
            counts["fill_other"] += 1
            if len(selected) >= limit:
                break

    return selected[:limit], counts


def distribution(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    getters: dict[str, Callable[[dict[str, Any]], str]] = {
        "dpo_context_bucket": lambda row: str((row.get("metadata") or {}).get("dpo_context_bucket", "unknown")),
        "budget_level": budget_level,
        "strictness": strictness,
        "travel_days": lambda row: str(travel_days(row)),
        "party_total": lambda row: str(party_total(row)),
        "companion_type": companion_type,
        "city_tier": city_tier,
        "diet": diet,
        "pace": pace,
    }
    result: dict[str, dict[str, int]] = {}
    for key, getter in getters.items():
        result[key] = dict(Counter(getter(row) for row in rows))
    return result


def planned_mimo_count(row: dict[str, Any], bucket: str) -> int:
    if bucket in {"budget_consistency", "meal_scale", "itinerary_structure"}:
        return 2
    if strictness(row) == "hard" or travel_days(row) >= 4 or budget_level(row) in {"premium", "luxury"}:
        return 2
    return 1


def build_candidate_plan(row: dict[str, Any], bucket: str) -> dict[str, Any]:
    mimo_count = planned_mimo_count(row, bucket)
    return {
        "local": LOCAL_CANDIDATE_SPECS,
        "local_total": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS),
        "mimo": {"label": "mimo_strong", "temperature": "judge/model_default", "count": mimo_count},
        "total_planned_candidates": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS) + mimo_count,
    }


def parse_quota(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("quota must be CATEGORY=COUNT")
    key, count = value.split("=", 1)
    try:
        return key, int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quota count must be an integer") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare high-confidence DPO context records.")
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "training/data/planner/dpo/260516_high_conf_contexts/records.jsonl",
    )
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=20260516)
    parser.add_argument("--id-prefix", default="dpo_hicontext_260516")
    parser.add_argument("--source", action="append", default=None, help="Record source jsonl. Can be repeated.")
    parser.add_argument("--eval-source", action="append", default=None, help="Frozen eval jsonl to exclude. Can be repeated.")
    parser.add_argument("--quota", type=parse_quota, action="append", default=None, help="CATEGORY=COUNT. Can be repeated.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = [project_path(path) for path in (args.source or DEFAULT_SOURCES)]
    eval_sources = [project_path(path) for path in (args.eval_source or DEFAULT_EVAL_SOURCES)]
    quotas = dict(args.quota or DEFAULT_QUOTAS.items())

    pool, pool_summary = load_pool(sources, eval_sources)
    selected, selected_counts = choose_records(pool, quotas, args.seed)

    output_rows: list[dict[str, Any]] = []
    running_bucket_counts: Counter = Counter()
    for index, row in enumerate(selected):
        original_record_id = row.get("record_id")
        source_path = row.pop("_high_conf_dpo_source_path", None)
        bucket = next((name for name in quotas if running_bucket_counts[name] < quotas[name] and category_match(row, name)), None)
        if not bucket:
            bucket = "fill_other"
        running_bucket_counts[bucket] += 1

        item = dict(row)
        item["record_id"] = f"{args.id_prefix}_{index:06d}__{original_record_id}"
        metadata = dict(item.get("metadata") or {})
        metadata.update(
            {
                "dpo_context_source_record_id": original_record_id,
                "dpo_context_source_path": source_path,
                "dpo_context_bucket": bucket,
                "dpo_context_bucket_reason": category_reason(item, bucket),
                "dpo_context_target_distribution": quotas,
                "dpo_candidate_plan": build_candidate_plan(item, bucket),
            }
        )
        item["metadata"] = metadata
        output_rows.append(item)

    write_jsonl(args.output, output_rows)
    summary = {
        "output": str(args.output),
        "selected": len(output_rows),
        "seed": args.seed,
        "id_prefix": args.id_prefix,
        "quotas": quotas,
        "selected_counts": dict(running_bucket_counts),
        "raw_selection_counts": dict(selected_counts),
        "candidate_plan": {
            "local": LOCAL_CANDIDATE_SPECS,
            "local_total": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS),
            "mimo_standard_count": 1,
            "mimo_complex_count": 2,
        },
        "distribution": distribution(output_rows),
        **pool_summary,
    }
    summary_path = args.summary_output or (args.output.parent / "records_summary.json")
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
