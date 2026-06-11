#!/usr/bin/env python3
"""Build an eval-clean closing DPO set for planner-soft budget failures."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = Path(__file__).resolve().parent
BESTOFN_DIR = SCRIPT_DIR / "bestofn"
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"

sys.path[:0] = [str(SCRIPT_DIR), str(BESTOFN_DIR)]

from build_planner_soft_clean_dpo import (  # noqa: E402
    clean_score,
    generation_clean,
    hard_ok,
    load_prompts,
    make_lf_pair,
    planner_fail_keys,
    planner_soft_ok,
    read_jsonl,
    register_dataset,
    schema_ok,
    source_kind,
    write_json,
    write_jsonl,
)
from prepare_high_confidence_dpo_contexts import request_signature  # noqa: E402


DEFAULT_EVAL_SOURCES = [
    PROJECT_ROOT / "training/data/planner/eval/records.jsonl",
    PROJECT_ROOT / "training/data/planner/eval_hard/records.jsonl",
    PROJECT_ROOT / "training/data/planner/eval_rebuilt_260517_comfort_hotel_fix/records.jsonl",
    PROJECT_ROOT / "training/data/planner/eval_hard_rebuilt_260517_comfort_hotel_fix/records.jsonl",
]

DEFAULT_QUOTAS = {
    "hard_user_budget_over": 280,
    "target_over": 180,
    "target_under": 260,
    "budget_boundary": 140,
    "meal_diversity": 120,
    "attraction_diversity": 90,
    "meal_scale": 60,
    "hard_valid_anchor": 120,
}

BUDGET_CATEGORIES = {
    "hard_user_budget_over",
    "target_over",
    "target_under",
    "budget_boundary",
}

STRICT_CHOSEN_METRICS = [
    "budget_consistent",
    "budget_arithmetic_consistent",
    "budget_relationship_ok",
    "budget_preference_aligned",
    "budget_user_constraint_ok",
    "hotel_budget_covers_nights",
    "hotel_budget_relation_ok",
    "transportation_budget_nonnegative",
    "attraction_budget_consistent",
    "meal_budget_consistent",
    "meal_cost_scale_ok",
    "meal_diversity_ok",
    "attraction_diversity_ok",
    "meal_grounding_ok",
    "attraction_grounding_ok",
    "hotel_grounding_ok",
    "weather_match",
    "recomputed_budget_user_constraint_ok",
    "recomputed_budget_fit_ok",
]

REJECTED_GUARDRAIL_METRICS = [
    "meal_grounding_ok",
    "attraction_grounding_ok",
    "hotel_grounding_ok",
    "weather_match",
]

AUDIT_METRIC_KEYS = [
    "sft_hard_pass",
    "planner_soft_pass",
    "dpo_soft_pass",
    "dpo_soft_recomputed_budget_pass",
    "recomputed_budget_user_constraint_ok",
    "recomputed_budget_fit_ok",
    "recomputed_budget_total",
    "recomputed_budget_per_person_day",
    "budget_consistent",
    "budget_arithmetic_consistent",
    "budget_relationship_ok",
    "budget_preference_aligned",
    "budget_user_constraint_ok",
    "budget_within_user_budget",
    "hotel_budget_covers_nights",
    "hotel_budget_relation_ok",
    "transportation_budget_nonnegative",
    "attraction_budget_consistent",
    "meal_budget_consistent",
    "meal_cost_scale_ok",
    "meal_diversity_ok",
    "attraction_diversity_ok",
    "meal_grounding_ok",
    "attraction_grounding_ok",
    "hotel_grounding_ok",
    "weather_match",
]


def bool_metric(candidate: dict[str, Any], key: str) -> bool:
    return (candidate.get("rule_metrics") or {}).get(key) is True


def float_metric(candidate: dict[str, Any], key: str) -> float:
    try:
        return float((candidate.get("rule_metrics") or {}).get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def intish(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_eval_signatures(paths: list[Path]) -> tuple[set[str], dict[str, Any]]:
    signatures: set[str] = set()
    source_counts: dict[str, int] = {}
    missing: list[str] = []
    for path in paths:
        if not path.exists():
            missing.append(path.relative_to(PROJECT_ROOT).as_posix())
            continue
        rows = read_jsonl(path)
        source_counts[path.relative_to(PROJECT_ROOT).as_posix()] = len(rows)
        for row in rows:
            signatures.add(request_signature(row))
    return signatures, {
        "eval_sources": source_counts,
        "missing_eval_sources": missing,
        "eval_signature_count": len(signatures),
    }


def budget_audit(row: dict[str, Any]) -> dict[str, Any]:
    return (row.get("metadata") or {}).get("budget_context_audit") or {}


def requested_budget(row: dict[str, Any]) -> dict[str, Any]:
    request = row.get("request") or {}
    control = row.get("control_spec") or {}
    budget = request.get("budget_constraint") or {}
    return {
        "amount": intish(budget.get("amount") or control.get("budget_amount")),
        "level": str(budget.get("budget_level") or control.get("budget_level") or "unknown"),
        "strictness": str(budget.get("strictness") or control.get("budget_strictness") or "unknown"),
    }


def target_range(row: dict[str, Any]) -> tuple[int, int]:
    audit = budget_audit(row)
    return intish(audit.get("target_min_total")), intish(audit.get("target_max_total"))


def travel_days(row: dict[str, Any]) -> int:
    request = row.get("request") or {}
    control = row.get("control_spec") or {}
    return intish(request.get("travel_days") or control.get("travel_days"))


def party_total(row: dict[str, Any]) -> int:
    request = row.get("request") or {}
    party = request.get("party") or {}
    return intish(party.get("total"))


def companion_type(row: dict[str, Any]) -> str:
    request = row.get("request") or {}
    party = request.get("party") or {}
    control = row.get("control_spec") or {}
    metadata = row.get("metadata") or {}
    return str(party.get("companion_type") or control.get("companion_type") or metadata.get("companion_type") or "unknown")


def candidate_budget_status(row: dict[str, Any], candidate: dict[str, Any]) -> str:
    total = intish((candidate.get("rule_metrics") or {}).get("recomputed_budget_total"))
    if total <= 0:
        return "unknown"
    if bool_metric(candidate, "recomputed_budget_fit_ok") and bool_metric(candidate, "recomputed_budget_user_constraint_ok"):
        return "budget_fit"
    budget = requested_budget(row)
    amount = budget["amount"]
    strictness = budget["strictness"]
    target_min, target_max = target_range(row)

    if amount > 0 and strictness == "hard" and total > amount:
        return "hard_user_budget_over"
    if amount > 0 and not bool_metric(candidate, "recomputed_budget_user_constraint_ok") and total > amount:
        return "hard_user_budget_over"
    if target_max > 0 and total > target_max:
        return "target_over"
    if target_min > 0 and total < target_min:
        return "target_under"
    return "budget_misaligned"


def strict_chosen_ok(candidate: dict[str, Any]) -> bool:
    return (
        schema_ok(candidate)
        and generation_clean(candidate)
        and hard_ok(candidate)
        and planner_soft_ok(candidate)
        and not (candidate.get("rule_errors") or [])
        and all(bool_metric(candidate, key) for key in STRICT_CHOSEN_METRICS)
    )


def rejected_clean_enough(candidate: dict[str, Any]) -> bool:
    return (
        schema_ok(candidate)
        and generation_clean(candidate)
        and hard_ok(candidate)
        and not planner_soft_ok(candidate)
        and all(bool_metric(candidate, key) for key in REJECTED_GUARDRAIL_METRICS)
    )


def enrich_candidate(row: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    item = dict(candidate)
    score, components = clean_score(candidate)
    item["closing_score"] = score
    item["closing_score_components"] = components
    item["closing_schema_ok"] = schema_ok(candidate)
    item["closing_generation_clean"] = generation_clean(candidate)
    item["closing_hard_ok"] = hard_ok(candidate)
    item["closing_planner_soft_ok"] = planner_soft_ok(candidate)
    item["closing_source_kind"] = source_kind(candidate)
    item["closing_budget_status"] = candidate_budget_status(row, candidate)
    item["planner_fail_keys"] = planner_fail_keys(candidate)
    return item


def reject_matches(row: dict[str, Any], candidate: dict[str, Any], category: str) -> bool:
    status = candidate.get("closing_budget_status")
    fail_keys = set(candidate.get("planner_fail_keys") or [])
    bucket = str((row.get("metadata") or {}).get("dpo_context_bucket") or "unknown")

    if category == "hard_user_budget_over":
        return status == "hard_user_budget_over"
    if category == "target_over":
        return status in {"target_over", "hard_user_budget_over"}
    if category == "target_under":
        return status == "target_under"
    if category == "budget_boundary":
        return (
            "recomputed_budget_fit_ok" in fail_keys
            or "recomputed_budget_user_constraint_ok" in fail_keys
            or status in {"target_over", "target_under", "hard_user_budget_over", "budget_misaligned"}
        )
    if category == "meal_diversity":
        return "meal_diversity_ok" in fail_keys and status == "budget_fit"
    if category == "attraction_diversity":
        return "attraction_diversity_ok" in fail_keys and status == "budget_fit"
    if category == "meal_scale":
        return "meal_cost_scale_ok" in fail_keys
    if category == "hard_valid_anchor":
        return bucket == "hard_valid_stability" or (
            not fail_keys
            and not bool_metric(candidate, "planner_soft_pass")
        )
    raise KeyError(category)


def row_priority(row: dict[str, Any], category: str, chosen: dict[str, Any], rejected: dict[str, Any], gap: float) -> float:
    budget = requested_budget(row)
    level = budget["level"]
    strictness = budget["strictness"]
    days = travel_days(row)
    party = party_total(row)
    companion = companion_type(row)
    priority = gap

    if category == "hard_user_budget_over":
        if strictness == "hard":
            priority += 35
        if level == "comfortable":
            priority += 24
        elif level == "standard":
            priority += 14
        elif level == "limited":
            priority += 8
        if days >= 4:
            priority += 10
        if party >= 3:
            priority += 8
        if companion in {"family_with_children", "family_mixed", "business"}:
            priority += 8
    elif category == "target_over":
        if level == "comfortable":
            priority += 18
        if strictness == "soft":
            priority += 8
        if days >= 4 or party >= 3:
            priority += 8
    elif category == "target_under":
        if level in {"standard", "premium"}:
            priority += 20
        elif level == "comfortable":
            priority += 12
        if strictness == "soft":
            priority += 8
    elif category in {"meal_diversity", "attraction_diversity"}:
        if days >= 4:
            priority += 12
    elif category == "meal_scale":
        if level in {"premium", "luxury"}:
            priority += 20

    if chosen.get("closing_source_kind") == "mimo":
        priority += 3
    if rejected.get("closing_source_kind") == "local":
        priority += 2
    return round(priority, 4)


def make_pair_candidate(row: dict[str, Any], prompt_row: dict[str, Any], category: str) -> tuple[dict[str, Any] | None, str]:
    scored = [enrich_candidate(row, candidate) for candidate in row.get("candidates") or []]
    chosen_pool = [candidate for candidate in scored if strict_chosen_ok(candidate)]
    if category in BUDGET_CATEGORIES:
        chosen_pool = [candidate for candidate in chosen_pool if candidate.get("closing_budget_status") == "budget_fit"]
    if not chosen_pool:
        return None, f"{category}:no_strict_chosen"

    rejected_pool = [
        candidate
        for candidate in scored
        if rejected_clean_enough(candidate)
        and candidate.get("candidate_id") not in {item.get("candidate_id") for item in chosen_pool}
        and reject_matches(row, candidate, category)
    ]
    if not rejected_pool:
        return None, f"{category}:no_clean_rejected"

    chosen = sorted(
        chosen_pool,
        key=lambda item: (float(item.get("closing_score") or 0.0), item.get("closing_source_kind") == "mimo"),
        reverse=True,
    )[0]
    rejected = sorted(
        rejected_pool,
        key=lambda item: (float(item.get("closing_score") or 0.0), item.get("closing_source_kind") == "mimo"),
    )[0]
    gap = round(float(chosen.get("closing_score") or 0.0) - float(rejected.get("closing_score") or 0.0), 4)
    pair = {
        "category": category,
        "bucket": str((row.get("metadata") or {}).get("dpo_context_bucket") or "unknown"),
        "pair_type": f"{category}:strict_planner_soft_vs_target_fail",
        "score_gap": gap,
        "chosen": chosen,
        "rejected": rejected,
        "rejected_planner_fail_keys": rejected.get("planner_fail_keys") or [],
        "priority": row_priority(row, category, chosen, rejected, gap),
        "prompt_row": prompt_row,
    }
    return pair, "ok"


def make_training_prompt(system_prompt: str, prompt: str) -> str:
    return f"{system_prompt.strip()}\n\n{prompt.strip()}".strip()


def prompt_hash(prompt_row: dict[str, Any]) -> str:
    return sha256_text(make_training_prompt(prompt_row.get("system_prompt", ""), prompt_row.get("prompt", "")))


def audit_pair(pair_id: str, row: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    chosen = pair["chosen"]
    rejected = pair["rejected"]
    prompt_row = pair["prompt_row"]
    budget = requested_budget(row)
    target_min, target_max = target_range(row)
    audit = {
        "pair_id": pair_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_id": row.get("prompt_id"),
        "record_id": row.get("record_id"),
        "request_signature_sha256": sha256_text(request_signature(row)),
        "prompt_hash": prompt_hash(prompt_row),
        "category": pair["category"],
        "bucket": pair["bucket"],
        "pair_type": pair["pair_type"],
        "score_gap": pair["score_gap"],
        "priority": pair["priority"],
        "budget_level": budget["level"],
        "budget_strictness": budget["strictness"],
        "budget_amount": budget["amount"],
        "target_min_total": target_min,
        "target_max_total": target_max,
        "travel_days": travel_days(row),
        "party_total": party_total(row),
        "companion_type": companion_type(row),
        "chosen_candidate_id": chosen.get("candidate_id"),
        "rejected_candidate_id": rejected.get("candidate_id"),
        "chosen_source": chosen.get("closing_source_kind"),
        "rejected_source": rejected.get("closing_source_kind"),
        "chosen_temperature": chosen.get("temperature"),
        "rejected_temperature": rejected.get("temperature"),
        "chosen_score": chosen.get("closing_score"),
        "rejected_score": rejected.get("closing_score"),
        "chosen_budget_status": chosen.get("closing_budget_status"),
        "rejected_budget_status": rejected.get("closing_budget_status"),
        "chosen_schema_ok": chosen.get("closing_schema_ok"),
        "rejected_schema_ok": rejected.get("closing_schema_ok"),
        "chosen_generation_clean": chosen.get("closing_generation_clean"),
        "rejected_generation_clean": rejected.get("closing_generation_clean"),
        "chosen_hard_ok": chosen.get("closing_hard_ok"),
        "rejected_hard_ok": rejected.get("closing_hard_ok"),
        "chosen_planner_soft": chosen.get("closing_planner_soft_ok"),
        "rejected_planner_soft": rejected.get("closing_planner_soft_ok"),
        "rejected_planner_fail_keys": rejected.get("planner_fail_keys") or [],
        "metadata": row.get("metadata") or {},
        "candidate_sources": row.get("candidate_sources") or [],
        "chosen_metrics": {key: (chosen.get("rule_metrics") or {}).get(key) for key in AUDIT_METRIC_KEYS},
        "rejected_metrics": {key: (rejected.get("rule_metrics") or {}).get(key) for key in AUDIT_METRIC_KEYS},
        "chosen_errors": chosen.get("rule_errors") or [],
        "rejected_errors": rejected.get("rule_errors") or [],
    }
    audit["llamafactory_pair"] = make_lf_pair(prompt_row, chosen, rejected, audit)
    return audit


def stratified_split(pairs: list[dict[str, Any]], val_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_category[str(pair.get("category") or "unknown")].append(pair)
    for category in sorted(by_category):
        rows = list(by_category[category])
        rng.shuffle(rows)
        val_count = max(1, round(len(rows) * val_ratio)) if len(rows) > 1 else 0
        val.extend(rows[:val_count])
        train.extend(rows[val_count:])
    train.sort(key=lambda item: str(item.get("pair_id")))
    val.sort(key=lambda item: str(item.get("pair_id")))
    return train, val


def duplicate_counts(rows: list[dict[str, Any]], key: str) -> int:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return sum(1 for value, count in counts.items() if value and count > 1)


def summarize(
    source_rows: int,
    source_candidates: int,
    pairs: list[dict[str, Any]],
    train_pairs: list[dict[str, Any]],
    val_pairs: list[dict[str, Any]],
    skipped: Counter[str],
    available: Counter[str],
    eval_audit: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    gaps = [float(pair.get("score_gap") or 0.0) for pair in pairs]
    fail_keys = Counter(key for pair in pairs for key in pair.get("rejected_planner_fail_keys") or [])
    source_paths = Counter(str((pair.get("metadata") or {}).get("dpo_context_source_path") or "unknown") for pair in pairs)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_prefix": args.dataset_prefix,
        "source_candidates": args.merged_candidates.relative_to(PROJECT_ROOT).as_posix(),
        "source_prompts": args.prompts.relative_to(PROJECT_ROOT).as_posix(),
        "source_rows": source_rows,
        "source_candidate_total": source_candidates,
        "available_pair_candidates": dict(available),
        "quotas": dict(args.quota),
        "selected_pairs": len(pairs),
        "train": len(train_pairs),
        "val": len(val_pairs),
        "category_counts": dict(Counter(str(pair.get("category") or "unknown") for pair in pairs)),
        "bucket_counts": dict(Counter(str(pair.get("bucket") or "unknown") for pair in pairs)),
        "budget_level_counts": dict(Counter(str(pair.get("budget_level") or "unknown") for pair in pairs)),
        "budget_strictness_counts": dict(Counter(str(pair.get("budget_strictness") or "unknown") for pair in pairs)),
        "chosen_sources": dict(Counter(str(pair.get("chosen_source") or "unknown") for pair in pairs)),
        "rejected_sources": dict(Counter(str(pair.get("rejected_source") or "unknown") for pair in pairs)),
        "chosen_budget_status": dict(Counter(str(pair.get("chosen_budget_status") or "unknown") for pair in pairs)),
        "rejected_budget_status": dict(Counter(str(pair.get("rejected_budget_status") or "unknown") for pair in pairs)),
        "rejected_planner_fail_keys": dict(fail_keys),
        "source_path_counts": dict(source_paths),
        "skipped": dict(skipped),
        "score_gap_min": round(min(gaps), 4) if gaps else None,
        "score_gap_avg": round(sum(gaps) / len(gaps), 4) if gaps else None,
        "score_gap_max": round(max(gaps), 4) if gaps else None,
        "duplicate_prompt_hashes": {
            "all": duplicate_counts(pairs, "prompt_hash"),
            "train": duplicate_counts(train_pairs, "prompt_hash"),
            "val": duplicate_counts(val_pairs, "prompt_hash"),
        },
        "duplicate_request_signatures": {
            "all": duplicate_counts(pairs, "request_signature_sha256"),
            "train": duplicate_counts(train_pairs, "request_signature_sha256"),
            "val": duplicate_counts(val_pairs, "request_signature_sha256"),
        },
        "anti_leak": {
            **eval_audit,
            "selected_eval_signature_overlap": 0,
            "policy": "Rows with request_signature in frozen eval sources are skipped before pair selection.",
        },
        "filters": {
            "chosen": "schema_ok && generation_clean && sft_hard_pass && planner_soft_pass && strict clean metrics",
            "rejected": "schema_ok && generation_clean && sft_hard_pass && !planner_soft_pass && grounding/weather guardrails",
            "one_pair_per_request_signature": True,
            "val_ratio": args.val_ratio,
            "seed": args.seed,
        },
    }


def parse_quota(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("quota must be CATEGORY=COUNT")
    key, count = value.split("=", 1)
    if key not in DEFAULT_QUOTAS:
        raise argparse.ArgumentTypeError(f"unknown quota category: {key}")
    try:
        return key, int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quota count must be an integer") from exc


def parse_args() -> argparse.Namespace:
    default_root = PROJECT_ROOT / "training/data/planner/dpo/260520_closing_budget_clean"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--merged-candidates",
        type=Path,
        default=PROJECT_ROOT / "training/data/planner/dpo/260518_planner_soft2400/filtered_pairs_planner_soft_clean/merged_candidates.jsonl",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=PROJECT_ROOT / "training/data/planner/dpo/260518_planner_soft2400/prompts.jsonl",
    )
    parser.add_argument("--output-dir", type=Path, default=default_root)
    parser.add_argument("--lf-output-dir", type=Path, default=LLAMAFACTORY_DIR / "generated")
    parser.add_argument("--dataset-prefix", default="trip_planner_dpo_260520_closing_budget_clean")
    parser.add_argument("--eval-source", action="append", type=Path, default=None)
    parser.add_argument("--quota", type=parse_quota, action="append", default=None)
    parser.add_argument("--val-ratio", type=float, default=0.08)
    parser.add_argument("--seed", type=int, default=260520)
    parser.add_argument("--update-dataset-info", action="store_true")
    args = parser.parse_args()
    args.merged_candidates = args.merged_candidates if args.merged_candidates.is_absolute() else PROJECT_ROOT / args.merged_candidates
    args.prompts = args.prompts if args.prompts.is_absolute() else PROJECT_ROOT / args.prompts
    args.output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    args.lf_output_dir = args.lf_output_dir if args.lf_output_dir.is_absolute() else PROJECT_ROOT / args.lf_output_dir
    eval_sources = args.eval_source or DEFAULT_EVAL_SOURCES
    args.eval_source = [path if path.is_absolute() else PROJECT_ROOT / path for path in eval_sources]
    args.quota = dict(args.quota or DEFAULT_QUOTAS.items())
    return args


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.merged_candidates)
    prompts = load_prompts(args.prompts)
    eval_signatures, eval_audit = load_eval_signatures(args.eval_source)

    skipped: Counter[str] = Counter()
    available: Counter[str] = Counter()
    candidates_by_category: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    seen_source_signatures: set[str] = set()

    for row in rows:
        signature = request_signature(row)
        if signature in eval_signatures:
            skipped["eval_signature_overlap"] += 1
            continue
        if signature in seen_source_signatures:
            skipped["duplicate_source_signature"] += 1
            continue
        seen_source_signatures.add(signature)

        prompt_row = prompts.get(str(row.get("prompt_id")))
        if not prompt_row:
            skipped["missing_prompt"] += 1
            continue

        for category in args.quota:
            pair, reason = make_pair_candidate(row, prompt_row, category)
            if not pair:
                skipped[reason] += 1
                continue
            available[category] += 1
            candidates_by_category[category].append((row, pair))

    selected: list[dict[str, Any]] = []
    used_signatures: set[str] = set()
    rng = random.Random(args.seed)
    for category, quota in args.quota.items():
        pool = list(candidates_by_category.get(category) or [])
        rng.shuffle(pool)
        pool.sort(key=lambda item: float(item[1].get("priority") or 0.0), reverse=True)
        for row, pair in pool:
            if len([item for item in selected if item.get("category") == category]) >= quota:
                break
            signature = request_signature(row)
            if signature in used_signatures:
                skipped[f"{category}:duplicate_selected_signature"] += 1
                continue
            pair_id = f"{args.dataset_prefix}_{len(selected) + 1:06d}"
            selected.append(audit_pair(pair_id, row, pair))
            used_signatures.add(signature)

    train_pairs, val_pairs = stratified_split(selected, args.val_ratio, args.seed)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.lf_output_dir.mkdir(parents=True, exist_ok=True)
    train_file = args.lf_output_dir / f"{args.dataset_prefix}_train.json"
    val_file = args.lf_output_dir / f"{args.dataset_prefix}_val.json"
    pairs_file = args.output_dir / "pairs.jsonl"
    summary_file = args.output_dir / "summary.json"

    write_json(train_file, [pair["llamafactory_pair"] for pair in train_pairs])
    write_json(val_file, [pair["llamafactory_pair"] for pair in val_pairs])
    write_jsonl(pairs_file, [{key: value for key, value in pair.items() if key != "llamafactory_pair"} for pair in selected])

    summary = summarize(
        len(rows),
        sum(len(row.get("candidates") or []) for row in rows),
        selected,
        train_pairs,
        val_pairs,
        skipped,
        available,
        eval_audit,
        args,
    )
    summary.update(
        {
            "pairs": pairs_file.relative_to(PROJECT_ROOT).as_posix(),
            "lf_train": train_file.relative_to(PROJECT_ROOT).as_posix(),
            "lf_val": val_file.relative_to(PROJECT_ROOT).as_posix(),
        }
    )
    write_json(summary_file, summary)

    if args.update_dataset_info:
        register_dataset(f"{args.dataset_prefix}_train", train_file, f"{args.dataset_prefix}_val", val_file)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
