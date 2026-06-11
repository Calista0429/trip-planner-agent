"""用强模型对两个模型的输出做 pairwise judge。"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_utils import (
    DEFAULT_EVAL_RECORDS,
    DEFAULT_EVAL_OUTPUT_DIR,
    append_jsonl,
    load_records_by_id,
    parse_trip_plan_output,
    read_jsonl,
    summarize_request,
    write_json,
)
from shared.llm_client import DataGenLLM


PAIRWISE_SYSTEM_PROMPT = """你是严谨的旅行规划偏好评估专家。你会看到同一个 TripRequest / PlannerContext 下的两个 TripPlan。

请判断哪个更适合作为最终旅行计划。优先考虑约束满足、工具 grounding、天气事实、用户偏好、可执行性和预算合理性。
餐饮要具体：如果 meal.name 是“早餐推荐”“午餐推荐”“晚餐推荐”“本地早餐”“当地早餐”“特色餐厅”等占位词，或者 lunch/dinner 没有使用 food_pois 的具体餐厅，应明显扣分。酒店早餐/民宿早餐/客栈早餐作为 breakfast 可接受且可重复；但同一天 lunch 和 dinner 不应是同一家餐厅，整趟行程也不应多天反复使用同一家真实餐厅、同一品牌或同一种单品。
不要因为文字更长就判胜。只输出 JSON。
"""


def stable_bool(record_id: str) -> bool:
    """稳定决定是否交换 A/B。"""
    digest = hashlib.sha256(record_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 2 == 0


def load_generations(path: Path) -> dict[str, dict[str, Any]]:
    """按 record_id 读取生成结果。"""
    return {row["record_id"]: row for row in read_jsonl(path)}


def load_done_ids(path: Path) -> set[str]:
    """读取已完成 ID。"""
    return {row.get("record_id", "") for row in read_jsonl(path)}


def valid_generation(row: dict[str, Any]) -> tuple[bool, str]:
    """生成是否可交给 judge。"""
    if not row or not row.get("ok"):
        return False, "generation_call_failed"
    _, _, error_stage, error = parse_trip_plan_output(row.get("output", ""))
    if error_stage:
        return False, error or error_stage
    return True, ""


def build_prompt(record: dict[str, Any], a_label: str, a_output: str, b_label: str, b_output: str) -> str:
    """构造 pairwise prompt。"""
    context = {
        "request": record.get("request"),
        "control_spec": record.get("control_spec"),
        "planner_context": record.get("compact_planner_context"),
    }
    return f"""请比较 A 和 B 两个旅行计划，输出 JSON:
{{
  "winner": "A" | "B" | "tie",
  "confidence": 1-5,
  "reasons": ["理由1", "理由2"],
  "summary": "简短结论"
}}

TripRequest 和 PlannerContext:
{json.dumps(context, ensure_ascii=False)}

A ({a_label}):
{a_output}

