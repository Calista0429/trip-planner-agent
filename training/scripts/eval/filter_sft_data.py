"""给 legacy SFT 数据补 control_spec、清洗脏样本并导出训练文件。

示例:

  cd helloagents-trip-planner
  .venv-training-py311/bin/python3 training/scripts/eval/filter_sft_data.py

当前默认清洗规则:

- 保留每天 1-3 个景点的样本；如果任意一天景点数超过 3 个，整条 record 进入 dirty 文件。
- 最后一天 hotel=null 可以保留；如果中间天 hotel=null，整条 record 进入 dirty 文件。
- 如果 hotel.name 是“无/无住宿/返程”等占位词，整条 record 进入 dirty 文件。

说明:

1 个景点的 day 在慢游、到达日、亲子/老人友好行程里可能是合理的，所以不默认删除。
原始 records.jsonl 不会被覆盖；脚本会生成 records_with_control_spec.jsonl 和 records_clean.jsonl。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(BACKEND_DIR))

from shared.common import DATA_DIR, LLAMAFACTORY_DIR, read_jsonl, split_train_val, write_json  # noqa: E402
from generate_sft_data import generate_controlled_request  # noqa: E402
from app.planner.output import is_invalid_hotel_name  # noqa: E402
from app.agents.prompts import PLANNER_AGENT_PROMPT  # noqa: E402


LEGACY_SFT_DIR = DATA_DIR / "legacy" / "sft"
DEFAULT_INPUT_RECORDS = LEGACY_SFT_DIR / "records.jsonl"
DEFAULT_HYDRATED_RECORDS = LEGACY_SFT_DIR / "records_with_control_spec.jsonl"
DEFAULT_HYDRATED_REQUESTS = LEGACY_SFT_DIR / "requests_with_control_spec.jsonl"
DEFAULT_CLEAN_RECORDS = LEGACY_SFT_DIR / "records_clean.jsonl"
DEFAULT_DIRTY_RECORDS = LEGACY_SFT_DIR / "records_dirty.jsonl"
DEFAULT_DIRTY_SUMMARY = LEGACY_SFT_DIR / "records_dirty_summary.md"
DEFAULT_TRAIN_OUTPUT = LLAMAFACTORY_DIR / "trip_legacy_sft_clean_train.json"
DEFAULT_VAL_OUTPUT = LLAMAFACTORY_DIR / "trip_legacy_sft_clean_val.json"
DATASET_INFO_PATH = LLAMAFACTORY_DIR / "dataset_info.json"

REQUEST_COMPARE_KEYS = [
    "city",
    "start_date",
    "end_date",
    "travel_days",
    "transportation",
    "accommodation",
    "preferences",
    "free_text_input",
]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """写入 JSONL。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_lf_row(record: dict[str, Any]) -> dict[str, Any]:
    """转换成 LLaMA-Factory alpaca 格式。"""
    return {
        "instruction": PLANNER_AGENT_PROMPT,
        "input": record["planner_query"],
        "output": record["output"],
    }


def parse_record_index(record_id: str) -> int | None:
    """从 legacy_request_000123 中解析编号。"""
    match = re.search(r"(\d+)$", record_id or "")
    if not match:
        return None
    return int(match.group(1))


def rebuild_control_spec(record: dict[str, Any], seed: int, date_mode: str) -> tuple[dict[str, Any], str]:
    """用 deterministic controlled generator 为旧 record 重建 control_spec。

    返回 (control_spec, status)。只有生成出的请求字段和 record.request 完全一致时才认为 matched。
    """
    existing = record.get("control_spec")
    if existing:
        return existing, "existing"

    index = parse_record_index(record.get("record_id", ""))
    if index is None:
        return {}, "missing_record_index"

    args = argparse.Namespace(seed=seed, date_mode=date_mode)
    generated = generate_controlled_request(index, args)
    request = record.get("request") or {}
    mismatched = [
        key
        for key in REQUEST_COMPARE_KEYS
        if generated.get(key) != request.get(key)
    ]
    if mismatched:
        return {}, "mismatch:" + ",".join(mismatched)
    return generated.get("control_spec", {}), "rebuilt"


