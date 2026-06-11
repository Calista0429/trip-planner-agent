#!/usr/bin/env python3
"""Build clean planner-soft direct DPO pairs from generated candidates."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"
DATASET_INFO = LLAMAFACTORY_DIR / "dataset_info.json"

PLANNER_KEYS = [
    "attraction_diversity_ok",
    "meal_diversity_ok",
    "meal_cost_scale_ok",
    "recomputed_budget_user_constraint_ok",
    "recomputed_budget_fit_ok",
]

PLANNER_WEIGHTS = {
    "recomputed_budget_fit_ok": 32.0,
    "recomputed_budget_user_constraint_ok": 24.0,
    "meal_diversity_ok": 18.0,
    "attraction_diversity_ok": 18.0,
    "meal_cost_scale_ok": 16.0,
}

QUALITY_WEIGHTS = {
    "budget_relationship_ok": 8.0,
    "budget_arithmetic_consistent": 8.0,
    "hotel_budget_covers_nights": 6.0,
    "meal_grounding_ok": 6.0,
    "attraction_grounding_ok": 6.0,
    "hotel_grounding_ok": 5.0,
    "weather_match": 5.0,
    "meal_repeat_limit_ok": 4.0,
    "attraction_repeat_limit_ok": 4.0,
}

RATE_WEIGHTS = {
    "meal_diversity_unique_rate": 5.0,
    "attraction_diversity_unique_rate": 5.0,
    "meal_grounding_rate": 4.0,
    "attraction_grounding_rate": 4.0,
    "hotel_grounding_rate": 3.0,
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


def schema_ok(candidate: dict[str, Any]) -> bool:
    return (
        candidate.get("parsed_ok") is True
        and candidate.get("schema_ok") is True
        and bool_metric(candidate, "json_extract_ok")
        and bool_metric(candidate, "schema_ok")
    )


def generation_clean(candidate: dict[str, Any]) -> bool:
    meta = candidate.get("generation_meta") or {}
    finish_reason = meta.get("finish_reason")
    return bool(candidate.get("output_text", "").strip()) and meta.get("ok") is True and finish_reason in {None, "stop"}


def hard_ok(candidate: dict[str, Any]) -> bool:
    return schema_ok(candidate) and generation_clean(candidate) and bool_metric(candidate, "sft_hard_pass")


def planner_soft_ok(candidate: dict[str, Any]) -> bool:
    return bool_metric(candidate, "planner_soft_pass")


def source_kind(candidate: dict[str, Any]) -> str:
    if candidate.get("source_type") == "strong" or candidate.get("source_model") == "mimo":
        return "mimo"
    return "local"


def planner_fail_keys(candidate: dict[str, Any]) -> list[str]:
    return [key for key in PLANNER_KEYS if not bool_metric(candidate, key)]


def clean_score(candidate: dict[str, Any]) -> tuple[float, dict[str, float]]:
    components: dict[str, float] = {}
    score = 0.0
    for key, weight in PLANNER_WEIGHTS.items():
        delta = weight if bool_metric(candidate, key) else 0.0
        components[key] = delta
        score += delta
    for key, weight in QUALITY_WEIGHTS.items():
        delta = weight if bool_metric(candidate, key) else 0.0
        components[key] = delta
        score += delta
    for key, weight in RATE_WEIGHTS.items():
        delta = float_metric(candidate, key) * weight
        components[key] = round(delta, 4)
        score += delta
    if source_kind(candidate) == "mimo":
        components["mimo_tiebreak"] = 1.0
        score += 1.0
    return round(score, 4), components


def make_training_prompt(system_prompt: str, prompt: str) -> str:
    return f"{system_prompt.strip()}\n\n{prompt.strip()}".strip()


def make_lf_pair(prompt_row: dict[str, Any], chosen: dict[str, Any], rejected: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
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
            f"{pair['bucket']}:planner_soft_clean_hard_vs_hard; "
            f"score_gap={pair['score_gap']}; "
            f"rejected_failed={','.join(pair.get('rejected_planner_fail_keys') or [])}; "
            f"chosen={chosen.get('candidate_id')} rejected={rejected.get('candidate_id')}"
        ),
    }


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        records[str(row.get("record_id"))] = row
    return records


def load_prompts(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row["prompt_id"]): row for row in read_jsonl(path)}


def merge_candidates(root: Path, source_dirs: list[str], records: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for source_dir in source_dirs:
        path = root / source_dir / "candidates.jsonl"
        for row in read_jsonl(path):
            prompt_id = str(row.get("prompt_id") or "")
            if not prompt_id:
                continue
            record_id = str(row.get("record_id") or prompt_id)
            record = records.get(record_id) or {}
            metadata = dict((record.get("metadata") or row.get("metadata") or {}))
            item = merged.setdefault(
                prompt_id,
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prompt_id": prompt_id,
                    "record_id": record_id,
                    "metadata": metadata,
                    "request": row.get("request") or record.get("request") or {},
                    "control_spec": row.get("control_spec") or record.get("control_spec") or {},
                    "candidate_sources": [],
                    "candidates": [],
                },
            )
            item["candidate_sources"].append(source_dir)
            seen_ids = {candidate.get("candidate_id") for candidate in item["candidates"]}
            for candidate in row.get("candidates") or []:
                if candidate.get("candidate_id") in seen_ids:
                    continue
                item["candidates"].append(candidate)
                seen_ids.add(candidate.get("candidate_id"))
    rows = list(merged.values())
    rows.sort(key=lambda item: str(item.get("prompt_id", "")))
    return rows


def select_pair(row: dict[str, Any], min_score_gap: float) -> tuple[dict[str, Any] | None, str]:
    scored: list[dict[str, Any]] = []
    for candidate in row.get("candidates") or []:
        item = dict(candidate)
        score, components = clean_score(candidate)
        item["clean_score"] = score
        item["clean_score_components"] = components
        item["clean_schema_ok"] = schema_ok(candidate)
        item["clean_hard_ok"] = hard_ok(candidate)
        item["clean_planner_soft_ok"] = planner_soft_ok(candidate)
        item["clean_source_kind"] = source_kind(candidate)
        item["planner_fail_keys"] = planner_fail_keys(candidate)
        scored.append(item)

    chosen_pool = [item for item in scored if item["clean_hard_ok"] and item["clean_planner_soft_ok"]]
    if not chosen_pool:
        return None, "no_clean_chosen"

    rejected_pool = [
        item
        for item in scored
        if item["clean_hard_ok"]
        and not item["clean_planner_soft_ok"]
        and item.get("candidate_id") not in {candidate.get("candidate_id") for candidate in chosen_pool}
    ]
    if not rejected_pool:
        return None, "no_clean_hard_rejected"

    chosen = sorted(
        chosen_pool,
        key=lambda item: (float(item.get("clean_score") or 0.0), item["clean_source_kind"] == "mimo"),
        reverse=True,
    )[0]
    rejected = sorted(
        rejected_pool,
        key=lambda item: (float(item.get("clean_score") or 0.0), item["clean_source_kind"] == "mimo"),
    )[0]
    score_gap = round(float(chosen["clean_score"]) - float(rejected["clean_score"]), 4)
    if score_gap < min_score_gap:
        return None, "low_score_gap"

    bucket = str((row.get("metadata") or {}).get("dpo_context_bucket", "unknown"))
    return {
        "bucket": bucket,
        "pair_type": f"{bucket}:planner_soft_hardpass_vs_hardpass_fail",
        "score_gap": score_gap,
        "chosen": chosen,
        "rejected": rejected,
        "rejected_planner_fail_keys": rejected.get("planner_fail_keys") or [],
    }, "ok"


def audit_pair(pair_id: str, row: dict[str, Any], prompt_row: dict[str, Any], pair: dict[str, Any]) -> dict[str, Any]:
    chosen = pair["chosen"]
    rejected = pair["rejected"]
    metric_keys = [
        "sft_hard_pass",
        "planner_soft_pass",
        "dpo_soft_pass",
        "dpo_soft_recomputed_budget_pass",
        "recomputed_budget_user_constraint_ok",
        "recomputed_budget_fit_ok",
        "budget_preference_aligned",
        "budget_relationship_ok",
        "budget_arithmetic_consistent",
        "meal_cost_scale_ok",
        "meal_diversity_ok",
        "attraction_diversity_ok",
        "meal_grounding_ok",
        "attraction_grounding_ok",
        "hotel_grounding_ok",
        "weather_match",
    ]
    chosen_metrics = chosen.get("rule_metrics") or {}
    rejected_metrics = rejected.get("rule_metrics") or {}
    audit = {
        "pair_id": pair_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_id": row.get("prompt_id"),
        "record_id": row.get("record_id"),
        "bucket": pair["bucket"],
        "pair_type": pair["pair_type"],
        "score_gap": pair["score_gap"],
        "chosen_candidate_id": chosen.get("candidate_id"),
        "rejected_candidate_id": rejected.get("candidate_id"),
        "chosen_source": chosen.get("clean_source_kind"),
        "rejected_source": rejected.get("clean_source_kind"),
        "chosen_temperature": chosen.get("temperature"),
        "rejected_temperature": rejected.get("temperature"),
        "chosen_score": chosen.get("clean_score"),
        "rejected_score": rejected.get("clean_score"),
        "chosen_schema_ok": chosen.get("clean_schema_ok"),
        "rejected_schema_ok": rejected.get("clean_schema_ok"),
        "chosen_hard_ok": chosen.get("clean_hard_ok"),
        "rejected_hard_ok": rejected.get("clean_hard_ok"),
        "chosen_planner_soft": chosen.get("clean_planner_soft_ok"),
        "rejected_planner_soft": rejected.get("clean_planner_soft_ok"),
        "rejected_planner_fail_keys": rejected.get("planner_fail_keys") or [],
        "metadata": row.get("metadata") or {},
        "candidate_sources": row.get("candidate_sources") or [],
        "chosen_metrics": {key: chosen_metrics.get(key) for key in metric_keys},
        "rejected_metrics": {key: rejected_metrics.get(key) for key in metric_keys},
        "chosen_errors": chosen.get("rule_errors") or [],
        "rejected_errors": rejected.get("rule_errors") or [],
    }
    audit["llamafactory_pair"] = make_lf_pair(prompt_row, chosen, rejected, audit)
    return audit


def stratified_split(pairs: list[dict[str, Any]], val_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pair in pairs:
        by_bucket[str(pair.get("bucket", "unknown"))].append(pair)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for bucket in sorted(by_bucket):
        rows = list(by_bucket[bucket])
        rng.shuffle(rows)
        val_count = max(1, round(len(rows) * val_ratio)) if len(rows) > 1 else 0
        val.extend(rows[:val_count])
        train.extend(rows[val_count:])
    train.sort(key=lambda item: str(item.get("pair_id", "")))
    val.sort(key=lambda item: str(item.get("pair_id", "")))
    return train, val


def register_dataset(train_name: str, train_file: Path, val_name: str, val_file: Path) -> None:
    data = json.loads(DATASET_INFO.read_text(encoding="utf-8")) if DATASET_INFO.exists() else {}
    entry = {
        "ranking": True,
        "formatting": "sharegpt",
        "columns": {"messages": "conversations", "chosen": "chosen", "rejected": "rejected"},
    }
    data[train_name] = {"file_name": train_file.relative_to(LLAMAFACTORY_DIR).as_posix(), **entry}
    data[val_name] = {"file_name": val_file.relative_to(LLAMAFACTORY_DIR).as_posix(), **entry}
    write_json(DATASET_INFO, data)


def summarize(merged: list[dict[str, Any]], pairs: list[dict[str, Any]], skipped: Counter[str], args: argparse.Namespace) -> dict[str, Any]:
    gaps = [float(pair.get("score_gap") or 0.0) for pair in pairs]
    fail_keys = Counter(key for pair in pairs for key in pair.get("rejected_planner_fail_keys") or [])
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "root": str(args.root),
        "merged_prompts": len(merged),
        "candidate_total": sum(len(row.get("candidates") or []) for row in merged),
        "selected_pairs": len(pairs),
        "bucket_counts": dict(Counter(str(pair.get("bucket", "unknown")) for pair in pairs)),
        "pair_types": dict(Counter(str(pair.get("pair_type", "unknown")) for pair in pairs)),
        "chosen_sources": dict(Counter(str(pair.get("chosen_source", "unknown")) for pair in pairs)),
        "rejected_sources": dict(Counter(str(pair.get("rejected_source", "unknown")) for pair in pairs)),
        "rejected_planner_fail_keys": dict(fail_keys),
        "skipped": dict(skipped),
        "score_gap_min": round(min(gaps), 4) if gaps else None,
        "score_gap_avg": round(sum(gaps) / len(gaps), 4) if gaps else None,
        "score_gap_max": round(max(gaps), 4) if gaps else None,
        "filters": {
            "chosen": "schema_ok && generation_clean && sft_hard_pass && planner_soft_pass",
            "rejected": "schema_ok && generation_clean && sft_hard_pass && !planner_soft_pass",
            "min_score_gap": args.min_score_gap,
            "max_pairs_per_prompt": 1,
        },
        "seed": args.seed,
        "val_ratio": args.val_ratio,
    }


def parse_args() -> argparse.Namespace:
    default_root = PROJECT_ROOT / "training/data/planner/dpo/260518_planner_soft2400"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=default_root)
    parser.add_argument("--records", type=Path, default=default_root / "records.jsonl")
    parser.add_argument("--prompts", type=Path, default=default_root / "prompts.jsonl")
    parser.add_argument("--output-dir", type=Path, default=default_root / "filtered_pairs_planner_soft_clean")
    parser.add_argument("--lf-output-dir", type=Path, default=LLAMAFACTORY_DIR / "generated")
    parser.add_argument("--dataset-prefix", default="trip_planner_dpo_260518_planner_soft2400_clean")
    parser.add_argument(
        "--source-dirs",
        nargs="+",
        default=[
            "gpu4",
            "gpu5",
            "gpu7",
            "rebalanced/gpu0",
            "rebalanced/gpu1",
            "rebalanced/gpu2",
            "rebalanced/gpu3",
            "rebalanced/gpu4",
            "rebalanced/gpu5",
            "rebalanced/gpu7",
            "mimo",
        ],
    )
    parser.add_argument("--min-score-gap", type=float, default=14.0)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=260518)
    parser.add_argument("--update-dataset-info", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_records(args.records)
    prompts = load_prompts(args.prompts)
    merged = merge_candidates(args.root, args.source_dirs, records)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "merged_candidates.jsonl", merged)

    pairs: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for row in merged:
        prompt_row = prompts.get(str(row.get("prompt_id")))
        if not prompt_row:
            skipped["missing_prompt"] += 1
            continue
        pair, reason = select_pair(row, args.min_score_gap)
        if not pair:
            skipped[reason] += 1
            continue
        pair_id = f"{args.dataset_prefix}_{len(pairs) + 1:06d}"
        pairs.append(audit_pair(pair_id, row, prompt_row, pair))

    train_pairs, val_pairs = stratified_split(pairs, args.val_ratio, args.seed)
    train_file = args.lf_output_dir / f"{args.dataset_prefix}_train.json"
    val_file = args.lf_output_dir / f"{args.dataset_prefix}_val.json"
    write_json(train_file, [pair["llamafactory_pair"] for pair in train_pairs])
    write_json(val_file, [pair["llamafactory_pair"] for pair in val_pairs])
    write_jsonl(args.output_dir / "pairs.jsonl", [{k: v for k, v in pair.items() if k != "llamafactory_pair"} for pair in pairs])

    summary = summarize(merged, pairs, skipped, args)
    summary.update(
        {
            "train": len(train_pairs),
            "val": len(val_pairs),
            "train_bucket_counts": dict(Counter(str(pair.get("bucket", "unknown")) for pair in train_pairs)),
            "val_bucket_counts": dict(Counter(str(pair.get("bucket", "unknown")) for pair in val_pairs)),
            "merged_candidates": str(args.output_dir / "merged_candidates.jsonl"),
            "pairs": str(args.output_dir / "pairs.jsonl"),
            "lf_train": train_file.relative_to(PROJECT_ROOT).as_posix(),
            "lf_val": val_file.relative_to(PROJECT_ROOT).as_posix(),
            "dataset_prefix": args.dataset_prefix,
        }
    )
    write_json(args.output_dir / "summary.json", summary)

    if args.update_dataset_info:
        register_dataset(f"{args.dataset_prefix}_train", train_file, f"{args.dataset_prefix}_val", val_file)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
