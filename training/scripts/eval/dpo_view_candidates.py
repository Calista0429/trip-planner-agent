#!/usr/bin/env python3
"""把 legacy DPO candidate JSONL 渲染成紧凑的中文 Markdown 报告。

Examples:
  cd helloagents-trip-planner

  # Print the first 3 prompts to terminal.
  .venv-training-py311/bin/python3 training/scripts/eval/dpo_view_candidates.py \
    --input training/data/legacy/dpo/candidates_vllm_5way_smoke20.jsonl \
    --limit 3

  # Export a readable Markdown report.
  .venv-training-py311/bin/python3 training/scripts/eval/dpo_view_candidates.py \
    --input training/data/legacy/dpo/candidates_vllm_5way_smoke20.jsonl \
    --limit 20 \
    --output training/data/legacy/dpo/candidates_vllm_5way_smoke20_preview.md

  # Inspect prompts that contain at least one invalid candidate.
  .venv-training-py311/bin/python3 training/scripts/eval/dpo_view_candidates.py \
    --only-invalid \
    --show-output
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from dpo_utils import hard_filter_pass


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INPUT = PROJECT_ROOT / "training/data/legacy/dpo/candidates_vllm_5way_smoke20.jsonl"

SOURCE_NAMES = {
    "base": "基模",
    "sft": "SFT模型",
    "strong": "强模型",
}

METRIC_NAMES = {
    "budget_consistent": "预算一致",
    "budget_arithmetic_consistent": "预算分项求和一致",
    "hotel_budget_covers_nights": "酒店预算覆盖住宿晚数",
    "budget_within_user_budget": "未超用户预算",
    "budget_level_aligned": "预算档位匹配",
    "budget_preference_aligned": "预算偏好匹配",
    "weather_match": "天气匹配",
}

REASON_NAMES = {
    "generation_failed": "生成调用失败",
    "json_extract_ok": "JSON解析失败",
    "schema_ok": "结构校验失败",
    "city_ok": "城市不匹配",
    "date_range_ok": "起止日期不匹配",
    "days_len_ok": "天数不匹配",
    "day_dates_ok": "每日日期不匹配",
    "weather_dates_ok": "天气日期不匹配",
    "day_index_ok": "day_index不正确",
    "meal_complete": "餐饮不完整",
    "middle_hotel_ok": "中间天酒店缺失",
    "invalid_hotel_name_ok": "酒店名称非法",
    "location_object_ok": "经纬度格式错误",
    "budget_arithmetic_consistent": "预算分项求和不一致",
    "hotel_budget_covers_nights": "酒店预算未覆盖住宿晚数",
    "weather_match": "天气未对齐",
    "attraction_grounding_low": "景点工具命中率低",
    "hotel_grounding_low": "酒店工具命中率低",
    "unknown": "未知原因",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def candidate_label(candidate: dict[str, Any]) -> str:
    candidate_id = str(candidate.get("candidate_id") or "")
    parts = candidate_id.split("__")
    if len(parts) >= 2:
        return parts[1]
    source_type = candidate.get("source_type") or "unknown"
    temperature = candidate.get("temperature")
    return f"{source_type}_t{temperature}"


def source_name(value: Any) -> str:
    return SOURCE_NAMES.get(str(value), str(value or ""))


def reason_name(value: Any) -> str:
    return REASON_NAMES.get(str(value), str(value or ""))


def short_text(value: Any, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def join_names(items: list[dict[str, Any]], limit: int = 5) -> str:
    names = [str(item.get("name") or "").strip() for item in items]
    names = [name for name in names if name]
    if len(names) > limit:
        names = names[:limit] + [f"...(+{len(names) - limit})"]
    return " / ".join(names)


def budget_summary(plan: dict[str, Any]) -> str:
    budget = plan.get("budget") or {}
    if not isinstance(budget, dict):
        return ""

    parts = [
        ("总计", budget.get("total")),
        ("景点", budget.get("total_attractions")),
        ("酒店", budget.get("total_hotels")),
        ("餐饮", budget.get("total_meals")),
        ("交通", budget.get("total_transportation")),
    ]
    return ", ".join(f"{key}={value}" for key, value in parts if value is not None)


def first_day_summary(plan: dict[str, Any]) -> dict[str, str]:
    days = plan.get("days") or []
    first_day = days[0] if days and isinstance(days[0], dict) else {}
    hotel = first_day.get("hotel") if isinstance(first_day, dict) else {}
    hotel = hotel if isinstance(hotel, dict) else {}
    attractions = first_day.get("attractions") if isinstance(first_day, dict) else []
    meals = first_day.get("meals") if isinstance(first_day, dict) else []
    return {
        "hotel": str(hotel.get("name") or ""),
        "hotel_cost": str(hotel.get("estimated_cost") or ""),
        "attractions": join_names(attractions if isinstance(attractions, list) else []),
        "meals": join_names(meals if isinstance(meals, list) else []),
    }


def important_metrics(candidate: dict[str, Any]) -> str:
    metrics = candidate.get("rule_metrics") or {}
    if not isinstance(metrics, dict):
        return ""

    pieces = []
    grounding = metrics.get("attraction_grounding_rate")
    hotel_grounding = metrics.get("hotel_grounding_rate")
    if grounding is not None:
        pieces.append(f"景点命中={grounding:.2f}" if isinstance(grounding, float) else f"景点命中={grounding}")
    if hotel_grounding is not None:
        pieces.append(
            f"酒店命中={hotel_grounding:.2f}"
            if isinstance(hotel_grounding, float)
            else f"酒店命中={hotel_grounding}"
        )

    for key in [
        "budget_consistent",
        "hotel_budget_covers_nights",
        "budget_within_user_budget",
        "budget_level_aligned",
        "budget_preference_aligned",
        "weather_match",
    ]:
        if key in metrics:
            pieces.append(f"{METRIC_NAMES[key]}={metrics[key]}")
    return ", ".join(pieces)


def hard_filter(candidate: dict[str, Any]) -> tuple[bool, list[str]]:
    """展示时动态重算硬过滤结果，避免读取旧文件里级联的失败原因。"""
    return hard_filter_pass(candidate)


def render_request(row: dict[str, Any]) -> list[str]:
    request = row.get("request") or {}
    control = row.get("control_spec") or {}
    metadata = row.get("metadata") or {}
    lines = []
    lines.append(
        f"**用户请求**: {request.get('city')} "
        f"{request.get('start_date')} -> {request.get('end_date')} "
        f"| 天数={request.get('travel_days')} "
        f"| 交通={request.get('transportation')} "
        f"| 住宿={request.get('accommodation')}"
    )
    preferences = request.get("preferences") or []
    if preferences:
        lines.append(f"**偏好**: {' / '.join(str(item) for item in preferences)}")
    if request.get("free_text_input"):
        lines.append(f"**自由文本**: {request.get('free_text_input')}")
    if control:
        lines.append(
            f"**抽样控制**: 预算={control.get('budget_level')} "
            f"| 同行={control.get('companion_type')} "
            f"| 节奏={control.get('pace')} "
            f"| 酒店={control.get('hotel_level')}"
        )
    if metadata:
        lines.append(
            f"**上下文**: prompt字符数={metadata.get('prompt_chars')} "
            f"| 行程天数={metadata.get('trip_days')}"
        )
    return lines


def render_candidate_table(row: dict[str, Any]) -> list[str]:
    lines = [
        "| 候选 | 来源 | 温度 | 硬过滤 | 预算 | 第一天酒店 | 第一天景点 | 第一天餐饮 | 关键指标 | 失败原因 |",
        "| --- | --- | ---: | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for candidate in row.get("candidates") or []:
        passed, reasons = hard_filter(candidate)
        plan = candidate.get("trip_plan") or {}
        day = first_day_summary(plan if isinstance(plan, dict) else {})
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(candidate_label(candidate)),
                    md_escape(source_name(candidate.get("source_type"))),
                    md_escape(candidate.get("temperature")),
                    "通过" if passed else "失败",
                    md_escape(budget_summary(plan if isinstance(plan, dict) else {})),
                    md_escape(f"{day['hotel']} ({day['hotel_cost']})"),
                    md_escape(day["attractions"]),
                    md_escape(day["meals"]),
                    md_escape(important_metrics(candidate)),
                    md_escape(", ".join(reason_name(item) for item in reasons)),
                ]
            )
            + " |"
        )
    return lines


def render_candidate_details(row: dict[str, Any], max_output_chars: int, show_output: bool) -> list[str]:
    lines: list[str] = []
    for candidate in row.get("candidates") or []:
        passed, reasons = hard_filter(candidate)
        plan = candidate.get("trip_plan") or {}
        suggestions = plan.get("overall_suggestions") if isinstance(plan, dict) else ""
        lines.append(f"<details><summary>{candidate_label(candidate)} 候选详情</summary>")
        lines.append("")
        lines.append(f"- 候选ID: `{candidate.get('candidate_id')}`")
        lines.append(f"- 模型: `{candidate.get('source_model')}`")
        lines.append(f"- JSON解析/结构校验: {candidate.get('parsed_ok')} / {candidate.get('schema_ok')}")
        lines.append(f"- 硬过滤通过: {passed}")
        generation_meta = candidate.get("generation_meta") or {}
        attempts = generation_meta.get("attempts")
        if attempts:
            lines.append(
                f"- 生成尝试: {attempts}/{generation_meta.get('max_json_parse_attempts', attempts)} "
                f"| JSON重试={generation_meta.get('json_parse_retry_count', 0)}"
            )
        if reasons:
            lines.append(f"- 硬过滤原因: {', '.join(reason_name(item) for item in reasons)}")
        if suggestions:
            lines.append(f"- 总体建议: {short_text(suggestions, 280)}")
        rule_errors = candidate.get("rule_errors") or []
        if rule_errors:
            lines.append("- 规则错误:")
            for error in rule_errors[:5]:
                lines.append(f"  - `{error.get('type')}` {short_text(error.get('details'), 240)}")
        if show_output:
            lines.append("")
            lines.append("```json")
            lines.append(short_text(candidate.get("output_text"), max_output_chars))
            lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return lines


def render_summary(rows: list[dict[str, Any]]) -> list[str]:
    total_candidates = 0
    valid_candidates = 0
    per_prompt_valid = Counter()
    by_label: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    fail_reasons = Counter()

    for row in rows:
        valid_for_row = 0
        for candidate in row.get("candidates") or []:
            passed, reasons = hard_filter(candidate)
            label = candidate_label(candidate)
            by_label[label][1] += 1
            total_candidates += 1
            if passed:
                by_label[label][0] += 1
                valid_candidates += 1
                valid_for_row += 1
            else:
                for reason in reasons or ["unknown"]:
                    fail_reasons[str(reason)] += 1
        per_prompt_valid[valid_for_row] += 1

    lines = [
        "# DPO候选数据预览",
        "",
        "## 汇总",
        "",
        f"- prompt数量: {len(rows)}",
        f"- 候选总数: {total_candidates}",
        f"- 有效候选数: {valid_candidates}",
        "",
        "### 各候选来源通过率",
        "",
        "| 候选来源 | 通过数 | 总数 | 通过率 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for label in sorted(by_label):
        passed, total = by_label[label]
        rate = passed / total if total else 0.0
        lines.append(f"| {label} | {passed} | {total} | {rate:.1%} |")

    lines.extend(["", "### 每个prompt的有效候选数", "", "| 有效候选数 | prompt数量 |", "| ---: | ---: |"])
    for valid_count in sorted(per_prompt_valid):
        lines.append(f"| {valid_count} | {per_prompt_valid[valid_count]} |")

    if fail_reasons:
        lines.extend(["", "### 失败原因", "", "| 原因 | 次数 |", "| --- | ---: |"])
        for reason, count in fail_reasons.most_common(20):
            lines.append(f"| {md_escape(reason_name(reason))} | {count} |")

    return lines


def select_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    selected = rows
    if args.prompt_id:
        prompt_ids = set(args.prompt_id)
        selected = [row for row in selected if row.get("prompt_id") in prompt_ids]
    if args.only_invalid:
        selected = [
            row
            for row in selected
            if any(not hard_filter(candidate)[0] for candidate in row.get("candidates") or [])
        ]
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def render(rows: list[dict[str, Any]], selected: list[dict[str, Any]], args: argparse.Namespace) -> str:
    lines = render_summary(rows)
    if args.summary_only:
        return "\n".join(lines) + "\n"

    lines.extend(["", "## 提示词明细", ""])
    if not selected:
        lines.append("_没有选中的数据。_")
        return "\n".join(lines) + "\n"

    for index, row in enumerate(selected, 1):
        lines.append(f"### {index}. {row.get('prompt_id')} / {row.get('record_id')}")
        lines.append("")
        lines.extend(render_request(row))
        lines.append("")
        lines.extend(render_candidate_table(row))
        lines.append("")
        lines.extend(render_candidate_details(row, args.max_output_chars, args.show_output))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把 legacy DPO candidates 渲染成终端/Markdown 中文报告。")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=None, help="Markdown报告输出路径。")
    parser.add_argument("--limit", type=int, default=3, help="展示多少条prompt。传 -1 表示全部。")
    parser.add_argument("--prompt-id", action="append", default=[], help="只看指定prompt_id，可重复传入。")
    parser.add_argument("--only-invalid", action="store_true", help="只看至少包含一个失败候选的prompt。")
    parser.add_argument("--summary-only", action="store_true", help="只打印整体汇总。")
    parser.add_argument("--show-output", action="store_true", help="在详情里展示截断后的模型原始输出。")
    parser.add_argument("--max-output-chars", type=int, default=1400)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        args.limit = None
    return args


def main() -> None:
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Input file does not exist: {args.input}")

    rows = read_jsonl(args.input)
    selected = select_rows(rows, args)
    report = render(rows, selected, args)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"已写入: {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
