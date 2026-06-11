#!/usr/bin/env python3
"""Build LLaMAFactory SFT data from replay rows plus Best-of-N winners."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
LLAMAFACTORY_DIR = PROJECT_ROOT / "training/data/llamafactory"
GENERATED_DIR = LLAMAFACTORY_DIR / "generated"
MANIFEST_DIR = LLAMAFACTORY_DIR / "manifests"


def read_json(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON list: {path}")
    return data


def write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_yaml_entry(path: Path, name: str, json_path: Path) -> None:
    path.write_text(
        f"{name}:\n  path: {json_path}\n  source: local\n  converter: alpaca\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--old-train",
        type=Path,
        default=GENERATED_DIR / "trip_260511_main_clean_plus_realbudget_usage700_train.json",
    )
    parser.add_argument(
        "--old-val",
        type=Path,
        default=GENERATED_DIR / "trip_260511_main_clean_plus_realbudget_usage700_val.json",
    )
    parser.add_argument("--bestofn-train", type=Path, required=True)
    parser.add_argument("--bestofn-val", type=Path, required=True)
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--oversample-ratio", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=260513)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)

    old_train = read_json(args.old_train)
    old_val = read_json(args.old_val)
    bestofn_train = read_json(args.bestofn_train)
    bestofn_val = read_json(args.bestofn_val)

    oversample_count = int(round(len(bestofn_train) * args.oversample_ratio))
    oversampled = [rng.choice(bestofn_train) for _ in range(oversample_count)] if bestofn_train else []

    train_rows = old_train + bestofn_train + oversampled
    val_rows = old_val + bestofn_val
    rng.shuffle(train_rows)
    rng.shuffle(val_rows)

    train_json = GENERATED_DIR / f"{args.output_prefix}_train.json"
    val_json = GENERATED_DIR / f"{args.output_prefix}_val.json"
    train_yaml = GENERATED_DIR / f"{args.output_prefix}_train.yaml"
    val_yaml = GENERATED_DIR / f"{args.output_prefix}_val.yaml"
    manifest_path = MANIFEST_DIR / f"{args.output_prefix}_manifest.json"

    write_json(train_json, train_rows)
    write_json(val_json, val_rows)
    write_yaml_entry(train_yaml, f"{args.output_prefix}_train", train_json)
    write_yaml_entry(val_yaml, f"{args.output_prefix}_val", val_json)

    manifest = {
        "train_output": str(train_json),
        "val_output": str(val_json),
        "old_train": len(old_train),
        "bestofn_train": len(bestofn_train),
        "bestofn_oversample": oversample_count,
        "train_total": len(train_rows),
        "old_val": len(old_val),
        "bestofn_val": len(bestofn_val),
        "val_total": len(val_rows),
        "bestofn_train_effective_ratio": round((len(bestofn_train) + oversample_count) / len(train_rows), 4)
        if train_rows
        else 0.0,
        "shuffle_seed": args.seed,
        "oversample_ratio": args.oversample_ratio,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
