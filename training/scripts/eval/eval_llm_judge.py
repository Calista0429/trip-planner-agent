"""用强模型对单模型输出做 LLM-as-judge 打分。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_utils import (
    DEFAULT_EVAL_RECORDS,
    DEFAULT_EVAL_OUTPUT_DIR,
    append_jsonl,
    average,
    load_records_by_id,
    model_run_dir,
    parse_trip_plan_output,
    read_jsonl,
    summarize_request,
    write_json,
)
from shared.llm_client import DataGenLLM


SCORE_KEYS = [
    "preference_satisfaction",
    "practicality",
    "grounding_faithfulness",
    "budget_reasonableness",
    "coherence",
    "overall_quality",
]

JUDGE_SYSTEM_PROMPT = """你是严谨的旅行规划评估专家。你需要根据 TripRequest、PlannerContext 和模型生成的 TripPlan 进行评分。

请只输出 JSON，不要输出 Markdown。
评分范围为 1-5 分，5 分最好。若 TripPlan 明显违反约束，相关维度应给低分。
"""


def latest_rows_by_id(path: Path) -> dict[str, dict[str, Any]]:
    """按 record_id 取最新一条记录，支持失败队列追加重跑。"""
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id", "")
        if record_id:
            rows[record_id] = row
    return rows


def load_done_ids(path: Path, retry_failed: bool = False) -> set[str]:
    """读取已完成样本 ID；可选择重跑 judge_failed 样本。"""
    latest_rows = latest_rows_by_id(path)
    if not retry_failed:
        return set(latest_rows)
    return {
        record_id
        for record_id, row in latest_rows.items()
        if row.get("skip_reason") != "judge_failed"
    }


def compact_judge_context(record: dict[str, Any]) -> dict[str, Any]:
    """给 judge 的上下文，保留足够判断的信息。"""
    context = record.get("compact_planner_context") or {}
    return {
        "request": record.get("request"),
        "control_spec": record.get("control_spec"),
        "planner_context": context,
    }


def build_judge_prompt(record: dict[str, Any], output: str) -> str:
    """构造单模型 judge prompt。"""
    return f"""请评估下面模型生成的旅行计划。

评分维度:
- preference_satisfaction: 是否满足用户偏好、同行类型、节奏、饮食和规避项
- practicality: 景点密度、交通、酒店位置、每日安排是否现实可执行
- grounding_faithfulness: 是否主要基于 PlannerContext 的工具候选和天气事实；景点、酒店、午餐、晚餐应尽量命中候选
- budget_reasonableness: 预算分项和总价是否自洽，是否符合住宿/餐饮/交通偏好，餐饮价格是否像全体同行这一餐费用
- coherence: 每日安排是否顺畅，描述是否具体，是否有重复或矛盾
- overall_quality: 综合旅行计划质量

特别注意:
- meal.name 如果是“早餐推荐”“午餐推荐”“晚餐推荐”“本地早餐”“当地早餐”“特色餐厅”等占位词，说明没有真实餐饮内容，应明显扣 grounding、coherence 和 overall_quality。
- breakfast 可以使用 food_pois 中的早餐/小吃候选；在赶早、到达日、亲子老人省力或住宿含早餐等场景下，“酒店早餐/民宿早餐/客栈早餐”也视为可接受的早餐 grounding，住宿早餐可重复，不按餐饮多样性扣分。
- lunch/dinner 没有使用 food_pois 中的具体餐厅，或写成“无”“酒店晚餐”“酒店午餐”“民宿晚餐”等住宿类/空值餐饮，应作为主要问题写入 major_issues。
- 旅游餐饮默认应有多样性：同一天 lunch 和 dinner 不应是同一家餐厅；整趟行程不应多天反复使用同一家真实餐厅、同一品牌或同一种单品。非住宿早餐如果连续多天重复，也应扣 coherence / overall_quality。

