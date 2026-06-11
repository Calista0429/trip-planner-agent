#!/usr/bin/env python3
"""Merge high-confidence DPO candidates and build bucket-balanced pairs."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"
DATASET_INFO = LLAMAFACTORY_DIR / "dataset_info.json"

DEFAULT_ROOT = PROJECT_ROOT / "training/data/planner/dpo/260516_high_conf_contexts"
DEFAULT_QUOTAS = {
    "budget_consistency": 240,
    "meal_scale": 150,
    "itinerary_structure": 90,
    "grounding": 60,
    "overall_experience": 60,
}

BUCKET_BOOL_WEIGHTS = {
    "budget_consistency": {
        "budget_arithmetic_consistent": 28,
        "dpo_soft_recomputed_budget_pass": 22,
        "recomputed_budget_fit_ok": 18,
        "budget_relationship_ok": 16,
        "budget_preference_aligned": 16,
        "budget_user_constraint_ok": 12,
        "recomputed_budget_preference_aligned": 12,
        "recomputed_budget_level_aligned": 10,
        "hotel_budget_relation_ok": 8,
        "hotel_budget_covers_nights": 8,
        "attraction_budget_party_relation_ok": 8,
        "meal_budget_consistent": 8,
    },
    "meal_scale": {
        "meal_complete": 18,
        "meal_specific_ok": 16,
        "meal_valid_semantics_ok": 16,
        "meal_grounding_ok": 14,
        "meal_cost_scale_ok": 24,
        "meal_lunch_dinner_same_day_ok": 14,
        "meal_repeat_limit_ok": 12,
        "meal_diversity_ok": 12,
        "meal_budget_consistent": 10,
        "dpo_soft_pass": 8,
    },
    "itinerary_structure": {
        "date_range_ok": 10,
        "days_len_ok": 10,
        "day_dates_ok": 10,
        "day_index_ok": 8,
        "weather_dates_ok": 8,
        "weather_match": 14,
        "attraction_count_ok": 18,
        "attraction_diversity_ok": 14,
        "attraction_repeat_limit_ok": 10,
        "transportation_budget_nonnegative": 6,
        "dpo_soft_pass": 10,
    },
    "grounding": {
        "attraction_grounding_ok": 24,
        "hotel_grounding_ok": 22,
        "meal_grounding_ok": 20,
        "location_object_ok": 10,
        "hotel_distance_placeholder_ok": 8,
        "weather_match": 8,
        "meal_specific_ok": 8,
        "invalid_hotel_name_ok": 8,
    },
    "overall_experience": {
        "sft_hard_pass": 18,
        "dpo_soft_pass": 16,
        "dpo_soft_recomputed_budget_pass": 10,
        "budget_preference_aligned": 8,
        "meal_diversity_ok": 8,
        "meal_cost_scale_ok": 8,
        "attraction_diversity_ok": 8,
        "attraction_grounding_ok": 8,
        "meal_grounding_ok": 8,
        "weather_match": 6,
    },
}

BUCKET_RATE_WEIGHTS = {
    "budget_consistency": {
        "recomputed_budget_per_person_day": 0.0,
    },
    "meal_scale": {
        "meal_grounding_rate": 8,
        "meal_food_pois_grounding_rate": 10,
        "meal_semantic_valid_rate": 8,
        "meal_diversity_unique_rate": 8,
    },
    "itinerary_structure": {
        "attraction_diversity_unique_rate": 10,
        "attraction_grounding_rate": 5,
    },
    "grounding": {
        "attraction_grounding_rate": 20,
        "hotel_grounding_rate": 18,
        "meal_grounding_rate": 16,
        "meal_food_pois_grounding_rate": 16,
    },
    "overall_experience": {
        "attraction_grounding_rate": 6,
        "hotel_grounding_rate": 6,
        "meal_grounding_rate": 6,
        "meal_diversity_unique_rate": 6,
        "attraction_diversity_unique_rate": 5,
    },
}

SEVERE_ERROR_PENALTIES = {
    "json_extract": 100,
    "schema": 90,
    "meal_grounding_miss": 30,
    "meal_invalid_name": 30,
    "meal_placeholder": 28,
    "meal_same_day_lunch_dinner_repeat": 24,
    "meal_repeat_too_many": 16,
    "budget_arithmetic_mismatch": 28,
    "budget_preference_mismatch": 18,
    "budget_relationship_mismatch": 18,
    "budget_hard_constraint_exceeded": 22,
    "hotel_grounding_low": 24,
    "attraction_grounding_low": 22,
    "weather_mismatch": 18,
    "hotel_distance_placeholder": 14,
    "middle_hotel_null": 14,
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid json") from exc
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def bool_metric(candidate: dict[str, Any], key: str) -> bool:
    return (candidate.get("rule_metrics") or {}).get(key) is True


def float_metric(candidate: dict[str, Any], key: str) -> float:
    try:
        return float((candidate.get("rule_metrics") or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def error_types(candidate: dict[str, Any]) -> list[str]:
    return [str(item.get("type") or item.get("stage") or "unknown") for item in candidate.get("rule_errors") or []]


def schema_ok(candidate: dict[str, Any]) -> bool:
    metrics = candidate.get("rule_metrics") or {}
    return (
        candidate.get("parsed_ok") is True
        and candidate.get("schema_ok") is True
        and metrics.get("json_extract_ok") is True
        and metrics.get("schema_ok") is True
    )


def hard_ok(candidate: dict[str, Any]) -> bool:
    return schema_ok(candidate) and bool_metric(candidate, "sft_hard_pass")


def make_training_prompt(system_prompt: str, prompt: str) -> str:
    return f"{system_prompt.strip()}\n\n{prompt.strip()}".strip()


def source_kind(candidate: dict[str, Any]) -> str:
    if candidate.get("source_type") == "strong" or candidate.get("source_model") == "mimo":
        return "mimo"
    return "local"


def base_score(candidate: dict[str, Any]) -> float:
    score = 0.0
    if schema_ok(candidate):
        score += 30
    else:
        score -= 120
    if hard_ok(candidate):
        score += 40
    if bool_metric(candidate, "dpo_soft_pass"):
        score += 12
    if bool_metric(candidate, "dpo_soft_recomputed_budget_pass"):
        score += 10
    for key in ("attraction_grounding_rate", "hotel_grounding_rate", "meal_grounding_rate"):
        score += float_metric(candidate, key) * 4
    for kind in error_types(candidate):
        score -= SEVERE_ERROR_PENALTIES.get(kind, 2)
    return score


def bucket_score(candidate: dict[str, Any], bucket: str) -> tuple[float, dict[str, float]]:
    components: dict[str, float] = {"base": round(base_score(candidate), 4)}
    score = components["base"]
    weights = BUCKET_BOOL_WEIGHTS.get(bucket, {})
    for key, weight in weights.items():
        delta = float(weight if bool_metric(candidate, key) else -weight * 0.65)
        components[key] = delta
        score += delta
    for key, weight in BUCKET_RATE_WEIGHTS.get(bucket, {}).items():
        if weight == 0:
            continue
        delta = float_metric(candidate, key) * float(weight)
        components[key] = round(delta, 4)
        score += delta
    if bucket == "overall_experience" and source_kind(candidate) == "mimo":
        components["mimo_naturalness_proxy"] = 6.0
        score += 6.0
    return round(score, 4), components


def target_pass(candidate: dict[str, Any], bucket: str) -> bool:
    if not schema_ok(candidate):
        return False
    checks = {
        "budget_consistency": [
            "budget_arithmetic_consistent",
            "dpo_soft_recomputed_budget_pass",
            "budget_relationship_ok",
            "budget_preference_aligned",
        ],
        "meal_scale": [
            "meal_complete",
            "meal_specific_ok",
            "meal_valid_semantics_ok",
            "meal_grounding_ok",
            "meal_cost_scale_ok",
            "meal_lunch_dinner_same_day_ok",
        ],
        "itinerary_structure": [
            "day_dates_ok",
            "weather_match",
            "attraction_count_ok",
            "attraction_diversity_ok",
        ],
        "grounding": [
            "attraction_grounding_ok",
            "hotel_grounding_ok",
            "meal_grounding_ok",
            "location_object_ok",
        ],
        "overall_experience": [
            "sft_hard_pass",
            "dpo_soft_pass",
            "meal_specific_ok",
            "attraction_count_ok",
            "weather_match",
        ],
    }
    keys = checks.get(bucket, [])
    if bucket == "budget_consistency":
        return bool_metric(candidate, "budget_arithmetic_consistent") and (
            bool_metric(candidate, "dpo_soft_recomputed_budget_pass")
            or bool_metric(candidate, "recomputed_budget_fit_ok")
            or bool_metric(candidate, "budget_preference_aligned")
        )
    return sum(1 for key in keys if bool_metric(candidate, key)) >= max(1, len(keys) - 1)


def scored_candidate(candidate: dict[str, Any], bucket: str) -> dict[str, Any]:
    score, components = bucket_score(candidate, bucket)
    item = dict(candidate)
    item["dpo_bucket_score"] = score
    item["dpo_bucket_components"] = components
    item["dpo_schema_ok"] = schema_ok(candidate)
    item["dpo_hard_ok"] = hard_ok(candidate)
    item["dpo_target_pass"] = target_pass(candidate, bucket)
    item["dpo_source_kind"] = source_kind(candidate)
    return item


def choose_pair(row: dict[str, Any], min_gap: float) -> tuple[dict[str, Any] | None, str]:
    bucket = (row.get("metadata") or {}).get("dpo_context_bucket", "unknown")
    scored = [scored_candidate(candidate, bucket) for candidate in row.get("candidates") or []]
    schema_candidates = [item for item in scored if item["dpo_schema_ok"]]
    if not schema_candidates:
        return None, "no_schema_candidate"

    chosen_pool = [item for item in schema_candidates if item["dpo_hard_ok"] and item["dpo_target_pass"]]
    if not chosen_pool:
        chosen_pool = [item for item in schema_candidates if item["dpo_hard_ok"]]
    if not chosen_pool:
        chosen_pool = schema_candidates

    if bucket == "overall_experience":
        max_score = max(item["dpo_bucket_score"] for item in chosen_pool)
        near_best = [item for item in chosen_pool if max_score - item["dpo_bucket_score"] <= 8.0]
        strong_near_best = [item for item in near_best if item["dpo_source_kind"] == "mimo"]
        chosen = sorted(strong_near_best or near_best, key=lambda item: item["dpo_bucket_score"], reverse=True)[0]
    else:
        chosen = sorted(chosen_pool, key=lambda item: item["dpo_bucket_score"], reverse=True)[0]

    rejected_pool = [
        item
        for item in schema_candidates
        if item.get("candidate_id") != chosen.get("candidate_id")
        and chosen["dpo_bucket_score"] - item["dpo_bucket_score"] >= min_gap
    ]
    target_fail = [item for item in rejected_pool if not item["dpo_target_pass"]]
    hard_fail = [item for item in rejected_pool if not item["dpo_hard_ok"]]
    same_hard = [item for item in rejected_pool if item["dpo_hard_ok"]]

    if target_fail:
        rejected = sorted(target_fail, key=lambda item: item["dpo_bucket_score"])[0]
        pair_type = f"{bucket}:target_pass_vs_target_fail"
    elif hard_fail:
        rejected = sorted(hard_fail, key=lambda item: item["dpo_bucket_score"])[0]
        pair_type = f"{bucket}:hardpass_vs_schema_hardfail"
    elif same_hard:
        rejected = sorted(same_hard, key=lambda item: item["dpo_bucket_score"])[0]
        pair_type = f"{bucket}:hardpass_vs_lower_hardpass"
    else:
        # Last-resort fallback keeps one pair per bucket item, but still only
        # compares schema-valid outputs.
        fallback = [item for item in schema_candidates if item.get("candidate_id") != chosen.get("candidate_id")]
        if not fallback:
            return None, "no_rejected_candidate"
        rejected = sorted(fallback, key=lambda item: item["dpo_bucket_score"])[0]
        pair_type = f"{bucket}:fallback_schema_pair"

    return {
        "chosen": chosen,
        "rejected": rejected,
        "pair_type": pair_type,
        "score_gap": round(chosen["dpo_bucket_score"] - rejected["dpo_bucket_score"], 4),
        "bucket": bucket,
    }, "ok"


def load_prompt_map(path: Path) -> dict[str, dict[str, Any]]:
    return {row["prompt_id"]: row for row in read_jsonl(path)}


def merge_candidates(root: Path, shards: list[str]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for shard in shards:
        path = root / shard / "candidates.jsonl"
        for row in read_jsonl(path):
            prompt_id = row.get("prompt_id")
            if not prompt_id:
                continue
            item = merged.setdefault(
                prompt_id,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prompt_id": prompt_id,
                    "record_id": row.get("record_id"),
                    "request": row.get("request") or {},
                    "control_spec": row.get("control_spec") or {},
                    "metadata": row.get("metadata") or {},
                    "candidate_sources": [],
                    "candidates": [],
                },
            )
            item["candidate_sources"].append(shard)
            item["candidates"].extend(row.get("candidates") or [])

    rows = list(merged.values())
    rows.sort(key=lambda item: item.get("prompt_id", ""))
    return rows


def make_lf_pair(prompt_row: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    chosen = pair["chosen"]
    rejected = pair["rejected"]
    return {
        "conversations": [
            {
                "from": "human",
                "value": make_training_prompt(prompt_row.get("system_prompt", ""), prompt_row.get("prompt", "")),
            }
        ],
        "chosen": {"from": "gpt", "value": chosen.get("output_text", "")},
        "rejected": {"from": "gpt", "value": rejected.get("output_text", "")},
        "preference_reason": (
            f"{pair['pair_type']}; bucket_score {chosen.get('dpo_bucket_score')} > "
            f"{rejected.get('dpo_bucket_score')}; chosen={chosen.get('candidate_id')} "
            f"rejected={rejected.get('candidate_id')}"
        ),
    }


def audit_pair(pair_id: str, row: dict[str, Any], prompt_row: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    chosen = pair["chosen"]
    rejected = pair["rejected"]
    chosen_metrics = chosen.get("rule_metrics") or {}
    rejected_metrics = rejected.get("rule_metrics") or {}
    metric_keys = [
        "sft_hard_pass",
        "dpo_soft_pass",
        "dpo_soft_recomputed_budget_pass",
        "recomputed_budget_fit_ok",
        "budget_preference_aligned",
        "budget_relationship_ok",
        "budget_arithmetic_consistent",
        "meal_cost_scale_ok",
        "meal_diversity_ok",
        "meal_grounding_ok",
        "attraction_grounding_ok",
        "hotel_grounding_ok",
        "weather_match",
        "attraction_count_ok",
        "attraction_diversity_ok",
    ]
    return {
        "pair_id": pair_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_id": row.get("prompt_id"),
        "record_id": row.get("record_id"),
        "bucket": pair["bucket"],
        "pair_type": pair["pair_type"],
        "score_gap": pair["score_gap"],
        "chosen_candidate_id": chosen.get("candidate_id"),
        "rejected_candidate_id": rejected.get("candidate_id"),
        "chosen_source": chosen.get("dpo_source_kind"),
        "rejected_source": rejected.get("dpo_source_kind"),
        "chosen_temperature": chosen.get("temperature"),
        "rejected_temperature": rejected.get("temperature"),
        "chosen_score": chosen.get("dpo_bucket_score"),
        "rejected_score": rejected.get("dpo_bucket_score"),
        "chosen_schema_ok": chosen.get("dpo_schema_ok"),
        "rejected_schema_ok": rejected.get("dpo_schema_ok"),
        "chosen_hard_ok": chosen.get("dpo_hard_ok"),
        "rejected_hard_ok": rejected.get("dpo_hard_ok"),
        "chosen_target_pass": chosen.get("dpo_target_pass"),
        "rejected_target_pass": rejected.get("dpo_target_pass"),
        "metadata": row.get("metadata") or {},
        "chosen_metrics": {key: chosen_metrics.get(key) for key in metric_keys},
        "rejected_metrics": {key: rejected_metrics.get(key) for key in metric_keys},
        "chosen_errors": chosen.get("rule_errors") or [],
        "rejected_errors": rejected.get("rule_errors") or [],
        "llamafactory_pair": make_lf_pair(prompt_row, pair),
    }


def stratified_split(pairs: list[dict[str, Any]], val_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_bucket[pair.get("bucket", "unknown")].append(pair)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for bucket, rows in by_bucket.items():
        rows = list(rows)
        rng.shuffle(rows)
        val_size = max(1, round(len(rows) * val_ratio)) if len(rows) > 1 else 0
        val.extend(rows[:val_size])
        train.extend(rows[val_size:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def update_dataset_info(train_path: Path, val_path: Path, train_name: str, val_name: str) -> None:
    data = json.loads(DATASET_INFO.read_text(encoding="utf-8")) if DATASET_INFO.exists() else {}
    entry = {
        "ranking": True,
        "formatting": "sharegpt",
        "columns": {
            "messages": "conversations",
            "chosen": "chosen",
            "rejected": "rejected",
        },
    }

    def file_name(path: Path) -> str:
        try:
            return path.relative_to(LLAMAFACTORY_DIR).as_posix()
        except ValueError:
            return path.name

    data[train_name] = {"file_name": file_name(train_path), **entry}
    data[val_name] = {"file_name": file_name(val_path), **entry}
    write_json(DATASET_INFO, data)


def summarize(merged: list[dict[str, Any]], pairs: list[dict[str, Any]], skipped: Counter[str], args: argparse.Namespace) -> dict[str, Any]:
    bucket_counts = Counter(pair.get("bucket", "unknown") for pair in pairs)
    pair_types = Counter(pair.get("pair_type", "unknown") for pair in pairs)
    chosen_sources = Counter(pair.get("chosen_source", "unknown") for pair in pairs)
    rejected_sources = Counter(pair.get("rejected_source", "unknown") for pair in pairs)
    gaps = [float(pair.get("score_gap") or 0.0) for pair in pairs]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(args.root),
        "merged_prompts": len(merged),
        "total_pairs": len(pairs),
        "target_quotas": DEFAULT_QUOTAS,
        "bucket_counts": dict(bucket_counts),
        "bucket_rates": {key: round(value / len(pairs), 4) for key, value in bucket_counts.items()} if pairs else {},
        "pair_types": dict(pair_types),
        "chosen_sources": dict(chosen_sources),
        "rejected_sources": dict(rejected_sources),
        "skipped": dict(skipped),
        "score_gap_min": round(min(gaps), 4) if gaps else None,
        "score_gap_avg": round(sum(gaps) / len(gaps), 4) if gaps else None,
        "score_gap_max": round(max(gaps), 4) if gaps else None,
        "min_gap": args.min_gap,
        "val_ratio": args.val_ratio,
        "seed": args.seed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_ROOT / "prompts.jsonl")
    parser.add_argument("--shard", action="append", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_ROOT / "filtered_pairs")
    parser.add_argument("--lf-output-dir", type=Path, default=LLAMAFACTORY_DIR / "generated")
    parser.add_argument("--dataset-prefix", default="trip_planner_dpo_260517_high_conf")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=260517)
    parser.add_argument("--min-gap", type=float, default=8.0)
    parser.add_argument("--update-dataset-info", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    shards = args.shard or ["gpu0", "gpu2", "gpu4", "gpu7", "mimo"]
    prompt_map = load_prompt_map(args.prompts)
    merged = merge_candidates(args.root, shards)

    merged_path = args.output_dir / "merged_candidates.jsonl"
    write_jsonl(merged_path, merged)

    pairs: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for row in merged:
        prompt_id = row.get("prompt_id")
        prompt_row = prompt_map.get(prompt_id)
        if not prompt_row:
            skipped["missing_prompt"] += 1
            continue
        pair, reason = choose_pair(row, args.min_gap)
        if not pair:
            skipped[reason] += 1
            continue
        pair_id = f"{args.dataset_prefix}_{len(pairs) + 1:06d}"
        pairs.append(audit_pair(pair_id, row, prompt_row, pair))

    pairs.sort(key=lambda item: item["pair_id"])
    train_pairs, val_pairs = stratified_split(pairs, args.val_ratio, args.seed)

    lf_train = [pair["llamafactory_pair"] for pair in train_pairs]
    lf_val = [pair["llamafactory_pair"] for pair in val_pairs]
    train_path = args.lf_output_dir / f"{args.dataset_prefix}_train.json"
    val_path = args.lf_output_dir / f"{args.dataset_prefix}_val.json"
    write_json(train_path, lf_train)
    write_json(val_path, lf_val)

    audit_rows = [{key: value for key, value in pair.items() if key != "llamafactory_pair"} for pair in pairs]
    write_jsonl(args.output_dir / "pairs.jsonl", audit_rows)

    summary = summarize(merged, pairs, skipped, args)
    summary.update(
        {
            "merged_candidates": str(merged_path),
            "pairs": str(args.output_dir / "pairs.jsonl"),
            "lf_train": str(train_path),
            "lf_val": str(val_path),
            "train": len(lf_train),
            "val": len(lf_val),
            "train_bucket_counts": dict(Counter(pair.get("bucket", "unknown") for pair in train_pairs)),
            "val_bucket_counts": dict(Counter(pair.get("bucket", "unknown") for pair in val_pairs)),
        }
    )
    write_json(args.output_dir / "summary.json", summary)

    if args.update_dataset_info:
        update_dataset_info(
            train_path,
            val_path,
            f"{args.dataset_prefix}_train",
            f"{args.dataset_prefix}_val",
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
