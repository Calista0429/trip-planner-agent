"""审计现有 SFT 数据的预算请求和 teacher 预算是否贴合当前预算口径。

本脚本只读取显式传入的 records.jsonl，不调用外部 API。
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
AUDIT_SCRIPT_DIR = Path(__file__).resolve().parent
DATA_SCRIPT_DIR = SCRIPTS_DIR / "planner" / "data"
EVAL_SCRIPT_DIR = SCRIPTS_DIR / "planner" / "eval"
sys.path[:0] = [str(AUDIT_SCRIPT_DIR), str(DATA_SCRIPT_DIR), str(EVAL_SCRIPT_DIR)]

from audit_budget_utilization_contexts import audit_context  # noqa: E402
from build_eval_set import (  # noqa: E402
    EVAL_CITY_BUDGET_FACTORS,
    EVAL_HOTEL_COST_BY_ACCOMMODATION,
    EVAL_PERSON_DAY_BUDGETS,
    EVAL_SHARED_TRANSPORT_DAY_COST,
    infer_city_tier,
)
from generate_sft_data import BUDGET_USAGE_RATIO_BY_LEVEL  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="审计 SFT 预算贴合度")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.records)
    rows = [audit_record(record) for record in records]
    summary = build_summary(rows)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows_path = args.output_dir / "audit_rows.jsonl"
    summary_path = args.output_dir / "summary.json"
    report_path = args.output_dir / "sft_budget_fit_audit.md"

    write_jsonl(rows_path, rows)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(summary, rows, args.records, rows_path), encoding="utf-8")

    print(f"records={args.records}")
    print(f"rows={rows_path}")
    print(f"summary={summary_path}")
    print(f"report={report_path}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def audit_record(record: dict[str, Any]) -> dict[str, Any]:
    request = record.get("request") or {}
    control_spec = record.get("control_spec") or {}
    budget = request.get("budget_constraint") or {}
    planner_context = record.get("planner_context") or {}
    trip_plan = record.get("trip_plan") or {}
    amount = int(budget.get("amount") or control_spec.get("budget_amount") or 0)
    level = str(budget.get("budget_level") or control_spec.get("budget_level") or "standard")
    strictness = str(budget.get("strictness") or control_spec.get("budget_strictness") or "unknown")
    party = request.get("party") or {}
    party_total = max(int(party.get("total") or 1), 1)
    travel_days = max(int(request.get("travel_days") or 1), 1)
    accommodation = str(request.get("accommodation") or "舒适型酒店")
    transportation = str(request.get("transportation") or "公共交通")
    city_tier = str(control_spec.get("city_tier") or infer_city_tier(str(request.get("city") or "")))
    recommended = recommended_budget_range(level, party_total, travel_days, accommodation, transportation, city_tier)
    request_status = classify(amount, recommended["min"], recommended["max"])

    target = budget_target_range(amount, level, strictness)
    teacher_total = int(((trip_plan.get("budget") or {}).get("total")) or 0)
    teacher_status = classify(teacher_total, target["min"], target["max"]) if target["enabled"] else "no_budget_policy"

    candidate_audit = audit_context(request, planner_context) if planner_context else {}
    high_ratio = float(candidate_audit.get("high_budget_ratio") or 0)
    food_count = int(((candidate_audit.get("tool_counts") or {}).get("food_pois")) or 0)

    return {
        "record_id": record.get("record_id"),
        "city": request.get("city"),
        "budget_level": level,
        "strictness": strictness,
        "amount": amount,
        "teacher_budget_total": teacher_total,
        "party_total": party_total,
        "travel_days": travel_days,
        "accommodation": accommodation,
        "transportation": transportation,
        "city_tier": city_tier,
        "recommended_min": recommended["min"],
        "recommended_max": recommended["max"],
        "recommended_mid": recommended["mid"],
        "request_budget_status": request_status,
        "target_min": target["min"],
        "target_max": target["max"],
        "teacher_budget_status": teacher_status,
        "candidate_high_ratio": round(high_ratio, 4),
        "candidate_reach_amount": high_ratio >= 1.0 if amount else False,
        "food_pois": food_count,
    }


def recommended_budget_range(
    level: str,
    party_total: int,
    travel_days: int,
    accommodation: str,
    transportation: str,
    city_tier: str,
) -> dict[str, int]:
    level = "premium" if level == "luxury" else level
    ppds = EVAL_PERSON_DAY_BUDGETS.get(level, EVAL_PERSON_DAY_BUDGETS["standard"])
    values = [
        realistic_budget_amount(ppd, party_total, travel_days, accommodation, transportation, city_tier)
        for ppd in ppds
    ]
    return {
        "min": min(values),
        "max": max(values),
        "mid": int(round(statistics.median(values))),
    }


def realistic_budget_amount(
    per_person_day: int,
    party_total: int,
    travel_days: int,
    accommodation: str,
    transportation: str,
    city_tier: str,
) -> int:
    lodging_nights = max(travel_days - 1, 0)
    room_count = max(1, math.ceil(party_total / 2))
    lodging_per_night = EVAL_HOTEL_COST_BY_ACCOMMODATION.get(accommodation, 520)
    shared_transport_day = EVAL_SHARED_TRANSPORT_DAY_COST.get(transportation, 120)
    city_factor = EVAL_CITY_BUDGET_FACTORS.get(city_tier, 1.05)
    raw_total = (
        lodging_per_night * lodging_nights * room_count
        + per_person_day * party_total * travel_days
        + shared_transport_day * travel_days
    ) * city_factor
    return max(500, int(round(raw_total / 100.0) * 100))


def budget_target_range(amount: int, level: str, strictness: str) -> dict[str, Any]:
    if amount <= 0 or strictness == "none":
        return {"enabled": False, "min": 0, "max": 0}
    min_ratio, max_ratio = BUDGET_USAGE_RATIO_BY_LEVEL.get(level, BUDGET_USAGE_RATIO_BY_LEVEL["standard"])
    if strictness == "hard":
        max_ratio = min(max_ratio, 1.0)
    elif strictness == "soft":
        max_ratio = max(max_ratio, 1.05)
    return {
        "enabled": True,
        "min": int(round(amount * min_ratio / 100.0) * 100),
        "max": int(round(amount * max_ratio / 100.0) * 100),
    }


def classify(value: int, low: int, high: int) -> str:
    if value < low:
        return "below"
    if value > high:
        return "above"
    return "ok"


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(rows),
        "request_budget_status": status_summary(rows, "request_budget_status"),
        "teacher_budget_status": status_summary(rows, "teacher_budget_status"),
        "candidate_reach_amount": bool_summary(rows, "candidate_reach_amount"),
        "food_pois_zero": sum(1 for row in rows if int(row.get("food_pois") or 0) == 0),
        "by_budget_level": {
            level: summarize_slice(items)
            for level, items in sorted(group_by(rows, "budget_level").items())
        },
        "by_budget_level_strictness": {
            key: summarize_slice(items)
            for key, items in sorted(group_by(rows, lambda row: f"{row['budget_level']}/{row['strictness']}").items())
        },
    }


def summarize_slice(rows: list[dict[str, Any]]) -> dict[str, Any]:
    amounts = [int(row["amount"]) for row in rows]
    teacher = [int(row["teacher_budget_total"]) for row in rows]
    ratios = [float(row["candidate_high_ratio"]) for row in rows]
    return {
        "count": len(rows),
        "amount_p50": int(statistics.median(amounts)) if amounts else 0,
        "teacher_total_p50": int(statistics.median(teacher)) if teacher else 0,
        "request_budget_status": status_summary(rows, "request_budget_status"),
        "teacher_budget_status": status_summary(rows, "teacher_budget_status"),
        "candidate_high_ratio_p50": round(statistics.median(ratios), 3) if ratios else 0,
        "food_pois_zero": sum(1 for row in rows if int(row.get("food_pois") or 0) == 0),
    }


def status_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    counts = Counter(str(row.get(key) or "unknown") for row in rows)
    total = len(rows)
    return {
        name: {
            "count": count,
            "rate": round(count / total, 4) if total else 0,
        }
        for name, count in sorted(counts.items())
    }


def bool_summary(rows: list[dict[str, Any]], key: str) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for row in rows if bool(row.get(key)))
    return {
        "pass": passed,
        "total": total,
        "rate": round(passed / total, 4) if total else 0,
    }


def group_by(rows: list[dict[str, Any]], key: str | Any) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_key = key(row) if callable(key) else row.get(key)
        groups[str(group_key)].append(row)
    return groups


def pct(item: dict[str, Any], name: str = "ok") -> str:
    value = item.get(name, {}).get("rate", 0)
    count = item.get(name, {}).get("count", 0)
    return f"{value * 100:.1f}% ({count})"


def render_report(summary: dict[str, Any], rows: list[dict[str, Any]], records_path: Path, rows_path: Path) -> str:
    lines = [
        "# SFT 预算贴合审计",
        "",
        f"- records: `{records_path}`",
        f"- audit_rows: `{rows_path}`",
        f"- 样本数：{summary['total']}",
        "",
        "## 总览",
        "",
        "| 项 | 结果 |",
        "|---|---:|",
        f"| 请求预算落在当前分档范围 | {pct(summary['request_budget_status'])} |",
        f"| teacher budget 落在请求目标区间 | {pct(summary['teacher_budget_status'])} |",
        f"| 候选池高配可达请求预算 | {summary['candidate_reach_amount']['rate'] * 100:.1f}% ({summary['candidate_reach_amount']['pass']}/{summary['candidate_reach_amount']['total']}) |",
        f"| food_pois=0 | {summary['food_pois_zero']} |",
        "",
        "## 按预算档位",
        "",
        "| 档位 | n | amount p50 | teacher p50 | 请求预算OK | teacher预算OK | 候选可达p50 | food_pois=0 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for level, item in summary["by_budget_level"].items():
        lines.append(
            f"| {level} | {item['count']} | {item['amount_p50']} | {item['teacher_total_p50']} | "
            f"{pct(item['request_budget_status'])} | {pct(item['teacher_budget_status'])} | "
            f"{item['candidate_high_ratio_p50']:.2f} | {item['food_pois_zero']} |"
        )

    lines.extend([
        "",
        "## 按档位和约束",
        "",
        "| 分组 | n | amount p50 | teacher p50 | 请求预算OK | teacher预算OK | 候选可达p50 | food_pois=0 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for key, item in summary["by_budget_level_strictness"].items():
        lines.append(
            f"| {key} | {item['count']} | {item['amount_p50']} | {item['teacher_total_p50']} | "
            f"{pct(item['request_budget_status'])} | {pct(item['teacher_budget_status'])} | "
            f"{item['candidate_high_ratio_p50']:.2f} | {item['food_pois_zero']} |"
        )

    weak = sorted(
        rows,
        key=lambda row: (
            row["request_budget_status"] == "ok",
            row["teacher_budget_status"] == "ok",
            -abs(row["amount"] - row["recommended_mid"]),
        ),
    )[:30]
    lines.extend([
        "",
        "## 优先复查样本",
        "",
        "| record_id | level | strict | amount | recommended | teacher_total | request_status | teacher_status | high_ratio | food |",
        "|---|---|---|---:|---:|---:|---|---|---:|---:|",
    ])
    for row in weak:
        lines.append(
            f"| {row['record_id']} | {row['budget_level']} | {row['strictness']} | {row['amount']} | "
            f"{row['recommended_min']}-{row['recommended_max']} | {row['teacher_budget_total']} | "
            f"{row['request_budget_status']} | {row['teacher_budget_status']} | "
            f"{row['candidate_high_ratio']:.2f} | {row['food_pois']} |"
        )

    lines.extend([
        "",
        "## 解释",
        "",
        "- `请求预算OK`：用户预算金额是否落在当前预算口径按人数、天数、住宿、城市推导出的推荐区间内。",
        "- `teacher预算OK`：SFT teacher 的 `trip_plan.budget.total` 是否落在该请求的 `budget_fit_policy` 目标区间内。",
        "- `候选可达p50`：当前候选池粗估高配预算 / 用户预算；低于 1 表示候选供给可能不足。",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
