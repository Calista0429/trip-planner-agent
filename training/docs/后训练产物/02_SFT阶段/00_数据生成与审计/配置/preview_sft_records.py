"""把显式传入的 SFT records.jsonl 可视化成中文 Markdown。

这个脚本只做人工审阅视图，不改训练数据。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL，文件不存在时返回空列表。"""
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def short_text(value: Any, limit: int = 180) -> str:
    """压缩长文本。"""
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def fmt_list(values: list[Any], empty: str = "无") -> str:
    """列表展示。"""
    items = [str(item) for item in values if str(item).strip()]
    return " / ".join(items) if items else empty


def fmt_budget(budget: dict[str, Any] | None) -> str:
    """预算摘要。"""
    if not budget:
        return "无"
    return (
        f"总计={budget.get('total')}，"
        f"景点={budget.get('total_attractions')}，"
        f"酒店={budget.get('total_hotels')}，"
        f"餐饮={budget.get('total_meals')}，"
        f"交通={budget.get('total_transportation')}"
    )


def fmt_weather(rows: list[dict[str, Any]]) -> str:
    """天气摘要。"""
    if not rows:
        return "无"
    parts = []
    for item in rows:
        parts.append(
            f"{item.get('date')} {item.get('day_weather')}/{item.get('night_weather')} "
            f"{item.get('day_temp')}/{item.get('night_temp')} source={item.get('source', '')}"
        )
    return "；".join(parts)


def day_summary(day: dict[str, Any]) -> list[str]:
    """单日摘要。"""
    hotel = day.get("hotel") or {}
    attractions = day.get("attractions") or []
    meals = day.get("meals") or []
    return [
        f"- D{int(day.get('day_index', 0)) + 1} `{day.get('date')}`：{short_text(day.get('description'), 140)}",
        f"  - 住宿：{hotel.get('name') or '无'} | {hotel.get('estimated_cost', '')} 元/晚 | accommodation={day.get('accommodation')}",
        "  - 景点："
        + fmt_list([f"{item.get('name')}({item.get('ticket_price')}元)" for item in attractions]),
        "  - 餐饮："
        + fmt_list([f"{item.get('type')}:{item.get('name')}({item.get('estimated_cost')}元)" for item in meals]),
    ]


def record_section(index: int, record: dict[str, Any]) -> list[str]:
    """单条记录 Markdown。"""
    request = record.get("request") or {}
    control = record.get("control_spec") or {}
    context = record.get("planner_context") or {}
    snapshot = context.get("tool_snapshot") or {}
    plan = record.get("trip_plan") or {}
    metadata = record.get("metadata") or {}
    food_pois = snapshot.get("food_pois") or []
    breakfast_food_count = sum("breakfast" in (item.get("meal_roles") or []) for item in food_pois)

    lines = [
        f"## #{index} {record.get('record_id')}",
        "",
        "### 用户请求",
        "",
        f"- 城市/日期：{request.get('city')} | {request.get('start_date')} -> {request.get('end_date')} | {request.get('travel_days')} 天",
        f"- 同行人数：{request.get('party')}",
        f"- 交通/住宿：{request.get('transportation')} / {request.get('accommodation')}",
        f"- 预算约束：{request.get('budget_constraint')}",
        f"- 正向偏好：{fmt_list(request.get('preferences') or [])}",
        f"- 自由文本：{request.get('free_text_input') or '无'}",
        "",
        "### 结构化约束",
        "",
        f"- positive_preferences：{fmt_list(control.get('positive_preferences') or [])}",
        f"- negative_constraints：{fmt_list(control.get('negative_constraints') or [])}",
        f"- diet_positive：{fmt_list(control.get('diet_positive') or [])}",
        f"- diet_avoid：{fmt_list(control.get('diet_avoid') or [])}",
        f"- traveler_constraints：{control.get('traveler_constraints') or {}}",
        "",
        "### 工具快照",
        "",
        (
            f"- 候选数量：classic={len(snapshot.get('classic_pois') or [])}，"
            f"preference={len(snapshot.get('preference_pois') or [])}，"
            f"scenic={len(snapshot.get('scenic_pois') or [])}，"
            f"experience={len(snapshot.get('experience_pois') or [])}，"
            f"hotel={len(snapshot.get('hotel_pois') or [])}，"
            f"food={len(food_pois)}，breakfast_food={breakfast_food_count}，"
            f"route={len(snapshot.get('route_hints') or [])}"
        ),
        f"- 天气：{fmt_weather(snapshot.get('trip_weather') or [])}",
        f"- prompt_chars：{metadata.get('prompt_chars')}，output_chars：{metadata.get('output_chars')}，weather_provider：{metadata.get('weather_provider')}",
        "",
        "### 模型输出摘要",
        "",
        f"- 预算：{fmt_budget(plan.get('budget'))}",
        f"- 总体建议：{short_text(plan.get('overall_suggestions'), 220)}",
        "",
    ]

    for day in plan.get("days") or []:
        lines.extend(day_summary(day))
    lines.append("")
    return lines


def error_section(errors: list[dict[str, Any]]) -> list[str]:
    """失败样本摘要。"""
    lines = ["# 失败样本", ""]
    if not errors:
        lines.append("无")
        return lines
    for index, row in enumerate(errors, start=1):
        lines.extend(
            [
                f"## 失败 #{index} {row.get('record_id')}",
                "",
                f"- error_type：{row.get('error_type')}",
                f"- error：{row.get('error')}",
                "",
            ]
        )
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description="可视化 SFT records.jsonl")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--errors", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0, help="最多展示多少条成功样本，0表示全部")
    args = parser.parse_args()

    records = read_jsonl(args.records)
    errors = read_jsonl(args.errors)
    if args.limit > 0:
        records = records[: args.limit]

    lines = [
        "# SFT Smoke 数据中文预览",
        "",
        "## 总览",
        "",
        f"- 成功样本：{len(records)}",
        f"- 失败样本：{len(errors)}",
        f"- records：`{args.records}`",
        f"- errors：`{args.errors}`",
        "",
    ]
    for index, record in enumerate(records, start=1):
        lines.extend(record_section(index, record))
    lines.extend(error_section(errors))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(f"preview: {args.output}")
    print(f"records={len(records)} errors={len(errors)}")


if __name__ == "__main__":
    main()
