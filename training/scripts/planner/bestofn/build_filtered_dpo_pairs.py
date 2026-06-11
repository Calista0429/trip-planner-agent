#!/usr/bin/env python3
"""Build filtered DPO pairs from Best-of-N candidate pools.

This script is intentionally stricter than the generic Best-of-N exporter:

- chosen responses must be schema-valid and hard-pass whenever possible;
- rejected responses must also be schema-valid;
- most pairs compare hard-pass responses against weaker hard-pass responses;
- a small controlled slice compares hard-pass responses against schema-valid
  hard-fail responses to preserve hard constraints.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_DIR = Path(__file__).resolve().parent
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"
DATASET_INFO = LLAMAFACTORY_DIR / "dataset_info.json"

sys.path.insert(0, str(SCRIPT_DIR))

from select_best import make_training_prompt, score_candidate  # noqa: E402


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, rows: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_prompt_map(path: Path) -> dict[str, dict[str, Any]]:
    return {row["prompt_id"]: row for row in read_jsonl(path)}


def bool_metric(candidate: dict[str, Any], key: str) -> bool:
    return (candidate.get("rule_metrics") or {}).get(key) is True


def candidate_quality(candidate: dict[str, Any]) -> dict[str, Any]:
    meta = score_candidate(candidate)
    item = dict(candidate)
    item["dpo_score"] = float(meta["score"])
    item["dpo_score_meta"] = meta
    item["schema_ok_for_dpo"] = bool(meta.get("schema_ok")) and bool_metric(candidate, "schema_ok")
    item["hard_pass_for_dpo"] = bool(meta.get("hard_pass")) and bool_metric(candidate, "sft_hard_pass")
    return item


def make_lf_pair(prompt_row: dict[str, Any], chosen: dict[str, Any], rejected: dict[str, Any], pair_type: str) -> dict[str, Any]:
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
            f"{pair_type}; score {chosen.get('dpo_score')} > {rejected.get('dpo_score')}; "
            f"chosen={chosen.get('candidate_id')} rejected={rejected.get('candidate_id')}"
        ),
    }


def make_audit_pair(
    row: dict[str, Any],
    prompt_row: dict[str, Any],
    chosen: dict[str, Any],
    rejected: dict[str, Any],
    pair_type: str,
) -> dict[str, Any]:
    chosen_metrics = chosen.get("rule_metrics") or {}
    rejected_metrics = rejected.get("rule_metrics") or {}
    return {
        "pair_id": "",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_id": row.get("prompt_id"),
        "record_id": row.get("record_id"),
        "pair_type": pair_type,
        "chosen_candidate_id": chosen.get("candidate_id"),
        "rejected_candidate_id": rejected.get("candidate_id"),
        "chosen_score": chosen.get("dpo_score"),
        "rejected_score": rejected.get("dpo_score"),
        "score_gap": round(float(chosen.get("dpo_score", 0.0)) - float(rejected.get("dpo_score", 0.0)), 4),
        "chosen_temperature": chosen.get("temperature"),
        "rejected_temperature": rejected.get("temperature"),
        "chosen_hard_pass": chosen.get("hard_pass_for_dpo"),
        "rejected_hard_pass": rejected.get("hard_pass_for_dpo"),
        "chosen_schema_ok": chosen.get("schema_ok_for_dpo"),
        "rejected_schema_ok": rejected.get("schema_ok_for_dpo"),
        "metadata": row.get("metadata") or {},
        "chosen_metrics": {
            "sft_hard_pass": chosen_metrics.get("sft_hard_pass"),
            "dpo_soft_pass": chosen_metrics.get("dpo_soft_pass"),
            "dpo_soft_recomputed_budget_pass": chosen_metrics.get("dpo_soft_recomputed_budget_pass"),
            "recomputed_budget_fit_ok": chosen_metrics.get("recomputed_budget_fit_ok"),
            "budget_relationship_ok": chosen_metrics.get("budget_relationship_ok"),
            "budget_preference_aligned": chosen_metrics.get("budget_preference_aligned"),
            "meal_cost_scale_ok": chosen_metrics.get("meal_cost_scale_ok"),
            "budget_arithmetic_consistent": chosen_metrics.get("budget_arithmetic_consistent"),
        },
        "rejected_metrics": {
            "sft_hard_pass": rejected_metrics.get("sft_hard_pass"),
            "dpo_soft_pass": rejected_metrics.get("dpo_soft_pass"),
            "dpo_soft_recomputed_budget_pass": rejected_metrics.get("dpo_soft_recomputed_budget_pass"),
            "recomputed_budget_fit_ok": rejected_metrics.get("recomputed_budget_fit_ok"),
            "budget_relationship_ok": rejected_metrics.get("budget_relationship_ok"),
            "budget_preference_aligned": rejected_metrics.get("budget_preference_aligned"),
            "meal_cost_scale_ok": rejected_metrics.get("meal_cost_scale_ok"),
            "budget_arithmetic_consistent": rejected_metrics.get("budget_arithmetic_consistent"),
        },
        "llamafactory_pair": make_lf_pair(prompt_row, chosen, rejected, pair_type),
    }


def should_use_hardfail_pair(index: int, hard_fail_ratio: float) -> bool:
    if hard_fail_ratio <= 0:
        return False
    period = max(1, round(1.0 / hard_fail_ratio))
    return index % period == 0


def select_pair_for_prompt(
    row: dict[str, Any],
    prompt_row: dict[str, Any],
    args: argparse.Namespace,
    prompt_index: int,
) -> tuple[dict[str, Any] | None, str]:
    scored = [candidate_quality(candidate) for candidate in row.get("candidates") or []]
    schema_ok = [item for item in scored if item.get("schema_ok_for_dpo")]
    hard_ok = [item for item in schema_ok if item.get("hard_pass_for_dpo")]
    if not hard_ok:
        return None, "no_hardpass_chosen"

    chosen = sorted(hard_ok, key=lambda item: item.get("dpo_score", -9999.0), reverse=True)[0]
    chosen_score = float(chosen.get("dpo_score", 0.0))

    hard_rejected = [
        item
        for item in hard_ok
        if item.get("candidate_id") != chosen.get("candidate_id")
        and chosen_score - float(item.get("dpo_score", 0.0)) >= args.min_score_gap
    ]
    hardfail_rejected = [
        item
        for item in schema_ok
        if item.get("candidate_id") != chosen.get("candidate_id")
        and not item.get("hard_pass_for_dpo")
        and chosen_score - float(item.get("dpo_score", 0.0)) >= args.min_score_gap
    ]

    prefer_hardfail = should_use_hardfail_pair(prompt_index, args.hard_fail_ratio)
    pair_type = ""
    rejected: dict[str, Any] | None = None
    if prefer_hardfail and hardfail_rejected:
        pair_type = "hardpass_vs_schema_hardfail"
        rejected = sorted(hardfail_rejected, key=lambda item: item.get("dpo_score", 0.0))[0]
    elif hard_rejected:
        pair_type = "hardpass_vs_hardpass"
        rejected = sorted(hard_rejected, key=lambda item: item.get("dpo_score", 0.0))[0]
    elif hardfail_rejected:
        pair_type = "hardpass_vs_schema_hardfail"
        rejected = sorted(hardfail_rejected, key=lambda item: item.get("dpo_score", 0.0))[0]

    if not rejected:
        return None, "no_rejected_after_gap"

    return make_audit_pair(row, prompt_row, chosen, rejected, pair_type), "ok"


def split_rows(rows: list[Any], val_ratio: float, seed: int) -> tuple[list[Any], list[Any]]:
    rows = list(rows)
    rng = random.Random(seed)
    rng.shuffle(rows)
    val_size = max(1, round(len(rows) * val_ratio)) if len(rows) > 1 else 0
    return rows[val_size:], rows[:val_size]


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


def summarize(pairs: list[dict[str, Any]], skipped: Counter[str], args: argparse.Namespace) -> dict[str, Any]:
    pair_types = Counter(pair["pair_type"] for pair in pairs)
    budget_levels = Counter((pair.get("metadata") or {}).get("budget_level", "unknown") for pair in pairs)
    companion_types = Counter((pair.get("metadata") or {}).get("companion_type", "unknown") for pair in pairs)
    score_gaps = [float(pair["score_gap"]) for pair in pairs]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompts": str(args.prompts),
        "candidates": str(args.candidates),
        "total_pairs": len(pairs),
        "pair_types": dict(pair_types),
        "pair_type_rates": {key: round(value / len(pairs), 4) for key, value in pair_types.items()} if pairs else {},
        "skipped": dict(skipped),
        "budget_level": dict(budget_levels),
        "companion_type": dict(companion_types),
        "score_gap_min": round(min(score_gaps), 4) if score_gaps else None,
        "score_gap_avg": round(sum(score_gaps) / len(score_gaps), 4) if score_gaps else None,
        "score_gap_max": round(max(score_gaps), 4) if score_gaps else None,
        "min_score_gap": args.min_score_gap,
        "hard_fail_ratio_target": args.hard_fail_ratio,
        "seed": args.seed,
        "val_ratio": args.val_ratio,
    }


def parse_args() -> argparse.Namespace:
    default_root = PROJECT_ROOT / "training/data/planner/bestofn/260512_anti_leak1200_vllm23_w8"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", type=Path, default=default_root / "prompts.jsonl")
    parser.add_argument("--candidates", type=Path, default=default_root / "candidates.jsonl")
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "training/data/planner/dpo/260516_bestofn1200_filtered")
    parser.add_argument("--lf-output-dir", type=Path, default=LLAMAFACTORY_DIR / "generated")
    parser.add_argument("--dataset-prefix", default="trip_planner_dpo_260516_bestofn1200_filtered")
    parser.add_argument("--smoke-prefix", default="trip_planner_dpo_260516_bestofn1200_filtered_smoke")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=260516)
    parser.add_argument("--min-score-gap", type=float, default=1.0)
    parser.add_argument("--hard-fail-ratio", type=float, default=0.2)
    parser.add_argument("--smoke-train-size", type=int, default=300)
    parser.add_argument("--smoke-val-size", type=int, default=50)
    parser.add_argument("--update-dataset-info", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    prompt_map = load_prompt_map(args.prompts)
    pairs: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    prompt_index = 0

    for row in read_jsonl(args.candidates):
        prompt_id = row.get("prompt_id")
        prompt_row = prompt_map.get(prompt_id)
        if not prompt_row:
            skipped["missing_prompt"] += 1
            continue
        pair, reason = select_pair_for_prompt(row, prompt_row, args, prompt_index)
        prompt_index += 1
        if not pair:
            skipped[reason] += 1
            continue
        pair["pair_id"] = f"{args.dataset_prefix}_{len(pairs) + 1:06d}"
        pairs.append(pair)

    rng = random.Random(args.seed)
    rng.shuffle(pairs)
    train_pairs, val_pairs = split_rows(pairs, args.val_ratio, args.seed)

    lf_train = [pair["llamafactory_pair"] for pair in train_pairs]
    lf_val = [pair["llamafactory_pair"] for pair in val_pairs]
    lf_train_path = args.lf_output_dir / f"{args.dataset_prefix}_train.json"
    lf_val_path = args.lf_output_dir / f"{args.dataset_prefix}_val.json"
    write_json(lf_train_path, lf_train)
    write_json(lf_val_path, lf_val)

    audit_pairs = [{key: value for key, value in pair.items() if key != "llamafactory_pair"} for pair in pairs]
    write_jsonl(args.output_dir / "pairs.jsonl", audit_pairs)
    write_json(args.output_dir / "summary.json", summarize(pairs, skipped, args) | {"train": len(train_pairs), "val": len(val_pairs)})

    smoke_rows = list(train_pairs)
    rng.shuffle(smoke_rows)
    smoke_train_pairs = smoke_rows[: args.smoke_train_size]
    remaining_for_val = smoke_rows[args.smoke_train_size :]
    smoke_val_pairs = remaining_for_val[: args.smoke_val_size] if len(remaining_for_val) >= args.smoke_val_size else val_pairs[: args.smoke_val_size]
    smoke_train = [pair["llamafactory_pair"] for pair in smoke_train_pairs]
    smoke_val = [pair["llamafactory_pair"] for pair in smoke_val_pairs]
    smoke_train_path = args.lf_output_dir / f"{args.smoke_prefix}_train.json"
    smoke_val_path = args.lf_output_dir / f"{args.smoke_prefix}_val.json"
    write_json(smoke_train_path, smoke_train)
    write_json(smoke_val_path, smoke_val)

    if args.update_dataset_info:
        update_dataset_info(
            lf_train_path,
            lf_val_path,
            f"{args.dataset_prefix}_train",
            f"{args.dataset_prefix}_val",
        )
        update_dataset_info(
            smoke_train_path,
            smoke_val_path,
            f"{args.smoke_prefix}_train",
            f"{args.smoke_prefix}_val",
        )

    result = {
        "pairs": len(pairs),
        "train": len(lf_train),
        "val": len(lf_val),
        "smoke_train": len(smoke_train),
        "smoke_val": len(smoke_val),
        "lf_train": str(lf_train_path),
        "lf_val": str(lf_val_path),
        "smoke_train_path": str(smoke_train_path),
        "smoke_val_path": str(smoke_val_path),
        "summary": str(args.output_dir / "summary.json"),
        "skipped": dict(skipped),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
