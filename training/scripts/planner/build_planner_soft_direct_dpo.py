#!/usr/bin/env python3
"""Materialize planner-soft direct DPO pairs for LLaMA-Factory."""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"
DATASET_INFO = LLAMAFACTORY_DIR / "dataset_info.json"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def load_candidates(root: Path, source_dirs: list[str]) -> dict[str, dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for source_dir in source_dirs:
        path = root / source_dir / "candidates.jsonl"
        for row in read_jsonl(path):
            for candidate in row.get("candidates") or []:
                candidates[candidate["candidate_id"]] = candidate
    return candidates


def is_planner_soft(candidate: dict[str, Any]) -> bool:
    return (candidate.get("rule_metrics") or {}).get("planner_soft_pass") is True


def select_pairs(
    pairs: list[dict[str, Any]],
    candidates: dict[str, dict[str, Any]],
    *,
    min_score_gap: float,
    exclude_fallback: bool,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    selected: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for pair in pairs:
        if exclude_fallback and "fallback" in str(pair.get("pair_type", "")):
            skipped["fallback_pair"] += 1
            continue
        if float(pair.get("score_gap") or 0.0) < min_score_gap:
            skipped["low_score_gap"] += 1
            continue
        chosen = candidates.get(str(pair.get("chosen_candidate_id")))
        rejected = candidates.get(str(pair.get("rejected_candidate_id")))
        if not chosen or not rejected:
            skipped["missing_candidate"] += 1
            continue
        if not is_planner_soft(chosen):
            skipped["chosen_not_planner_soft"] += 1
            continue
        if is_planner_soft(rejected):
            skipped["rejected_planner_soft"] += 1
            continue
        selected.append(pair)
    selected.sort(key=lambda row: str(row.get("pair_id", "")))
    return selected, skipped


def split_by_bucket(rows: list[dict[str, Any]], val_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_bucket[str(row.get("bucket", "unknown"))].append(row)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for bucket in sorted(by_bucket):
        bucket_rows = list(by_bucket[bucket])
        rng.shuffle(bucket_rows)
        val_count = max(1, round(len(bucket_rows) * val_ratio)) if len(bucket_rows) > 1 else 0
        val.extend(bucket_rows[:val_count])
        train.extend(bucket_rows[val_count:])

    train.sort(key=lambda row: str(row.get("pair_id", "")))
    val.sort(key=lambda row: str(row.get("pair_id", "")))
    return train, val


def make_lf_row(pair: dict[str, Any], prompts: dict[str, dict[str, Any]], candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prompt = prompts[str(pair["prompt_id"])]
    chosen = candidates[str(pair["chosen_candidate_id"])]
    rejected = candidates[str(pair["rejected_candidate_id"])]
    return {
        "conversations": [{"from": "human", "value": prompt["prompt"]}],
        "chosen": {"from": "gpt", "value": chosen.get("output_text", "")},
        "rejected": {"from": "gpt", "value": rejected.get("output_text", "")},
        "preference_reason": (
            f"{pair.get('bucket')}:planner_soft_direct; "
            f"score_gap={pair.get('score_gap')}; "
            f"chosen_planner_soft=true rejected_planner_soft=false; "
            f"chosen={pair.get('chosen_candidate_id')} rejected={pair.get('rejected_candidate_id')}"
        ),
    }


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT / "training/data/planner/dpo/260517_failure_driven600_enriched")
    parser.add_argument("--pairs", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--dataset-prefix", default="trip_planner_dpo_260517_fd600_planner_soft_direct402")
    parser.add_argument("--source-dirs", nargs="+", default=["gpu1", "gpu2", "gpu3", "gpu4", "mimo"])
    parser.add_argument("--min-score-gap", type=float, default=8.0)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=260518)
    parser.add_argument("--include-fallback", action="store_true")
    args = parser.parse_args()

    root = args.root
    pairs_path = args.pairs or root / "filtered_pairs_rule_mixed/pairs.jsonl"
    output_dir = args.output_dir or root / "filtered_pairs_planner_soft_direct402"
    prompts = {row["prompt_id"]: row for row in read_jsonl(root / "prompts.jsonl")}
    candidates = load_candidates(root, args.source_dirs)
    pairs, skipped = select_pairs(
        read_jsonl(pairs_path),
        candidates,
        min_score_gap=args.min_score_gap,
        exclude_fallback=not args.include_fallback,
    )
    train_pairs, val_pairs = split_by_bucket(pairs, args.val_ratio, args.seed)

    train_file = LLAMAFACTORY_DIR / "generated" / f"{args.dataset_prefix}_train.json"
    val_file = LLAMAFACTORY_DIR / "generated" / f"{args.dataset_prefix}_val.json"
    write_json(train_file, [make_lf_row(pair, prompts, candidates) for pair in train_pairs])
    write_json(val_file, [make_lf_row(pair, prompts, candidates) for pair in val_pairs])
    write_jsonl(output_dir / "pairs.jsonl", pairs)

    summary = {
        "dataset_prefix": args.dataset_prefix,
        "selected_pairs": len(pairs),
        "train": len(train_pairs),
        "val": len(val_pairs),
        "bucket_counts_all": dict(Counter(str(row.get("bucket", "unknown")) for row in pairs)),
        "bucket_counts_train": dict(Counter(str(row.get("bucket", "unknown")) for row in train_pairs)),
        "bucket_counts_val": dict(Counter(str(row.get("bucket", "unknown")) for row in val_pairs)),
        "skipped": dict(skipped),
        "filters": {
            "exclude_fallback": not args.include_fallback,
            "min_score_gap": args.min_score_gap,
            "chosen_planner_soft_pass": True,
            "rejected_planner_soft_pass": False,
        },
        "train_file": train_file.relative_to(PROJECT_ROOT).as_posix(),
        "val_file": val_file.relative_to(PROJECT_ROOT).as_posix(),
    }
    write_json(output_dir / "summary.json", summary)
    register_dataset(f"{args.dataset_prefix}_train", train_file, f"{args.dataset_prefix}_val", val_file)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