B ({b_label}):
{b_output}
"""


def judge_one(record: dict[str, Any], left: dict[str, Any], right: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """对单条样本做 pairwise judge。"""
    record_id = record["record_id"]
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "record_id": record_id,
        "left_label": args.left_label,
        "right_label": args.right_label,
        "request_summary": summarize_request(record),
        "control_spec": record.get("control_spec", {}),
    }
    left_valid, left_reason = valid_generation(left)
    right_valid, right_reason = valid_generation(right)
    if not left_valid and not right_valid:
        row.update({"winner": "tie", "judge_mode": "auto_invalid", "reasons": [left_reason, right_reason]})
        return row
    if left_valid and not right_valid:
        row.update({"winner": "left", "judge_mode": "auto_invalid", "reasons": [right_reason]})
        return row
    if right_valid and not left_valid:
        row.update({"winner": "right", "judge_mode": "auto_invalid", "reasons": [left_reason]})
        return row

    swap = stable_bool(record_id)
    if swap:
        a_label, a_output = args.right_label, right.get("output", "")
        b_label, b_output = args.left_label, left.get("output", "")
    else:
        a_label, a_output = args.left_label, left.get("output", "")
        b_label, b_output = args.right_label, right.get("output", "")

    llm = DataGenLLM()
    data = llm.complete_json(
        PAIRWISE_SYSTEM_PROMPT,
        build_prompt(record, a_label, a_output, b_label, b_output),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    raw_winner = str((data or {}).get("winner", "tie")).strip().upper()
    if raw_winner == "A":
        winner = "right" if swap else "left"
    elif raw_winner == "B":
        winner = "left" if swap else "right"
    else:
        winner = "tie"

    row.update(
        {
            "winner": winner,
            "judge_mode": "llm",
            "judge_model": llm.model,
            "confidence": data.get("confidence"),
            "reasons": data.get("reasons", []),
            "summary": data.get("summary", ""),
            "swapped": swap,
        }
    )
    return row


def summarize(rows: list[dict[str, Any]], left_label: str, right_label: str) -> dict[str, Any]:
    """汇总 pairwise 结果。"""
    counts = {"left": 0, "right": 0, "tie": 0}
    for row in rows:
        if row.get("winner") in counts:
            counts[row["winner"]] += 1
    total = len(rows) or 1
    return {
        "total": len(rows),
        "left_label": left_label,
        "right_label": right_label,
        "left_wins": counts["left"],
        "right_wins": counts["right"],
        "ties": counts["tie"],
        "left_win_rate": round(counts["left"] / total, 4),
        "right_win_rate": round(counts["right"] / total, 4),
        "tie_rate": round(counts["tie"] / total, 4),
    }


def write_summary(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    """写 Markdown 摘要。"""
    lines = ["# Pairwise Judge Summary\n\n", "```json\n", json.dumps(summary, ensure_ascii=False, indent=2), "\n```\n"]
    lines.append("\n## Examples\n\n")
    for row in rows[:30]:
        lines.append(f"### {row['record_id']} winner={row.get('winner')}\n")
        lines.append(f"- request: {row.get('request_summary')}\n")
        lines.append(f"- reasons: {row.get('reasons')}\n")
        lines.append(f"- summary: {row.get('summary', '')}\n\n")
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pairwise judge 两个模型输出。")
    parser.add_argument("--records", type=Path, default=DEFAULT_EVAL_RECORDS)
    parser.add_argument("--left-generations", type=Path, required=True)
    parser.add_argument("--right-generations", type=Path, required=True)
    parser.add_argument("--left-label", required=True)
    parser.add_argument("--right-label", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT_DIR / "comparison")
    parser.add_argument("--output-file", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1600)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records_by_id = load_records_by_id(args.records)
    left_rows = load_generations(args.left_generations)
    right_rows = load_generations(args.right_generations)
    ids = [record_id for record_id in records_by_id if record_id in left_rows and record_id in right_rows]
    if args.limit > 0:
        ids = ids[: args.limit]

    output_file = args.output_file or (args.output_dir / f"pairwise_{args.left_label}_vs_{args.right_label}.jsonl")
    summary_json = args.output_dir / f"pairwise_{args.left_label}_vs_{args.right_label}_summary.json"
    summary_md = args.output_dir / f"pairwise_{args.left_label}_vs_{args.right_label}_summary.md"
    done_ids = load_done_ids(output_file) if args.resume else set()
    todo = [record_id for record_id in ids if record_id not in done_ids]

    print(f"pairwise judge: {args.left_label} vs {args.right_label}, total={len(ids)}, todo={len(todo)}")
    if args.workers <= 1:
        for index, record_id in enumerate(todo, start=1):
            row = judge_one(records_by_id[record_id], left_rows[record_id], right_rows[record_id], args)
            append_jsonl(output_file, row)
            print(f"progress {index}/{len(todo)} last={record_id} winner={row.get('winner')}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(judge_one, records_by_id[record_id], left_rows[record_id], right_rows[record_id], args): record_id
                for record_id in todo
            }
            for index, future in enumerate(as_completed(futures), start=1):
                row = future.result()
                append_jsonl(output_file, row)
                print(f"progress {index}/{len(todo)} last={row['record_id']} winner={row.get('winner')}", flush=True)

    rows = read_jsonl(output_file)
    summary = summarize(rows, args.left_label, args.right_label)
    write_json(summary_json, summary)
    write_summary(summary_md, rows, summary)
    print(f"pairwise output: {output_file}")
    print(f"summary: {summary_md}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
