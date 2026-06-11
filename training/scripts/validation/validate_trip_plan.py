"""校验 SFT/DPO 中的 TripPlan 是否符合后端 schema。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from shared.common import extract_json  # noqa: E402

from app.models.schemas import TripPlan  # noqa: E402


def read_rows(path: Path) -> list[dict]:
    """读取 JSON 数组或 JSONL。"""
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError(f"{path} 不是 JSON 数组或 JSONL")
        return data
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def validate_text(text: str) -> None:
    """校验 JSON 文本。"""
    TripPlan(**extract_json(text))


def validate_sft(path: Path) -> tuple[int, int]:
    """校验 SFT output。"""
    total = failed = 0
    for row_no, row in enumerate(read_rows(path), start=1):
        total += 1
        try:
            validate_text(row["output"])
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"SFT 第 {row_no} 条失败: {exc}")
    return total, failed


def validate_dpo(path: Path, validate_rejected: bool) -> tuple[int, int]:
    """校验 DPO chosen 和可选 rejected。"""
    total = failed = 0
    for row_no, row in enumerate(read_rows(path), start=1):
        total += 1
        try:
            validate_text(row["chosen"]["value"])
            if validate_rejected:
                validate_text(row["rejected"]["value"])
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"DPO 第 {row_no} 条失败: {exc}")
    return total, failed


def validate_eval_gt(path: Path) -> tuple[int, int]:
    """校验独立评估 GT。"""
    total = failed = 0
    for row_no, row in enumerate(read_rows(path), start=1):
        total += 1
        try:
            TripPlan(**row["reference_trip_plan"])
            validate_text(row["reference_output"])
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"Eval GT 第 {row_no} 条失败: {exc}")
    return total, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sft")
    parser.add_argument("--dpo")
    parser.add_argument("--eval-gt")
    parser.add_argument("--validate-rejected", action="store_true")
    args = parser.parse_args()

    if not args.sft and not args.dpo and not args.eval_gt:
        parser.error("必须提供 --sft、--dpo 或 --eval-gt")

    total = failed = 0
    if args.sft:
        count, errors = validate_sft(Path(args.sft))
        total += count
        failed += errors
    if args.dpo:
        count, errors = validate_dpo(Path(args.dpo), args.validate_rejected)
        total += count
        failed += errors
    if args.eval_gt:
        count, errors = validate_eval_gt(Path(args.eval_gt))
        total += count
        failed += errors

    print(f"校验完成: total={total}, failed={failed}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