请输出 JSON:
{{
  "scores": {{
    "preference_satisfaction": 1-5,
    "practicality": 1-5,
    "grounding_faithfulness": 1-5,
    "budget_reasonableness": 1-5,
    "coherence": 1-5,
    "overall_quality": 1-5
  }},
  "major_issues": ["问题1", "问题2"],
  "rationale": "简短评价"
}}

TripRequest 和 PlannerContext:
{json.dumps(compact_judge_context(record), ensure_ascii=False)}

待评估 TripPlan:
{output}
"""


def normalize_scores(data: dict[str, Any]) -> dict[str, float]:
    """规范化分数。"""
    raw = data.get("scores") or {}
    scores = {}
    for key in SCORE_KEYS:
        try:
            value = float(raw.get(key, 0))
        except Exception:  # noqa: BLE001
            value = 0.0
        scores[key] = max(0.0, min(5.0, value))
    return scores


def failed_judge_row(
    record_id: str,
    generation: dict[str, Any],
    args: argparse.Namespace,
    error: Exception | str,
    record: dict[str, Any] | None = None,
    skip_reason: str = "judge_failed",
) -> dict[str, Any]:
    """构造单条 judge 失败记录，避免一个坏响应中断整批评估。"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "record_id": record_id,
        "model_name": args.model_name,
        "request_summary": summarize_request(record) if record else "",
        "control_spec": record.get("control_spec", {}) if record else {},
        "judge_model": None,
        "ok": False,
        "skipped": True,
        "skip_reason": skip_reason,
        "scores": {key: 0 for key in SCORE_KEYS},
        "major_issues": [str(error)],
        "rationale": "LLM judge 未返回可解析 JSON 或调用失败，本条记为 judge_failed，不中断整批评估。",
        "generation_ok": generation.get("ok"),
    }


