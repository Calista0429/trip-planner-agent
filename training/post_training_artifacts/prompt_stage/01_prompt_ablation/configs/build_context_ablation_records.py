"""基于 frozen eval records 生成 PlannerContext 消融版本。

脚本不重新调用工具，只改 record 中的 planner_context、compact_planner_context
以及 planner_query 里的 PlannerContext JSON。system_prompt 和后续执行规则保持不变。
"""

from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VARIANT_ORDER = [
    "full_context",
    "compact_context",
    "topk_context",
    "policy_first_topk_context",
]

POI_KEEP_KEYS = {
    "name",
    "type",
    "district",
    "address",
    "location",
    "matched_keyword",
    "source_bucket",
    "ticket_price_hint",
    "estimated_cost_hint",
    "meal_cost_hint",
    "meal_roles",
    "cuisine_tags",
    "diet_tags",
    "avoid_risk_keywords",
    "price_level",
}

TOPK_LIMITS = {
    "classic_pois": 8,
    "preference_pois": 8,
    "scenic_pois": 8,
    "experience_pois": 4,
    "hotel_pois": 6,
    "food_pois": 10,
}

SNAPSHOT_POI_KEYS = [
    "classic_pois",
    "preference_pois",
    "scenic_pois",
    "experience_pois",
    "hotel_pois",
    "food_pois",
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def trim_poi(item: dict[str, Any]) -> dict[str, Any]:
    """保留规划和评估需要的 POI 字段。"""
    return {key: value for key, value in item.items() if key in POI_KEEP_KEYS and value not in (None, "", [])}


def dedupe_by_name(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for item in items:
        name = str(item.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        output.append(item)
    return output


def context_counts(context: dict[str, Any]) -> dict[str, int]:
    snapshot = context.get("tool_snapshot") or {}
    return {key: len(snapshot.get(key) or []) for key in SNAPSHOT_POI_KEYS + ["trip_weather"]}


def build_policy_summary(context: dict[str, Any]) -> dict[str, Any]:
    request = context.get("request") or {}
    preference = context.get("preference_profile") or {}
    lodging = context.get("lodging_policy") or {}
    constraints = context.get("planner_constraints") or {}
    return {
        "city": request.get("city"),
        "travel_days": request.get("travel_days"),
        "transportation": request.get("transportation"),
        "party": context.get("party") or {},
        "budget_constraint": context.get("budget_constraint") or {},
        "positive_preferences": preference.get("positive_preferences") or [],
        "negative_constraints": preference.get("negative_constraints") or [],
        "diet_avoid": preference.get("diet_avoid") or [],
        "traveler_constraints": preference.get("traveler_constraints") or {},
        "lodging_nights": lodging.get("default_lodging_nights"),
        "budget_fit_policy": constraints.get("budget_fit_policy") or {},
    }


def transform_context(original: dict[str, Any], variant: str) -> dict[str, Any]:
    context = copy.deepcopy(original)
    if variant == "full_context":
        return context

    snapshot = context.setdefault("tool_snapshot", {})
    for key in SNAPSHOT_POI_KEYS:
        values = [trim_poi(item) for item in snapshot.get(key) or []]
        values = dedupe_by_name(values)
        if variant in {"topk_context", "policy_first_topk_context"}:
            values = values[: TOPK_LIMITS[key]]
        snapshot[key] = values

    candidate_counts = dict(snapshot.get("candidate_counts") or {})
    for key in SNAPSHOT_POI_KEYS:
        candidate_counts[key] = len(snapshot.get(key) or [])
    snapshot["candidate_counts"] = candidate_counts

    if variant == "policy_first_topk_context":
        ordered = {
            "version": context.get("version"),
            "policy_summary": build_policy_summary(context),
            "request": context.get("request") or {},
            "party": context.get("party") or {},
            "budget_constraint": context.get("budget_constraint") or {},
            "preference_profile": context.get("preference_profile") or {},
            "lodging_policy": context.get("lodging_policy") or {},
            "pricing_policy": context.get("pricing_policy") or {},
            "route_policy": context.get("route_policy") or {},
            "planner_constraints": context.get("planner_constraints") or {},
            "tool_snapshot": snapshot,
        }
        return {key: value for key, value in ordered.items() if value is not None}

    return context


def replace_context_in_query(query: str, request: dict[str, Any], context: dict[str, Any]) -> str:
    marker = "\n\n请严格遵守:"
    marker_index = query.find(marker)
    suffix = query[marker_index:] if marker_index >= 0 else ""
    city = request.get("city") or context.get("request", {}).get("city") or "目的地"
    days = request.get("travel_days") or context.get("request", {}).get("travel_days") or ""
    context_json = json.dumps(context, ensure_ascii=False, separators=(",", ":"))
    return f"请根据下面的 PlannerContext JSON 生成{city}的{days}天旅行计划。\n\nPlannerContext:\n{context_json}{suffix}"


def build_variant_records(records: list[dict[str, Any]], variant: str, source_records: Path) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    output = []
    for record in records:
        original_context = record.get("compact_planner_context") or record.get("planner_context") or {}
        context = transform_context(original_context, variant)
        row = dict(record)
        row["planner_context"] = context
        row["compact_planner_context"] = context
        row["planner_query"] = replace_context_in_query(str(row.get("planner_query") or ""), row.get("request") or {}, context)
        row["context_variant"] = variant
        row["context_variant_source_records"] = str(source_records)
        row["context_variant_created_at"] = now

        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "context_variant": variant,
                "context_variant_source_records": str(source_records),
                "context_variant_created_at": now,
                "prompt_chars": len(row["planner_query"]),
                "compact_context_chars": len(json.dumps(context, ensure_ascii=False)),
                "tool_counts": context_counts(context),
            }
        )
        row["metadata"] = metadata
        output.append(row)
    return output


def write_summary(path: Path, variant: str, records: list[dict[str, Any]], source_records: Path) -> None:
    before = []
    after = []
    for row in records:
        after.append(context_counts(row.get("compact_planner_context") or {}))
    lines = [
        f"# Context 消融记录：{variant}",
        "",
        f"- 来源 records：`{source_records}`",
        f"- 样本数：{len(records)}",
        "- 改动范围：只改 PlannerContext JSON 和 planner_query 中的上下文；system_prompt 与后续 prompt 规则不变。",
        "",
        "## 变体说明",
        "",
    ]
    if variant == "full_context":
        lines.append("- 不改上下文，作为原始对照。")
    elif variant == "compact_context":
        lines.append("- 不限制候选数量，只裁剪 POI 冗余字段。")
    elif variant == "topk_context":
        lines.append(f"- 裁剪 POI 冗余字段，并按固定 TopK 限制候选数量：`{TOPK_LIMITS}`。")
    elif variant == "policy_first_topk_context":
        lines.append("- 在 topk_context 基础上，把人数、预算、负向约束、住宿晚数等 policy_summary 前置。")
    if after:
        avg = {
            key: round(sum(row.get(key, 0) for row in after) / len(after), 2)
            for key in SNAPSHOT_POI_KEYS + ["trip_weather"]
        }
        lines.extend(["", "## 平均候选数量", "", "```json", json.dumps(avg, ensure_ascii=False, indent=2), "```"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 context 消融 frozen records")
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("training/data/planner/context_ablation"))
    parser.add_argument("--name-prefix", required=True)
    parser.add_argument("--variants", default=",".join(VARIANT_ORDER))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.input_records)
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    unknown = [item for item in variants if item not in VARIANT_ORDER]
    if unknown:
        raise ValueError(f"未知 variant: {unknown}; 可选: {VARIANT_ORDER}")

    for variant in variants:
        output_dir = args.output_root / f"{args.name_prefix}_{variant}"
        output_records = build_variant_records(records, variant, args.input_records)
        write_jsonl(output_dir / "records.jsonl", output_records)
        write_summary(output_dir / "context消融说明.md", variant, output_records, args.input_records)
        avg_prompt_chars = int(sum(len(row.get("planner_query") or "") for row in output_records) / max(len(output_records), 1))
        print(f"{variant}: {len(output_records)} -> {output_dir / 'records.jsonl'} avg_prompt_chars={avg_prompt_chars}")


if __name__ == "__main__":
    main()
