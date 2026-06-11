"""用强模型对 DPO 候选打分。

示例:

  .venv-training-py311/bin/python3 training/scripts/eval/dpo_judge_candidates.py \
    --workers 8 \
    --resume
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dpo_utils import (
    DEFAULT_DPO_CANDIDATES,
    DEFAULT_DPO_JUDGEMENTS,
    DPO_SCORE_KEYS,
    DPO_SCORE_WEIGHTS,
    hard_filter_pass,
    judgement_done_candidate_ids,
    normalize_hard_flags,
    normalize_scores,
)
from eval_utils import append_jsonl, read_jsonl, write_json
from shared.llm_client import DataGenLLM


JUDGE_SYSTEM_PROMPT = """你是严谨的旅行规划偏好评估专家。你需要根据 TripRequest、PlannerContext 和候选 TripPlan 打分。

请只输出 JSON，不要输出 Markdown。
所有分数范围为 1-5，5 分最好。若候选明显违反约束，相关维度必须给低分。
"""


def compact_judge_context(candidate_row: dict[str, Any]) -> dict[str, Any]:
    """给 judge 的压缩上下文。"""
    return {
        "request": candidate_row.get("request") or {},
        "control_spec": candidate_row.get("control_spec") or {},
        "metadata": candidate_row.get("metadata") or {},
    }


def build_judge_prompt(candidate_row: dict[str, Any], candidate: dict[str, Any]) -> str:
    """构造 judge prompt。"""
    weights = ", ".join(f"{key}={weight}" for key, weight in DPO_SCORE_WEIGHTS.items())
    return f"""请评估下面候选旅行计划是否适合作为 DPO chosen。

评分维度:
- grounding: 是否主要使用 PlannerContext 工具候选，是否少幻觉
- budget_alignment: 是否符合预算总额、预算档位和预算分配
- preference_alignment: 是否符合兴趣、同行类型、饮食约束、避雷项和节奏
- weather_awareness: 是否正确使用天气信息，并据此调整行程
- feasibility: 动线、节奏、每天景点数量和酒店位置是否现实可执行
- specificity: 是否具体、清晰、前端可读

overall 请按以下权重计算: {weights}

餐饮特别规则:
- meal.name 如果是“早餐推荐”“午餐推荐”“晚餐推荐”“本地早餐”“当地早餐”“特色餐厅”等占位词，specificity 和 grounding 应明显扣分。
- 酒店早餐/民宿早餐/客栈早餐可以作为 breakfast，且可重复，不按餐饮多样性扣分。
- lunch/dinner 没有使用 food_pois 中的具体餐厅，或写成“无”“酒店晚餐”“酒店午餐”等住宿类/空值餐饮，应写入 major_issues。
- 同一天 lunch 和 dinner 不应是同一家餐厅；整趟行程不应多天反复使用同一家真实餐厅、同一品牌或同一种单品。非住宿早餐如果连续多天重复，也应扣 specificity / overall。

hard_flags 说明:
- has_hallucinated_poi: 是否存在明显脱离工具候选的景点/酒店幻觉
- violates_diet: 是否违反饮食限制
- over_budget: 是否明显超过用户预算
- too_rushed: 是否明显过赶
- bad_hotel: 酒店位置/类型/名称是否明显不合适

请输出 JSON:
{{
  "scores": {{
    "grounding": 1-5,
    "budget_alignment": 1-5,
    "preference_alignment": 1-5,
    "weather_awareness": 1-5,
    "feasibility": 1-5,
    "specificity": 1-5
  }},
  "hard_flags": {{
    "has_hallucinated_poi": true/false,
    "violates_diet": true/false,
    "over_budget": true/false,
    "too_rushed": true/false,
    "bad_hotel": true/false
  }},
  "major_issues": ["问题1", "问题2"],
  "reason": "简短说明为什么这样打分"
}}

TripRequest / control_spec:
{json.dumps(compact_judge_context(candidate_row), ensure_ascii=False)}

规则评估结果:
{json.dumps({"metrics": candidate.get("rule_metrics", {}), "errors": candidate.get("rule_errors", [])}, ensure_ascii=False)}