def judge_one(record: dict[str, Any], generation: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """评分单条输出。"""
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "record_id": record["record_id"],
        "model_name": args.model_name,
        "request_summary": summarize_request(record),
        "control_spec": record.get("control_spec", {}),
        "judge_model": None,
    }
    if not generation.get("ok"):
        row.update(
            {
                "ok": False,
                "skipped": True,
                "skip_reason": "generation_call_failed",
                "scores": {key: 0 for key in SCORE_KEYS},
                "major_issues": [generation.get("error", "generation failed")],
                "rationale": "模型调用失败，直接记为无效输出。",
            }
        )
        return row

    trip_plan, _, error_stage, error = parse_trip_plan_output(generation.get("output", ""))
    if error_stage:
        row.update(
            {
                "ok": False,
                "skipped": True,
                "skip_reason": error_stage,
                "scores": {key: 0 for key in SCORE_KEYS},
                "major_issues": [error or error_stage],
                "rationale": "输出未通过 JSON/schema 基础解析，直接记为无效输出。",
            }
        )
        return row

    llm = DataGenLLM()
    row["judge_model"] = llm.model
    data = None
    last_error: Exception | str = "unknown judge error"
    for attempt in range(1, args.judge_retries + 1):
        try:
            data = llm.complete_json(
                JUDGE_SYSTEM_PROMPT,
                build_judge_prompt(record, generation.get("output", "")),
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
            if not isinstance(data, dict):
                raise ValueError("judge output is not a JSON object")
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= args.judge_retries:
                row.update(
                    {
                        "ok": False,
                        "skipped": True,
                        "skip_reason": "judge_failed",
                        "scores": {key: 0 for key in SCORE_KEYS},
                        "major_issues": [str(last_error)],
                        "rationale": "LLM judge 多次未返回可解析 JSON 或调用失败，本条记为 judge_failed。",
                    }
                )
                return row

    row.update(
        {
            "ok": True,
            "skipped": False,
            "scores": normalize_scores(data),
            "major_issues": data.get("major_issues", []),
            "rationale": data.get("rationale", ""),
        }
    )
    return row


def safe_judge_one(records_by_id: dict[str, dict[str, Any]], generation: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """带兜底的单条 judge，保证并发任务不会因为异常整体退出。"""
    record_id = generation.get("record_id", "")
    record = records_by_id.get(record_id)
    if not record:
        return failed_judge_row(
            record_id=record_id,
            generation=generation,
            args=args,
            error=f"record not found: {record_id}",
            record=None,
            skip_reason="record_not_found",
        )
    try:
        return judge_one(record, generation, args)
    except Exception as exc:  # noqa: BLE001
        return failed_judge_row(record_id, generation, args, exc, record=record)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总 judge 分数。"""
    valid = [row for row in rows if row.get("ok")]
    skipped = [row for row in rows if not row.get("ok")]
    scores = {
        key: average([row.get("scores", {}).get(key, 0) for row in valid])
        for key in SCORE_KEYS
    }
    return {
        "total": len(rows),
        "judged": len(valid),
        "skipped": len(skipped),
        "judge_coverage": round(len(valid) / len(rows), 4) if rows else 0.0,
        "skip_reason_counts": dict(Counter(row.get("skip_reason", "unknown") for row in skipped)),
        "scores_avg": scores,
    }


def write_summary(path: Path, rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    """写 Markdown 摘要。"""
    lines = ["# LLM Judge Summary\n\n", "```json\n", json.dumps(summary, ensure_ascii=False, indent=2), "\n```\n"]
    lines.append("\n## Low Score Examples\n\n")
    ordered = sorted(rows, key=lambda row: row.get("scores", {}).get("overall_quality", 0))
    for row in ordered[:20]:
        lines.append(f"### {row['record_id']}\n")
        lines.append(f"- overall: {row.get('scores', {}).get('overall_quality')}\n")
        lines.append(f"- request: {row.get('request_summary')}\n")
        lines.append(f"- issues: {row.get('major_issues')}\n")
        lines.append(f"- rationale: {row.get('rationale')}\n\n")
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM judge 单模型输出。")
    parser.add_argument("--records", type=Path, default=DEFAULT_EVAL_RECORDS)
    parser.add_argument("--generations", type=Path, default=None)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT_DIR)
    parser.add_argument("--output-file", type=Path, default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--judge-retries", type=int, default=3)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="配合 --resume 使用：只重跑上一轮 skip_reason=judge_failed 的样本。",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records_by_id = load_records_by_id(args.records)
    run_dir = model_run_dir(args.model_name, args.output_dir)
    generations_path = args.generations or (run_dir / "generations.jsonl")
    output_file = args.output_file or (run_dir / "judge_scores.jsonl")
    summary_json = run_dir / "judge_summary.json"
    summary_md = run_dir / "judge_summary.md"

    generations = read_jsonl(generations_path)
    if args.limit > 0:
        generations = generations[: args.limit]
    done_ids = load_done_ids(output_file, retry_failed=args.retry_failed) if args.resume else set()
    todo = [row for row in generations if row.get("record_id") not in done_ids]

    print(f"LLM judge: model={args.model_name}, total={len(generations)}, todo={len(todo)}, workers={args.workers}")
    if args.workers <= 1:
        for index, generation in enumerate(todo, start=1):
            row = safe_judge_one(records_by_id, generation, args)
            append_jsonl(output_file, row)
            print(f"progress {index}/{len(todo)} last={row['record_id']} ok={row.get('ok')}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(safe_judge_one, records_by_id, generation, args): generation["record_id"]
                for generation in todo
            }
            for index, future in enumerate(as_completed(futures), start=1):
                row = future.result()
                append_jsonl(output_file, row)
                print(f"progress {index}/{len(todo)} last={row['record_id']} ok={row.get('ok')}", flush=True)

    rows = list(latest_rows_by_id(output_file).values())
    summary = summarize(rows)
    write_json(summary_json, summary)
    write_summary(summary_md, rows, summary)
    print(f"judge scores: {output_file}")
    print(f"judge summary: {summary_md}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