def hydrate_control_spec(records: list[dict[str, Any]], seed: int, date_mode: str) -> tuple[list[dict[str, Any]], Counter]:
    """为 records 补 control_spec，不修改输入对象。"""
    status_counter: Counter = Counter()
    hydrated_records: list[dict[str, Any]] = []
    for record in records:
        hydrated = dict(record)
        metadata = dict(hydrated.get("metadata") or {})
        control_spec, status = rebuild_control_spec(record, seed=seed, date_mode=date_mode)
        status_counter[status] += 1
        if control_spec:
            hydrated["control_spec"] = control_spec
        metadata["control_spec_status"] = status
        hydrated["metadata"] = metadata
        hydrated_records.append(hydrated)
    return hydrated_records, status_counter


def dirty_reasons(record: dict[str, Any], max_attractions_per_day: int) -> list[dict[str, Any]]:
    """返回一条 record 的脏数据原因。"""
    reasons = []
    days = (record.get("trip_plan") or {}).get("days") or []
    for index, day in enumerate(days):
        attractions = day.get("attractions") or []
        if len(attractions) > max_attractions_per_day:
            reasons.append(
                {
                    "type": "too_many_attractions",
                    "max_attractions_per_day": max_attractions_per_day,
                    "date": day.get("date"),
                    "day_index": day.get("day_index"),
                    "attraction_count": len(attractions),
                    "attractions": [item.get("name") for item in attractions if isinstance(item, dict)],
                }
            )
        hotel = day.get("hotel")
        is_final_day = index == len(days) - 1
        if hotel is None and not is_final_day:
            reasons.append(
                {
                    "type": "missing_mid_trip_hotel",
                    "date": day.get("date"),
                    "day_index": day.get("day_index"),
                    "accommodation": day.get("accommodation"),
                }
            )
        elif isinstance(hotel, dict) and is_invalid_hotel_name(str(hotel.get("name", ""))):
            reasons.append(
                {
                    "type": "invalid_hotel_name",
                    "date": day.get("date"),
                    "day_index": day.get("day_index"),
                    "hotel_name": hotel.get("name"),
                }
            )
    return reasons


def update_dataset_info(train_output: Path, val_output: Path) -> None:
    """注册 clean 数据集。"""
    if DATASET_INFO_PATH.exists():
        data = json.loads(DATASET_INFO_PATH.read_text(encoding="utf-8"))
    else:
        data = {}

    data["trip_legacy_sft_clean_train"] = {"file_name": train_output.name}
    data["trip_legacy_sft_clean_val"] = {"file_name": val_output.name}
    write_json(DATASET_INFO_PATH, data)