候选 TripPlan:
{candidate.get("output_text", "")}
"""


def iter_judge_items(candidate_rows: list[dict[str, Any]], args: argparse.Namespace) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """展开需要 judge 的候选。"""
    items = []
    for row in candidate_rows:
        for candidate in row.get("candidates") or []:
            passed, reasons = hard_filter_pass(
                candidate,
                min_attraction_grounding=args.min_attraction_grounding,
                min_hotel_grounding=args.min_hotel_grounding,
            )
            if not passed:
                continue
            items.append((row, candidate))
    if args.limit > 0:
        items = items[: args.limit]
    return items


def judge_one(candidate_row: dict[str, Any], candidate: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    """judge 一个候选。"""
    llm = DataGenLLM()
    data = llm.complete_json(
        JUDGE_SYSTEM_PROMPT,
        build_judge_prompt(candidate_row, candidate),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )
    if not isinstance(data, dict):
        raise ValueError("judge output is not a JSON object")

    scores = normalize_scores(data.get("scores") or {})
    flags = normalize_hard_flags(data.get("hard_flags") or {})
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt_id": candidate_row["prompt_id"],
        "record_id": candidate_row["record_id"],
        "candidate_id": candidate["candidate_id"],
        "source_model": candidate.get("source_model"),
        "source_type": candidate.get("source_type"),
        "temperature": candidate.get("temperature"),
        "judge_model": llm.model,
        "ok": True,
        "scores": scores,
        "hard_flags": flags,
        "major_issues": data.get("major_issues", []),
        "reason": data.get("reason", ""),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总 judge 结果。"""
    valid = [row for row in rows if row.get("ok")]
    averages = {
        key: round(sum(row.get("scores", {}).get(key, 0) for row in valid) / len(valid), 4)
        if valid
        else 0.0
        for key in [*DPO_SCORE_KEYS, "overall"]
    }
    return {
        "total": len(rows),
        "ok": len(valid),
        "scores_avg": averages,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="对 DPO 候选做 LLM judge。")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_DPO_CANDIDATES)
    parser.add_argument("--output", type=Path, default=DEFAULT_DPO_JUDGEMENTS)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-tokens", type=int, default=1800)
    parser.add_argument("--min-attraction-grounding", type=float, default=0.7)
    parser.add_argument("--min-hotel-grounding", type=float, default=0.8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    candidate_rows = read_jsonl(args.candidates)
    items = iter_judge_items(candidate_rows, args)
    done_ids = judgement_done_candidate_ids(args.output) if args.resume else set()
    todo = [(row, candidate) for row, candidate in items if candidate["candidate_id"] not in done_ids]

    config_path = args.output.parent / "judge_config.json"
    write_json(
        config_path,
        {
            "candidates": str(args.candidates),
            "output": str(args.output),
            "items": len(items),
            "todo": len(todo),
            "workers": args.workers,
            "min_attraction_grounding": args.min_attraction_grounding,
            "min_hotel_grounding": args.min_hotel_grounding,
        },
    )

    print(f"DPO judge: candidates={len(items)}, todo={len(todo)}, workers={args.workers}")
    ok = 0
    failed = 0
    if args.workers <= 1:
        for index, (candidate_row, candidate) in enumerate(todo, start=1):
            try:
                row = judge_one(candidate_row, candidate, args)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                row = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "prompt_id": candidate_row["prompt_id"],
                    "record_id": candidate_row["record_id"],
                    "candidate_id": candidate["candidate_id"],
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                failed += 1
            append_jsonl(args.output, row)
            print(f"progress {index}/{len(todo)} ok={ok} failed={failed} last={row['candidate_id']}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(judge_one, row, candidate, args): candidate["candidate_id"] for row, candidate in todo}
            for index, future in enumerate(as_completed(futures), start=1):
                candidate_id = futures[future]
                try:
                    row = future.result()
                    ok += 1
                except Exception as exc:  # noqa: BLE001
                    row = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "candidate_id": candidate_id,
                        "ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                    failed += 1
                append_jsonl(args.output, row)
                print(f"progress {index}/{len(todo)} ok={ok} failed={failed} last={candidate_id}", flush=True)

    rows = read_jsonl(args.output)
    summary = summarize(rows)
    write_json(args.output.parent / "judge_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
