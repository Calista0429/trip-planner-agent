"""构造 legacy DPO prompt 池。

示例:

  .venv-training-py311/bin/python3 training/scripts/eval/dpo_build_prompts.py \
    --records training/data/legacy/sft/records_train.jsonl \
    --limit 20 \
    --shuffle
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import random
import re
from pathlib import Path

from dpo_utils import DEFAULT_DPO_PROMPTS, prompt_row_from_record
from eval_utils import estimate_party_size, read_jsonl, write_jsonl
from app.agents.prompts import PLANNER_AGENT_PROMPT


PER_PERSON_DAY_BUDGETS = {
    "limited": [200, 300],
    "medium": [400, 500],
    "upper": [800, 1000],
    "luxury": [1200, 1500, 2000],
}

BUDGET_PATTERNS = [
    r"人均每天\s*\d+(?:\.\d+)?\s*元左右?",
    r"每人每天\s*\d+(?:\.\d+)?\s*元左右?",
    r"一人一天\s*\d+(?:\.\d+)?\s*元左右?",
    r"人均预算大概\s*\d+(?:\.\d+)?\s*元",
    r"人均预算约\s*\d+(?:\.\d+)?\s*元",
    r"总预算控制在\s*\d+(?:\.\d+)?\s*元左右?",
    r"每日预算大概\s*\d+(?:\.\d+)?\s*元",
]


def load_existing_ids(path: Path) -> set[str]:
    """读取已存在 prompt_id。"""
    return {row.get("prompt_id", "") for row in read_jsonl(path)}


def stable_rng(record: dict, seed: int) -> random.Random:
    """按 record_id 构造稳定随机数，保证每次重建 prompt 预算一致。"""
    key = f"{seed}:{record.get('record_id') or (record.get('request') or {}).get('request_id')}"
    digest = hashlib.md5(key.encode("utf-8")).hexdigest()
    return random.Random(int(digest[:12], 16))


def choose_budget_phrase(record: dict, seed: int) -> str:
    """把 control_spec.budget_level 转成真实口吻的百元整数预算表达。"""
    request = record.get("request") or {}
    control = record.get("control_spec") or {}
    budget_level = str(control.get("budget_level") or "medium")
    rng = stable_rng(record, seed)
    per_person_day = rng.choice(PER_PERSON_DAY_BUDGETS.get(budget_level, PER_PERSON_DAY_BUDGETS["medium"]))
    days = max(1, int(request.get("travel_days") or 1))
    people = max(1, estimate_party_size(record))
    total = per_person_day * days * people

    # DPO legacy 先只训练总预算，避免“人均每天/人均总预算/总预算”
    # 三种语义同时出现，导致模型和评估脚本学到不一致的预算口径。
    return f"总预算控制在{total}元左右"


def replace_budget_text(text: str, phrase: str) -> str:
    """替换一句话中的预算片段；没有预算片段时追加预算表达。"""
    result = text
    replaced = False
    for pattern in BUDGET_PATTERNS:
        result, count = re.subn(pattern, phrase, result)
        replaced = replaced or count > 0
    if replaced:
        return result
    if not result:
        return phrase
    separator = "" if result.endswith(("。", "！", "？")) else "，"
    return f"{result.rstrip('。')}{separator}{phrase}。"


def normalize_record_budget_text(record: dict, seed: int) -> dict:
    """把旧 record 里的非真实预算表达规范化，并同步 planner_query。"""
    normalized = copy.deepcopy(record)
    request = normalized.get("request") or {}
    old_text = str(request.get("free_text_input") or "")
    if not old_text:
        return normalized

    phrase = choose_budget_phrase(normalized, seed)
    new_text = replace_budget_text(old_text, phrase)
    request["free_text_input"] = new_text
    normalized["request"] = request

    planner_query = str(normalized.get("planner_query") or "")
    if old_text and old_text in planner_query:
        normalized["planner_query"] = planner_query.replace(old_text, new_text)
    elif planner_query:
        normalized["planner_query"] = replace_budget_text(planner_query, phrase)

    metadata = normalized.get("metadata") or {}
    metadata["budget_text_normalized"] = True
    metadata["budget_text_before"] = old_text
    metadata["budget_text_after"] = new_text
    normalized["metadata"] = metadata
    return normalized


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="构造 legacy DPO prompt 池。")
    parser.add_argument("--records", type=Path, default=Path("training/data/legacy/sft/records_train.jsonl"))
    parser.add_argument("--output", type=Path, default=DEFAULT_DPO_PROMPTS)
    parser.add_argument("--source", default=None, help="写入 prompt.source，默认使用 records 文件名")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20260502)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--resume", action="store_true", help="追加缺失样本，不覆盖已有 prompts.jsonl")
    parser.add_argument(
        "--normalize-budget-text",
        action="store_true",
        help="把旧记录里的精确随机预算改成按百元整数的总预算表达。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.records)
    if args.shuffle:
        rng = random.Random(args.seed)
        records = list(records)
        rng.shuffle(records)
    if args.limit > 0:
        records = records[: args.limit]
    if args.normalize_budget_text:
        records = [normalize_record_budget_text(record, args.seed) for record in records]

    source = args.source or args.records.stem
    rows = [
        prompt_row_from_record(record, source=source, system_prompt=PLANNER_AGENT_PROMPT)
        for record in records
    ]

    if args.resume and args.output.exists():
        done_ids = load_existing_ids(args.output)
        old_rows = read_jsonl(args.output)
        new_rows = [row for row in rows if row["prompt_id"] not in done_ids]
        rows = old_rows + new_rows
        print(f"resume: existing={len(old_rows)}, add={len(new_rows)}")

    write_jsonl(args.output, rows)
    print(f"DPO prompts: {args.output}")
    print(f"records={len(records)}, written={len(rows)}")


if __name__ == "__main__":
    main()