def write_dirty_summary(
    path: Path,
    *,
    records: list[dict[str, Any]],
    clean_records: list[dict[str, Any]],
    dirty_records: list[dict[str, Any]],
    control_status: Counter,
    dirty_reason_counts: Counter,
    dirty_attraction_counts: Counter,
) -> None:
    """写一份便于人工审查的清洗摘要。"""
    city_counter: Counter = Counter((record.get("request") or {}).get("city", "UNKNOWN") for record in dirty_records)
    reason_examples: dict[str, list[dict[str, Any]]] = {}
    for record in dirty_records:
        for reason in record.get("dirty_reasons") or []:
            reason_type = reason.get("type", "unknown")
            reason_examples.setdefault(reason_type, [])
            if len(reason_examples[reason_type]) >= 8:
                continue
            reason_examples[reason_type].append(
                {
                    "record_id": record.get("record_id"),
                    "city": (record.get("request") or {}).get("city"),
                    "date": reason.get("date"),
                    "day_index": reason.get("day_index"),
                    "reason": reason,
                }
            )

    lines = [
        "# legacy SFT 清洗摘要\n\n",
        f"- 输入样本: {len(records)}\n",
        f"- 干净样本: {len(clean_records)}\n",
        f"- 脏样本: {len(dirty_records)}\n",
        f"- control_spec 状态: {dict(control_status)}\n",
        f"- 脏数据原因统计: {dict(dirty_reason_counts)}\n",
        f"- 超限景点数量统计: {dict(dirty_attraction_counts)}\n",
        "\n## 脏样本城市 Top 20\n",
    ]
    for city, count in city_counter.most_common(20):
        lines.append(f"- {city}: {count}\n")

    lines.append("\n## 示例\n")
    for reason_type, examples in reason_examples.items():
        lines.append(f"\n### {reason_type}\n")
        for example in examples:
            lines.append(
                f"- {example['record_id']} | {example['city']} | "
                f"date={example['date']} | day_index={example['day_index']} | "
                f"{json.dumps(example['reason'], ensure_ascii=False)}\n"
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="清洗 legacy SFT 数据。")
    parser.add_argument("--input-records", type=Path, default=DEFAULT_INPUT_RECORDS)
    parser.add_argument("--hydrated-records", type=Path, default=DEFAULT_HYDRATED_RECORDS)
    parser.add_argument("--hydrated-requests", type=Path, default=DEFAULT_HYDRATED_REQUESTS)
    parser.add_argument("--clean-records", type=Path, default=DEFAULT_CLEAN_RECORDS)
    parser.add_argument("--dirty-records", type=Path, default=DEFAULT_DIRTY_RECORDS)
    parser.add_argument("--dirty-summary", type=Path, default=DEFAULT_DIRTY_SUMMARY)
    parser.add_argument("--train-output", type=Path, default=DEFAULT_TRAIN_OUTPUT)
    parser.add_argument("--val-output", type=Path, default=DEFAULT_VAL_OUTPUT)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=20260429)
    parser.add_argument("--date-mode", choices=["future", "mixed", "past"], default="mixed")
    parser.add_argument("--max-attractions-per-day", type=int, default=3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.input_records)
    records, control_status = hydrate_control_spec(records, seed=args.seed, date_mode=args.date_mode)

    clean_records: list[dict[str, Any]] = []
    dirty_records: list[dict[str, Any]] = []
    dirty_reason_counts: Counter = Counter()
    dirty_attraction_counts: Counter = Counter()

    for record in records:
        reasons = dirty_reasons(record, args.max_attractions_per_day)
        if reasons:
            dirty = dict(record)
            dirty["dirty_reasons"] = reasons
            dirty_records.append(dirty)
            for reason in reasons:
                dirty_reason_counts[reason["type"]] += 1
                if reason["type"] == "too_many_attractions":
                    dirty_attraction_counts[reason["attraction_count"]] += 1
            continue
        clean_records.append(record)

    lf_rows = [make_lf_row(record) for record in clean_records]
    train_rows, val_rows = split_train_val(lf_rows, val_ratio=args.val_ratio)

    hydrated_requests = [
        (record.get("request") or {}) | {"control_spec": record.get("control_spec", {})}
        for record in records
    ]

    write_jsonl(args.hydrated_records, records)
    write_jsonl(args.hydrated_requests, hydrated_requests)
    write_jsonl(args.clean_records, clean_records)
    write_jsonl(args.dirty_records, dirty_records)
    write_json(args.train_output, train_rows)
    write_json(args.val_output, val_rows)
    update_dataset_info(args.train_output, args.val_output)
    write_dirty_summary(
        args.dirty_summary,
        records=records,
        clean_records=clean_records,
        dirty_records=dirty_records,
        control_status=control_status,
        dirty_reason_counts=dirty_reason_counts,
        dirty_attraction_counts=dirty_attraction_counts,
    )

    print(f"input_records={len(records)}")
    print(f"control_spec_status={dict(control_status)}")
    print(f"clean_records={len(clean_records)}")
    print(f"dirty_records={len(dirty_records)}")
    print(f"dirty_reason_counts={dict(sorted(dirty_reason_counts.items()))}")
    print(f"dirty_attraction_counts={dict(sorted(dirty_attraction_counts.items()))}")
    print(f"train={len(train_rows)} val={len(val_rows)}")
    print(f"hydrated_records_path={args.hydrated_records}")
    print(f"hydrated_requests_path={args.hydrated_requests}")
    print(f"clean_records_path={args.clean_records}")
    print(f"dirty_records_path={args.dirty_records}")
    print(f"dirty_summary_path={args.dirty_summary}")
    print(f"train_output={args.train_output}")
    print(f"val_output={args.val_output}")


if __name__ == "__main__":
    main()
