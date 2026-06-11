#!/usr/bin/env python3
"""用最新规则重新计算 DPO candidate 文件里的 rule metrics。

用途：评估/硬过滤规则改动后，不需要重新调用本地模型或强模型，只要复用
已有 output_text，就能刷新 parsed_ok、schema_ok、rule_metrics、rule_errors
和 hard_filter_pass。

Examples:
  cd helloagents-trip-planner

  .venv-training-py311/bin/python3 training/scripts/eval/dpo_refresh_candidate_metrics.py \
    --input training/data/legacy/dpo/candidates_vllm_5way_budget_norm_smoke20.jsonl \
    --output training/data/legacy/dpo/candidates_vllm_5way_budget_norm_smoke20_refreshed.jsonl
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from dpo_utils import hard_filter_pass
from eval_utils import budget_alignment_details, parse_trip_plan_output, read_jsonl, write_jsonl


def refresh_candidate(row: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """刷新单个 candidate 的规则评估字段。"""
    output = str(candidate.get("output_text") or "")
    generation_meta = candidate.get("generation_meta") or {}
    generation_ok = bool(output) and generation_meta.get("ok") is not False

    refreshed = dict(candidate)
    if not generation_ok:
        refreshed["parsed_ok"] = False
        refreshed["schema_ok"] = False
        refreshed["trip_plan"] = None
        refreshed["rule_metrics"] = {}
        refreshed["rule_errors"] = [{"stage": "call", "message": generation_meta.get("error") or "call failed"}]
    else:
        trip_plan, _, error_stage, _ = parse_trip_plan_output(output)
        refreshed["parsed_ok"] = error_stage != "json_extract"
        refreshed["schema_ok"] = trip_plan is not None
        refreshed["trip_plan"] = trip_plan.model_dump() if trip_plan else None
        metrics = dict(candidate.get("rule_metrics") or {})
        rule_errors = [
            item
            for item in candidate.get("rule_errors") or []
            if item.get("type") != "hotel_budget_underestimated"
        ]
        if trip_plan:
            plan = trip_plan.model_dump()
            record = {
                "record_id": row.get("record_id"),
                "request": row.get("request") or {},
                "control_spec": row.get("control_spec") or {},
            }
            budget_eval = budget_alignment_details(record, plan.get("budget"), plan)
            metrics["budget_consistent"] = budget_eval["arithmetic_consistent"]
            metrics["budget_arithmetic_consistent"] = budget_eval["arithmetic_consistent"]
            metrics["budget_within_user_budget"] = budget_eval["within_user_budget"]
            metrics["budget_level_aligned"] = budget_eval["level_aligned"]
            metrics["budget_preference_aligned"] = budget_eval["preference_aligned"]
            metrics["hotel_budget_covers_nights"] = budget_eval["hotel_budget_covers_nights"]
            if not budget_eval["hotel_budget_covers_nights"]:
                rule_errors.append(
                    {
                        "stage": "rule",
                        "type": "hotel_budget_underestimated",
                        "details": budget_eval["hotel_budget"],
                    }
                )
        refreshed["rule_metrics"] = metrics
        refreshed["rule_errors"] = rule_errors

    passed, reasons = hard_filter_pass(refreshed)
    refreshed["hard_filter_pass"] = passed
    refreshed["hard_filter_reasons"] = reasons
    return refreshed


def refresh_row(row: dict[str, Any]) -> dict[str, Any]:
    """刷新一行 prompt 下的所有 candidates。"""
    refreshed = dict(row)
    refreshed["candidates"] = [refresh_candidate(row, item) for item in row.get("candidates") or []]
    return refreshed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用最新规则刷新 DPO candidate rule metrics。")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.input)
    refreshed = [refresh_row(row) for row in rows]
    write_jsonl(args.output, refreshed)
    total = sum(len(row.get("candidates") or []) for row in refreshed)
    passed = sum(1 for row in refreshed for item in row.get("candidates") or [] if item.get("hard_filter_pass"))
    print(f"刷新完成: rows={len(refreshed)}, candidates={total}, hard_pass={passed}")
    print(f"输出: {args.output}")


if __name__ == "__main__":
    main()
