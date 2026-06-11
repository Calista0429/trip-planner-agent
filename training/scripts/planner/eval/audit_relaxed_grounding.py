#!/usr/bin/env python3
"""Side-channel audit for relaxed POI grounding.

This script does not mutate rule-eval reports. It answers one diagnostic
question: if POI matching also normalizes full/half-width forms, common
traditional/simplified variants, brackets, whitespace, and punctuation, how
many strict grounding misses look like evaluator false negatives?
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = PROJECT_ROOT / "backend"
LEGACY_SCRIPTS_DIR = PROJECT_ROOT / "training/scripts/eval"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(LEGACY_SCRIPTS_DIR))

from app.planner.output import (  # noqa: E402
    POI_CITY_PREFIXES,
    POI_NAME_SUFFIXES,
    is_lodging_breakfast_meal,
    is_placeholder_meal_name,
    name_in_candidates,
)
from eval_rule_metrics import meal_semantic_validity  # noqa: E402
from eval_utils import (  # noqa: E402
    candidate_names,
    load_records_by_id,
    metric_rate,
    parse_trip_plan_output,
    read_jsonl,
    summarize_request,
    write_json,
)


SFT_NO_BUDGET_SUM_HARD_KEYS = [
    "json_extract_ok",
    "schema_ok",
    "city_ok",
    "date_range_ok",
    "days_len_ok",
    "day_dates_ok",
    "weather_dates_ok",
    "day_index_ok",
    "accommodation_type_ok",
    "meal_complete",
    "meal_specific_ok",
    "meal_valid_semantics_ok",
    "meal_grounding_ok",
    "attraction_count_ok",
    "attraction_grounding_ok",
    "middle_hotel_ok",
    "invalid_hotel_name_ok",
    "hotel_grounding_ok",
    "hotel_distance_placeholder_ok",
    "location_object_ok",
    "transportation_budget_nonnegative",
    "weather_match",
]


# Small, explainable table for POI-name variants that showed up in the rebuilt
# context. This is intentionally not a phonetic or edit-distance matcher.
TRADITIONAL_TO_SIMPLIFIED = str.maketrans(
    {
        "發": "发",
        "髮": "发",
        "隨": "随",
        "園": "园",
        "館": "馆",
        "樓": "楼",
        "廳": "厅",
        "餐": "餐",
        "廚": "厨",
        "齋": "斋",
        "寶": "宝",
        "貝": "贝",
        "龍": "龙",
        "鳳": "凤",
        "麗": "丽",
        "樂": "乐",
        "麥": "麦",
        "麵": "面",
        "魚": "鱼",
        "鮮": "鲜",
        "雞": "鸡",
        "鴨": "鸭",
        "鵝": "鹅",
        "鹵": "卤",
        "滷": "卤",
        "燒": "烧",
        "烤": "烤",
        "鍋": "锅",
        "湯": "汤",
        "粵": "粤",
        "廣": "广",
        "東": "东",
        "雲": "云",
        "臺": "台",
        "台": "台",
        "灣": "湾",
        "門": "门",
        "閣": "阁",
        "巷": "巷",
        "舊": "旧",
        "藝": "艺",
        "鄉": "乡",
        "鎮": "镇",
        "縣": "县",
        "區": "区",
        "國": "国",
        "華": "华",
        "順": "顺",
        "親": "亲",
        "實": "实",
        "師": "师",
        "壹": "一",
        "貳": "二",
        "參": "三",
        "叁": "三",
        "萬": "万",
        "點": "点",
        "號": "号",
        "會": "会",
        "軒": "轩",
        "莊": "庄",
        "餅": "饼",
        "餃": "饺",
        "飯": "饭",
        "飲": "饮",
        "餛": "馄",
        "飩": "饨",
        "鱔": "鳝",
        "蝦": "虾",
        "蟹": "蟹",
        "煲": "煲",
        "羹": "羹",
        "麩": "麸",
        "鹽": "盐",
        "醬": "酱",
        "醃": "腌",
        "臘": "腊",
        "衚": "胡",
        "鬍": "胡",
        "裏": "里",
        "裡": "里",
        "內": "内",
        "門": "门",
        "長": "长",
        "慶": "庆",
        "慶": "庆",
        "賓": "宾",
        "貴": "贵",
        "陽": "阳",
        "寧": "宁",
        "蘇": "苏",
        "廈": "厦",
        "錦": "锦",
        "橋": "桥",
        "頭": "头",
        "島": "岛",
        "濱": "滨",
        "灣": "湾",
        "獅": "狮",
        "龜": "龟",
        "鷺": "鹭",
        "遙": "遥",
        "遊": "游",
        "覽": "览",
        "戲": "戏",
        "劇": "剧",
        "場": "场",
        "舖": "铺",
        "鋪": "铺",
        "車": "车",
        "馬": "马",
        "騰": "腾",
        "騎": "骑",
        "舘": "馆",
        "範": "范",
        "豐": "丰",
        "億": "亿",
        "銀": "银",
        "鐵": "铁",
        "鐵": "铁",
        "鉑": "铂",
        "鑽": "钻",
        "鑫": "鑫",
    }
)

BRACKET_CONTENT_RE = re.compile(r"[\(\[\{<【（［｛].*?[\)\]\}>】）］｝]")
KEEP_ALNUM_CJK_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+")


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def load_latest_generations(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if record_id:
            rows[record_id] = row
    return rows


def normalize_relaxed_name(name: str, *, strip_brackets: bool) -> str:
    text = unicodedata.normalize("NFKC", str(name or "")).strip().lower()
    if strip_brackets:
        text = BRACKET_CONTENT_RE.sub("", text)
    text = text.translate(TRADITIONAL_TO_SIMPLIFIED)
    text = text.replace("&", "and")
    text = KEEP_ALNUM_CJK_RE.sub("", text)
    return text


def relaxed_aliases(name: str) -> list[str]:
    aliases = {
        normalize_relaxed_name(name, strip_brackets=True),
    }
    aliases = {alias for alias in aliases if len(alias) >= 2}

    for alias in list(aliases):
        for prefix in POI_CITY_PREFIXES:
            prefix_norm = normalize_relaxed_name(prefix, strip_brackets=True)
            if alias.startswith(prefix_norm) and len(alias) > len(prefix_norm) + 1:
                aliases.add(alias[len(prefix_norm) :])

    for alias in list(aliases):
        for suffix in POI_NAME_SUFFIXES:
            suffix_norm = normalize_relaxed_name(suffix, strip_brackets=True)
            if alias.endswith(suffix_norm) and len(alias) > len(suffix_norm) + 1:
                aliases.add(alias[: -len(suffix_norm)])

    return sorted(alias for alias in aliases if len(alias) >= 2)


def relaxed_name_in_candidates(name: str, candidates: list[str]) -> tuple[bool, str | None, str | None]:
    left_aliases = relaxed_aliases(name)
    if not left_aliases:
        return False, None, None
    for candidate in candidates:
        right_aliases = relaxed_aliases(candidate)
        for left in left_aliases:
            for right in right_aliases:
                if left == right or left in right or right in left:
                    return True, candidate, f"{left} ~= {right}"
    return False, None, None


def rate_row(pass_count: int, total: int) -> dict[str, Any]:
    return {
        "pass": pass_count,
        "total": total,
        "rate": metric_rate(pass_count, total),
    }


def rate_text(item: dict[str, Any]) -> str:
    return f"{item['pass']}/{item['total']} ({item['rate']:.2%})"


def append_example(examples: list[dict[str, Any]], item: dict[str, Any], limit: int) -> None:
    if len(examples) < limit:
        examples.append(item)


def audit_plan_grounding(
    *,
    record: dict[str, Any],
    generation: dict[str, Any],
    strict_result: dict[str, Any] | None,
    example_limit: int,
) -> dict[str, Any]:
    output = generation.get("output", "") if generation else ""
    metrics = (strict_result or {}).get("metrics") or {}
    base = {
        "record_id": record["record_id"],
        "request_summary": summarize_request(record),
        "strict_hard_pass": bool(metrics.get("hard_pass")),
        "relaxed_hard_pass_estimate": False,
        "relaxed_metrics": {},
        "item_counts": {},
        "examples": {
            "meal_recovered": [],
            "attraction_recovered": [],
            "hotel_recovered": [],
            "meal_still_invalid": [],
            "meal_still_ungrounded": [],
        },
        "reason_counts": {},
    }

    if not generation or not generation.get("ok"):
        base["parse_error"] = "missing_or_failed_generation"
        return base

    trip_plan, _data, error_stage, error = parse_trip_plan_output(output)
    if error_stage:
        base["parse_error"] = error_stage
        base["parse_message"] = error
        return base

    assert trip_plan is not None
    plan = trip_plan.model_dump()
    attraction_candidates = candidate_names(record, ["classic_pois", "preference_pois", "scenic_pois", "experience_pois"])
    hotel_candidates = candidate_names(record, ["hotel_pois"])
    food_candidates = candidate_names(record, ["food_pois"])

    counts = {
        "meal_total": 0,
        "meal_strict_hit": 0,
        "meal_relaxed_hit": 0,
        "meal_semantic_strict_hit": 0,
        "meal_semantic_relaxed_hit": 0,
        "attraction_total": 0,
        "attraction_strict_hit": 0,
        "attraction_relaxed_hit": 0,
        "hotel_total": 0,
        "hotel_strict_hit": 0,
        "hotel_relaxed_hit": 0,
    }
    reasons: Counter[str] = Counter()

    for day in plan.get("days") or []:
        for attraction in day.get("attractions") or []:
            name = str(attraction.get("name") or "")
            counts["attraction_total"] += 1
            strict_hit = name_in_candidates(name, attraction_candidates)
            relaxed_hit, matched, why = relaxed_name_in_candidates(name, attraction_candidates)
            counts["attraction_strict_hit"] += int(strict_hit)
            counts["attraction_relaxed_hit"] += int(relaxed_hit)
            if not strict_hit and relaxed_hit:
                append_example(
                    base["examples"]["attraction_recovered"],
                    {
                        "record_id": record["record_id"],
                        "date": day.get("date"),
                        "selected": name,
                        "matched_candidate": matched,
                        "match": why,
                    },
                    example_limit,
                )

        hotel = day.get("hotel")
        if isinstance(hotel, dict):
            name = str(hotel.get("name") or "")
            counts["hotel_total"] += 1
            strict_hit = bool(name) and name_in_candidates(name, hotel_candidates)
            relaxed_hit = False
            matched = None
            why = None
            if name:
                relaxed_hit, matched, why = relaxed_name_in_candidates(name, hotel_candidates)
            counts["hotel_strict_hit"] += int(strict_hit)
            counts["hotel_relaxed_hit"] += int(relaxed_hit)
            if not strict_hit and relaxed_hit:
                append_example(
                    base["examples"]["hotel_recovered"],
                    {
                        "record_id": record["record_id"],
                        "date": day.get("date"),
                        "selected": name,
                        "matched_candidate": matched,
                        "match": why,
                    },
                    example_limit,
                )

        for meal in day.get("meals") or []:
            name = str(meal.get("name") or "")
            meal_type = str(meal.get("type") or "").lower()
            counts["meal_total"] += 1
            lodging_breakfast = is_lodging_breakfast_meal(name, meal_type)
            strict_hit = lodging_breakfast or name_in_candidates(name, food_candidates)
            relaxed_candidate_hit = False
            matched = None
            why = None
            if not lodging_breakfast:
                relaxed_candidate_hit, matched, why = relaxed_name_in_candidates(name, food_candidates)
            relaxed_hit = lodging_breakfast or relaxed_candidate_hit
            counts["meal_strict_hit"] += int(strict_hit)
            counts["meal_relaxed_hit"] += int(relaxed_hit)

            if strict_hit:
                strict_semantic_hit = True
                strict_semantic_reason = "strict_candidate_match"
            else:
                strict_validity = meal_semantic_validity(name, meal_type, hotel_candidates)
                strict_semantic_hit = bool(strict_validity["valid"])
                strict_semantic_reason = str(strict_validity["reason"])

            if relaxed_hit:
                relaxed_semantic_hit = True
                relaxed_semantic_reason = "relaxed_candidate_match"
            else:
                relaxed_validity = meal_semantic_validity(name, meal_type, hotel_candidates)
                relaxed_semantic_hit = bool(relaxed_validity["valid"])
                relaxed_semantic_reason = str(relaxed_validity["reason"])

            counts["meal_semantic_strict_hit"] += int(strict_semantic_hit)
            counts["meal_semantic_relaxed_hit"] += int(relaxed_semantic_hit)

            if not strict_hit and relaxed_hit:
                reasons["relaxed_candidate_recovered"] += 1
                append_example(
                    base["examples"]["meal_recovered"],
                    {
                        "record_id": record["record_id"],
                        "date": day.get("date"),
                        "type": meal.get("type"),
                        "selected": name,
                        "matched_candidate": matched,
                        "match": why,
                    },
                    example_limit,
                )
            elif not relaxed_hit:
                if is_placeholder_meal_name(name):
                    reasons["placeholder"] += 1
                elif strict_semantic_hit:
                    reasons[f"semantic_fallback:{strict_semantic_reason}"] += 1
                else:
                    reasons[f"invalid:{relaxed_semantic_reason}"] += 1
                    append_example(
                        base["examples"]["meal_still_invalid"],
                        {
                            "record_id": record["record_id"],
                            "date": day.get("date"),
                            "type": meal.get("type"),
                            "selected": name,
                            "reason": relaxed_semantic_reason,
                        },
                        example_limit,
                    )
                append_example(
                    base["examples"]["meal_still_ungrounded"],
                    {
                        "record_id": record["record_id"],
                        "date": day.get("date"),
                        "type": meal.get("type"),
                        "selected": name,
                        "semantic_reason": strict_semantic_reason,
                    },
                    example_limit,
                )

    relaxed_metrics = dict(metrics)
    relaxed_metrics.update(
        {
            "meal_grounding_rate": metric_rate(counts["meal_relaxed_hit"], counts["meal_total"]),
            "meal_grounding_ok": counts["meal_relaxed_hit"] == counts["meal_total"],
            "meal_food_pois_grounding_rate": metric_rate(counts["meal_relaxed_hit"], counts["meal_total"]),
            "meal_semantic_valid_rate": metric_rate(counts["meal_semantic_relaxed_hit"], counts["meal_total"]),
            "meal_valid_semantics_ok": counts["meal_semantic_relaxed_hit"] == counts["meal_total"],
            "attraction_grounding_rate": metric_rate(counts["attraction_relaxed_hit"], counts["attraction_total"]),
            "attraction_grounding_ok": counts["attraction_relaxed_hit"] == counts["attraction_total"],
            "hotel_grounding_rate": metric_rate(counts["hotel_relaxed_hit"], counts["hotel_total"]),
            "hotel_grounding_ok": counts["hotel_relaxed_hit"] == counts["hotel_total"],
        }
    )
    relaxed_metrics["sft_no_budget_sum_hard_pass"] = all(
        bool(relaxed_metrics.get(key)) for key in SFT_NO_BUDGET_SUM_HARD_KEYS
    )
    relaxed_metrics["sft_hard_pass"] = relaxed_metrics["sft_no_budget_sum_hard_pass"]
    relaxed_metrics["hard_pass"] = relaxed_metrics["sft_hard_pass"]

    base["relaxed_hard_pass_estimate"] = bool(relaxed_metrics["hard_pass"])
    base["relaxed_metrics"] = {
        key: relaxed_metrics.get(key)
        for key in [
            "hard_pass",
            "meal_grounding_ok",
            "meal_valid_semantics_ok",
            "attraction_grounding_ok",
            "hotel_grounding_ok",
            "meal_grounding_rate",
            "meal_semantic_valid_rate",
            "attraction_grounding_rate",
            "hotel_grounding_rate",
        ]
    }
    base["item_counts"] = counts
    base["reason_counts"] = dict(reasons)
    base["recovered_hard_pass"] = bool(not metrics.get("hard_pass") and relaxed_metrics["hard_pass"])
    base["relaxed_fixed_metrics"] = [
        key
        for key in ["meal_grounding_ok", "meal_valid_semantics_ok", "attraction_grounding_ok", "hotel_grounding_ok"]
        if metrics.get(key) is False and relaxed_metrics.get(key) is True
    ]
    return base


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    parsed = sum(1 for row in records if "parse_error" not in row)
    strict_hard = sum(1 for row in records if row.get("strict_hard_pass"))
    relaxed_hard = sum(1 for row in records if row.get("relaxed_hard_pass_estimate"))
    recovered_hard = sum(1 for row in records if row.get("recovered_hard_pass"))

    sums = Counter()
    reason_counts = Counter()
    fixed_metric_counts = Counter()
    example_groups = {
        "meal_recovered": [],
        "attraction_recovered": [],
        "hotel_recovered": [],
        "meal_still_invalid": [],
        "meal_still_ungrounded": [],
        "hard_pass_recovered": [],
        "partially_fixed_records": [],
    }
    for row in records:
        sums.update(row.get("item_counts") or {})
        reason_counts.update(row.get("reason_counts") or {})
        fixed_metric_counts.update(row.get("relaxed_fixed_metrics") or [])
        for name, rows in (row.get("examples") or {}).items():
            for item in rows:
                append_example(example_groups[name], item, 30)
        if row.get("recovered_hard_pass"):
            append_example(
                example_groups["hard_pass_recovered"],
                {
                    "record_id": row["record_id"],
                    "request_summary": row["request_summary"],
                    "fixed_metrics": row.get("relaxed_fixed_metrics") or [],
                },
                30,
            )
        elif row.get("relaxed_fixed_metrics") and not row.get("strict_hard_pass"):
            append_example(
                example_groups["partially_fixed_records"],
                {
                    "record_id": row["record_id"],
                    "request_summary": row["request_summary"],
                    "fixed_metrics": row.get("relaxed_fixed_metrics") or [],
                },
                30,
            )

    return {
        "records": {
            "total": total,
            "parsed": parsed,
            "parse_failed": total - parsed,
        },
        "hard_pass": {
            "strict": rate_row(strict_hard, parsed),
            "relaxed_estimate": rate_row(relaxed_hard, parsed),
            "recovered": recovered_hard,
        },
        "item_grounding": {
            "meal": {
                "strict": rate_row(sums["meal_strict_hit"], sums["meal_total"]),
                "relaxed": rate_row(sums["meal_relaxed_hit"], sums["meal_total"]),
                "recovered_items": sums["meal_relaxed_hit"] - sums["meal_strict_hit"],
            },
            "meal_semantic": {
                "strict": rate_row(sums["meal_semantic_strict_hit"], sums["meal_total"]),
                "relaxed": rate_row(sums["meal_semantic_relaxed_hit"], sums["meal_total"]),
                "recovered_items": sums["meal_semantic_relaxed_hit"] - sums["meal_semantic_strict_hit"],
            },
            "attraction": {
                "strict": rate_row(sums["attraction_strict_hit"], sums["attraction_total"]),
                "relaxed": rate_row(sums["attraction_relaxed_hit"], sums["attraction_total"]),
                "recovered_items": sums["attraction_relaxed_hit"] - sums["attraction_strict_hit"],
            },
            "hotel": {
                "strict": rate_row(sums["hotel_strict_hit"], sums["hotel_total"]),
                "relaxed": rate_row(sums["hotel_relaxed_hit"], sums["hotel_total"]),
                "recovered_items": sums["hotel_relaxed_hit"] - sums["hotel_strict_hit"],
            },
        },
        "fixed_metric_counts": dict(fixed_metric_counts),
        "meal_miss_reason_counts": dict(reason_counts),
        "examples": example_groups,
    }


def audit_report(label: str, report_path: Path, example_limit: int) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    records_path = resolve_project_path(report["records_path"])
    generations_path = resolve_project_path(report["generations_path"])
    records_by_id = load_records_by_id(records_path)
    generations_by_id = load_latest_generations(generations_path)
    strict_results_by_id = {row.get("record_id"): row for row in report.get("results") or [] if row.get("record_id")}

    rows = []
    for record_id, record in records_by_id.items():
        rows.append(
            audit_plan_grounding(
                record=record,
                generation=generations_by_id.get(record_id, {}),
                strict_result=strict_results_by_id.get(record_id),
                example_limit=example_limit,
            )
        )

    return {
        "label": label,
        "report_path": str(report_path.relative_to(PROJECT_ROOT) if report_path.is_relative_to(PROJECT_ROOT) else report_path),
        "records_path": str(records_path.relative_to(PROJECT_ROOT) if records_path.is_relative_to(PROJECT_ROOT) else records_path),
        "generations_path": str(
            generations_path.relative_to(PROJECT_ROOT) if generations_path.is_relative_to(PROJECT_ROOT) else generations_path
        ),
        "summary": summarize_records(rows),
        "records": rows,
    }


def parse_report_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--report must be LABEL=path")
    label, raw_path = value.split("=", 1)
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError("report label cannot be empty")
    return label, resolve_project_path(raw_path.strip())


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Relaxed Grounding Audit\n\n",
        "This is a side-channel audit only. It does not modify `rule_eval_report.json` or the official hard_pass numbers.\n\n",
        "Relaxed matching applies NFKC, lowercase, a small traditional-to-simplified POI character table, bracket/space/punctuation removal, and the existing city-prefix / POI-suffix aliases.\n\n",
        "## Hard Pass Estimate\n\n",
        "| Run | Records | Parsed | Strict hard_pass | Relaxed estimate | Recovered hard_pass |\n",
        "| --- | ---: | ---: | ---: | ---: | ---: |\n",
    ]
    for run in report["runs"]:
        summary = run["summary"]
        records = summary["records"]
        hard = summary["hard_pass"]
        lines.append(
            f"| {run['label']} | {records['total']} | {records['parsed']} | "
            f"{rate_text(hard['strict'])} | {rate_text(hard['relaxed_estimate'])} | {hard['recovered']} |\n"
        )

    lines.extend(
        [
            "\n## Item Grounding\n\n",
            "| Run | Meal strict | Meal relaxed | Meal recovered | Meal semantic strict | Meal semantic relaxed | Attraction strict | Attraction relaxed | Hotel strict | Hotel relaxed |\n",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n",
        ]
    )
    for run in report["runs"]:
        item = run["summary"]["item_grounding"]
        lines.append(
            f"| {run['label']} | "
            f"{rate_text(item['meal']['strict'])} | {rate_text(item['meal']['relaxed'])} | {item['meal']['recovered_items']} | "
            f"{rate_text(item['meal_semantic']['strict'])} | {rate_text(item['meal_semantic']['relaxed'])} | "
            f"{rate_text(item['attraction']['strict'])} | {rate_text(item['attraction']['relaxed'])} | "
            f"{rate_text(item['hotel']['strict'])} | {rate_text(item['hotel']['relaxed'])} |\n"
        )

    lines.extend(["\n## Fixed Metrics\n\n", "| Run | Fixed metric counts | Meal miss reason counts |\n", "| --- | --- | --- |\n"])
    for run in report["runs"]:
        summary = run["summary"]
        lines.append(
            f"| {run['label']} | `{json.dumps(summary['fixed_metric_counts'], ensure_ascii=False)}` | "
            f"`{json.dumps(summary['meal_miss_reason_counts'], ensure_ascii=False)}` |\n"
        )

    lines.append("\n## Recovered Hard-Pass Records\n\n")
    for run in report["runs"]:
        examples = run["summary"]["examples"]["hard_pass_recovered"]
        lines.append(f"### {run['label']}\n\n")
        if not examples:
            lines.append("- none\n\n")
            continue
        for item in examples[:10]:
            lines.append(f"- `{item['record_id']}` fixed={item['fixed_metrics']} request={item['request_summary']}\n")
        lines.append("\n")

    lines.append("## Recovered Meal Examples\n\n")
    for run in report["runs"]:
        examples = run["summary"]["examples"]["meal_recovered"]
        lines.append(f"### {run['label']}\n\n")
        if not examples:
            lines.append("- none\n\n")
            continue
        for item in examples[:12]:
            lines.append(
                f"- `{item['record_id']}` {item.get('date')} {item.get('type')}: "
                f"`{item['selected']}` -> `{item['matched_candidate']}` ({item['match']})\n"
            )
        lines.append("\n")

    lines.append("## Still Invalid Meal Examples\n\n")
    for run in report["runs"]:
        examples = run["summary"]["examples"]["meal_still_invalid"]
        lines.append(f"### {run['label']}\n\n")
        if not examples:
            lines.append("- none\n\n")
            continue
        for item in examples[:10]:
            lines.append(
                f"- `{item['record_id']}` {item.get('date')} {item.get('type')}: "
                f"`{item['selected']}` reason={item['reason']}\n"
            )
        lines.append("\n")

    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit strict vs relaxed POI grounding for existing eval reports.")
    parser.add_argument("--report", action="append", type=parse_report_arg, required=True, help="LABEL=rule_eval_report.json")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "training/outputs/eval/audits/260511_high_end_context_relaxed_grounding",
    )
    parser.add_argument("--example-limit", type=int, default=8)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs = [audit_report(label, path, args.example_limit) for label, path in args.report]
    report = {
        "audit": "relaxed_grounding",
        "official_metrics_mutated": False,
        "normalization": {
            "nfkc": True,
            "lowercase": True,
            "traditional_to_simplified_table": True,
            "strip_bracket_content": True,
            "strip_non_alnum_cjk": True,
            "reuse_city_prefix_and_poi_suffix_aliases": True,
            "phonetic_or_edit_distance": False,
        },
        "runs": runs,
    }

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "relaxed_grounding_audit.json", report)
    write_markdown(output_dir / "relaxed_grounding_audit.md", report)
    print(f"wrote {output_dir / 'relaxed_grounding_audit.md'}")


if __name__ == "__main__":
    main()
