"""把 legacy clean SFT 数据切成 train / val / eval。

示例:

  cd helloagents-trip-planner
  .venv-training-py311/bin/python3 training/scripts/eval/split_sft_data.py

默认比例:

- train: 85%
- val: 5%，只用于训练过程观察 loss
- eval: 10%，冻结为独立评估集，不参与训练和调参
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from shared.common import DATA_DIR, LLAMAFACTORY_DIR, read_jsonl, write_json, write_jsonl  # noqa: E402
from app.agents.prompts import PLANNER_AGENT_PROMPT  # noqa: E402


LEGACY_SFT_DIR = DATA_DIR / "legacy" / "sft"
DEFAULT_INPUT_RECORDS = LEGACY_SFT_DIR / "records_clean.jsonl"
DEFAULT_RECORDS_TRAIN = LEGACY_SFT_DIR / "records_train.jsonl"
DEFAULT_RECORDS_VAL = LEGACY_SFT_DIR / "records_val.jsonl"
DEFAULT_RECORDS_EVAL = LEGACY_SFT_DIR / "records_eval.jsonl"
DEFAULT_LF_TRAIN = LLAMAFACTORY_DIR / "trip_legacy_sft_clean_train.json"
DEFAULT_LF_VAL = LLAMAFACTORY_DIR / "trip_legacy_sft_clean_val.json"
DEFAULT_LF_EVAL = LLAMAFACTORY_DIR / "trip_legacy_sft_clean_eval.json"
DEFAULT_SUMMARY = LEGACY_SFT_DIR / "split_summary.md"
DATASET_INFO_PATH = LLAMAFACTORY_DIR / "dataset_info.json"


def stable_float(value: str) -> float:
    """把字符串稳定映射到 [0, 1)。"""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(16**16)


def weather_bucket(record: dict[str, Any]) -> str:
    """从 PlannerContext 里归纳天气来源类型。"""
    snapshot = ((record.get("planner_context") or {}).get("tool_snapshot") or {})
    sources = {item.get("source", "unknown") for item in snapshot.get("trip_weather") or []}
    if "open_meteo_archive" in sources:
        return "historical"
    if "amap_forecast" in sources:
        return "amap_forecast"
    if "unavailable_future_weather" in sources:
        return "future_unavailable"
    return "unknown"


def stratification_key(record: dict[str, Any]) -> tuple[Any, ...]:
    """轻量分层键，覆盖最关键的业务切片。"""
    request = record.get("request") or {}
    control_spec = record.get("control_spec") or {}
    return (
        control_spec.get("companion_type", "unknown"),
        control_spec.get("city_tier", "unknown"),
        request.get("travel_days", "unknown"),
        weather_bucket(record),
    )


def ordered_group(records: list[dict[str, Any]], tag: str, seed: int) -> list[dict[str, Any]]:
    """组内稳定随机排序。"""
    return sorted(
        records,
        key=lambda item: stable_float(f"{seed}:{tag}:{item.get('record_id', '')}"),
    )


def take_stratified(records: list[dict[str, Any]], target_size: int, tag: str, seed: int) -> list[dict[str, Any]]:
    """从 records 中按分层比例抽取 target_size 条。"""
    if target_size <= 0:
        return []
    if target_size >= len(records):
        return list(records)

    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[stratification_key(record)].append(record)

    selected: list[dict[str, Any]] = []
    quotas = []
    total = len(records)
    for key, rows in groups.items():
        ideal = len(rows) * target_size / total
        base = min(len(rows), math.floor(ideal))
        quotas.append(
            {
                "key": key,
                "rows": ordered_group(rows, tag, seed),
                "base": base,
                "remainder": ideal - base,
            }
        )

    for quota in quotas:
        selected.extend(quota["rows"][: quota["base"]])

    remaining = target_size - len(selected)
    quotas.sort(
        key=lambda item: (
            -item["remainder"],
            stable_float(f"{seed}:{tag}:quota:{item['key']}"),
        )
    )
    cursor = 0
    while remaining > 0 and quotas:
        quota = quotas[cursor % len(quotas)]
        already = quota["base"]
        if already < len(quota["rows"]):
            selected.append(quota["rows"][already])
            quota["base"] += 1
            remaining -= 1
        cursor += 1
        if cursor > len(quotas) * 4 and all(item["base"] >= len(item["rows"]) for item in quotas):
            break

    return selected[:target_size]


def split_records(
    records: list[dict[str, Any]],
    *,
    train_ratio: float,
    val_ratio: float,
    eval_ratio: float,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """按 train/val/eval 比例切分。"""
    total_ratio = train_ratio + val_ratio + eval_ratio
    if abs(total_ratio - 1.0) > 1e-6:
        raise ValueError(f"train/val/eval ratio must sum to 1, got {total_ratio}")

    total = len(records)
    eval_size = round(total * eval_ratio)
    val_size = round(total * val_ratio)

    eval_records = take_stratified(records, eval_size, "eval", seed)
    eval_ids = {item["record_id"] for item in eval_records}
    rest = [item for item in records if item["record_id"] not in eval_ids]

    val_records = take_stratified(rest, val_size, "val", seed)
    val_ids = {item["record_id"] for item in val_records}
    train_records = [item for item in rest if item["record_id"] not in val_ids]

    train_records = ordered_group(train_records, "train_output", seed)
    val_records = ordered_group(val_records, "val_output", seed)
    eval_records = ordered_group(eval_records, "eval_output", seed)
    return train_records, val_records, eval_records


def make_lf_row(record: dict[str, Any]) -> dict[str, Any]:
    """转换成 LLaMA-Factory alpaca 格式。"""
    return {
        "instruction": PLANNER_AGENT_PROMPT,
        "input": record["planner_query"],
        "output": record["output"],
    }


def write_lf(path: Path, records: list[dict[str, Any]]) -> None:
    """写 LLaMA-Factory JSON 数组。"""
    write_json(path, [make_lf_row(record) for record in records])


def update_dataset_info(train_path: Path, val_path: Path, eval_path: Path) -> None:
    """注册 clean train/val/eval。"""
    if DATASET_INFO_PATH.exists():
        data = json.loads(DATASET_INFO_PATH.read_text(encoding="utf-8"))
    else:
        data = {}

    data["trip_legacy_sft_clean_train"] = {"file_name": train_path.name}
    data["trip_legacy_sft_clean_val"] = {"file_name": val_path.name}
    data["trip_legacy_sft_clean_eval"] = {"file_name": eval_path.name}
    write_json(DATASET_INFO_PATH, data)


def summarize(records: list[dict[str, Any]]) -> dict[str, Counter]:
    """统计关键分布。"""
    counters = {
        "companion_type": Counter(),
        "city_tier": Counter(),
        "travel_days": Counter(),
        "weather_bucket": Counter(),
        "budget_level": Counter(),
        "diet": Counter(),
        "city": Counter(),
    }
    for record in records:
        request = record.get("request") or {}
        control_spec = record.get("control_spec") or {}
        counters["companion_type"][control_spec.get("companion_type", "unknown")] += 1
        counters["city_tier"][control_spec.get("city_tier", "unknown")] += 1
        counters["travel_days"][request.get("travel_days", "unknown")] += 1
        counters["weather_bucket"][weather_bucket(record)] += 1
        counters["budget_level"][control_spec.get("budget_level", "unknown")] += 1
        counters["diet"][control_spec.get("diet", "unknown")] += 1
        counters["city"][request.get("city", "unknown")] += 1
    return counters


def write_summary(path: Path, splits: dict[str, list[dict[str, Any]]]) -> None:
    """写切分摘要。"""
    lines = ["# legacy SFT Train / Val / Eval Split\n\n"]
    for name, records in splits.items():
        lines.append(f"## {name}\n\n")
        lines.append(f"- count: {len(records)}\n")
        counters = summarize(records)
        for counter_name, counter in counters.items():
            lines.append(f"- {counter_name}: {dict(counter.most_common(20))}\n")
        lines.append("\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="切分 legacy clean SFT 数据。")
    parser.add_argument("--input-records", type=Path, default=DEFAULT_INPUT_RECORDS)
    parser.add_argument("--records-train", type=Path, default=DEFAULT_RECORDS_TRAIN)
    parser.add_argument("--records-val", type=Path, default=DEFAULT_RECORDS_VAL)
    parser.add_argument("--records-eval", type=Path, default=DEFAULT_RECORDS_EVAL)
    parser.add_argument("--lf-train", type=Path, default=DEFAULT_LF_TRAIN)
    parser.add_argument("--lf-val", type=Path, default=DEFAULT_LF_VAL)
    parser.add_argument("--lf-eval", type=Path, default=DEFAULT_LF_EVAL)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--train-ratio", type=float, default=0.85)
    parser.add_argument("--val-ratio", type=float, default=0.05)
    parser.add_argument("--eval-ratio", type=float, default=0.10)
    parser.add_argument("--seed", type=int, default=20260501)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.input_records)
    train_records, val_records, eval_records = split_records(
        records,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        eval_ratio=args.eval_ratio,
        seed=args.seed,
    )

    write_jsonl(args.records_train, train_records)
    write_jsonl(args.records_val, val_records)
    write_jsonl(args.records_eval, eval_records)
    write_lf(args.lf_train, train_records)
    write_lf(args.lf_val, val_records)
    write_lf(args.lf_eval, eval_records)
    update_dataset_info(args.lf_train, args.lf_val, args.lf_eval)
    write_summary(
        args.summary,
        {
            "train": train_records,
            "val": val_records,
            "eval": eval_records,
        },
    )

    print(f"input_records={len(records)}")
    print(f"train={len(train_records)} val={len(val_records)} eval={len(eval_records)}")
    print(f"records_train={args.records_train}")
    print(f"records_val={args.records_val}")
    print(f"records_eval={args.records_eval}")
    print(f"lf_train={args.lf_train}")
    print(f"lf_val={args.lf_val}")
    print(f"lf_eval={args.lf_eval}")
    print(f"summary={args.summary}")


if __name__ == "__main__":
    main()
