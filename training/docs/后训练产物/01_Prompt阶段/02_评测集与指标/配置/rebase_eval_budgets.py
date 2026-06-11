"""按候选池可达性重标 frozen eval 的预算金额。

这个脚本不重新调用高德、Open-Meteo 或 Planner 模型，只使用已冻结的
PlannerContext 估算当前候选池能支撑的预算上限。如果用户预算金额超过
候选池可达上限，就把预算下调到可达金额，并刷新 request / compact
context / planner_query。
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
LEGACY_SCRIPTS_DIR = SCRIPTS_DIR / "legacy"
EVAL_SCRIPTS_DIR = Path(__file__).resolve().parent
AUDIT_SCRIPT_DIR = SCRIPTS_DIR / "planner" / "audit"
DATA_SCRIPT_DIR = SCRIPTS_DIR / "planner" / "data"
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path[:0] = [
    str(EVAL_SCRIPTS_DIR),
    str(AUDIT_SCRIPT_DIR),
    str(DATA_SCRIPT_DIR),
    str(SCRIPTS_DIR),
    str(LEGACY_SCRIPTS_DIR),
    str(BACKEND_DIR),
]

from audit_budget_utilization_contexts import audit_context  # noqa: E402
from build_eval_set import summarize_records, write_request_row, write_summary_markdown  # noqa: E402
from shared.common import read_jsonl, write_json  # noqa: E402
from app.agents.planner_query import build_planner_query  # noqa: E402
from app.agents.prompts import PLANNER_AGENT_PROMPT  # noqa: E402
from app.models.schemas import TripRequest  # noqa: E402
from app.planner.compact import compact_for_planner  # noqa: E402
from app.planner.policy import build_budget_fit_policy  # noqa: E402


class FrozenContextBuilder:
    """给 build_planner_query 提供线上同名压缩接口。"""

    def compact_for_planner(self, planner_context: dict[str, Any]) -> dict[str, Any]:
        return compact_for_planner(planner_context)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="重标 frozen eval 预算金额")
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--min-reach-ratio",
        type=float,
        default=1.0,
        help="候选池高配估算 / 用户预算 的最低目标；1.0 表示候选池至少能达到预算100%",
    )
    parser.add_argument("--downgrade-luxury", action="store_true", default=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.input_records)
    rebased = [rebase_record(record, args) for record in records]
    write_outputs(args.output_dir, rebased, args)
    print(f"预算重标完成: {len(rebased)} 条")
    print(f"records: {args.output_dir / 'records.jsonl'}")
    print(f"summary: {args.output_dir / '评估集摘要.md'}")


def rebase_record(record: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    request = copy.deepcopy(record.get("request") or {})
    planner_context = copy.deepcopy(record.get("planner_context") or {})
    before = audit_context(request, planner_context)

    budget = dict(request.get("budget_constraint") or {})
    old_amount = int(budget.get("amount") or 0)
    old_level = str(budget.get("budget_level") or "standard")
    high_total = float((before.get("estimated_high_budget") or {}).get("total") or 0)
    max_reachable_amount = max(500, int(math.floor((high_total / max(args.min_reach_ratio, 0.01)) / 100.0) * 100))
    new_amount = min(old_amount, max_reachable_amount) if old_amount > 0 else old_amount
    new_level = "premium" if args.downgrade_luxury and old_level == "luxury" else old_level

    changed = new_amount != old_amount or new_level != old_level
    if changed:
        budget["amount"] = new_amount
        budget["budget_level"] = new_level
        request["budget_constraint"] = budget
        request["free_text_input"] = replace_budget_amount_text(
            str(request.get("free_text_input") or ""),
            old_amount,
            new_amount,
        )

    control_spec = copy.deepcopy(record.get("control_spec") or {})
    control_spec["budget_amount"] = new_amount
    control_spec["budget_level"] = new_level
    if new_level != old_level:
        control_spec["budget_level_rebased_from"] = old_level
    control_spec["budget_rebase_policy"] = {
        "method": "cap_to_candidate_reachable_budget",
        "min_reach_ratio": args.min_reach_ratio,
        "old_amount": old_amount,
        "new_amount": new_amount,
        "candidate_high_total": int(high_total),
        "high_budget_ratio_before": before.get("high_budget_ratio"),
    }

    request_model = TripRequest(**request)
    sync_request_into_planner_context(planner_context, request_model.model_dump())
    planner_constraints = planner_context.setdefault("planner_constraints", {})
    planner_constraints["budget_fit_policy"] = build_budget_fit_policy(request_model)
    builder = FrozenContextBuilder()
    compact_context = builder.compact_for_planner(planner_context)
    planner_query = build_planner_query(builder, request_model, planner_context)

    refreshed = copy.deepcopy(record)
    refreshed["request"] = request_model.model_dump()
    refreshed["control_spec"] = control_spec
    refreshed["system_prompt"] = PLANNER_AGENT_PROMPT
    refreshed["planner_context"] = planner_context
    refreshed["compact_planner_context"] = compact_context
    refreshed["planner_query"] = planner_query
    refreshed["budget_rebased_at"] = datetime.now(timezone.utc).isoformat()

    after = audit_context(refreshed["request"], planner_context)
    metadata = dict(refreshed.get("metadata") or {})
    metadata.update(
        {
            "prompt_chars": len(planner_query),
            "compact_context_chars": len(json.dumps(compact_context, ensure_ascii=False)),
            "raw_context_chars": len(json.dumps(planner_context, ensure_ascii=False)),
            "budget_rebase": changed,
            "budget_rebase_min_reach_ratio": args.min_reach_ratio,
            "budget_high_ratio_before": before.get("high_budget_ratio"),
            "budget_high_ratio_after": after.get("high_budget_ratio"),
        }
    )
    refreshed["metadata"] = metadata
    return refreshed


def sync_request_into_planner_context(planner_context: dict[str, Any], request: dict[str, Any]) -> None:
    """同步 PlannerContext 里冗余保存的请求字段，避免 frozen prompt 残留旧预算。"""
    planner_context["request"] = {
        "city": request.get("city"),
        "start_date": request.get("start_date"),
        "end_date": request.get("end_date"),
        "travel_days": request.get("travel_days"),
        "transportation": request.get("transportation"),
        "accommodation": request.get("accommodation"),
        "preferences": request.get("preferences") or [],
        "free_text_input": request.get("free_text_input") or "",
    }
    planner_context["party"] = request.get("party") or {}
    planner_context["budget_constraint"] = request.get("budget_constraint") or {}


def replace_budget_amount_text(text: str, old_amount: int, new_amount: int) -> str:
    if old_amount > 0 and f"{old_amount}元" in text:
        return text.replace(f"{old_amount}元", f"{new_amount}元")
    return text


def write_outputs(output_dir: Path, records: list[dict[str, Any]], args: argparse.Namespace) -> None:
    records_path = output_dir / "records.jsonl"
    requests_path = output_dir / "requests.jsonl"
    errors_path = output_dir / "errors.jsonl"
    summary_json_path = output_dir / "summary.json"
    summary_md_path = output_dir / "评估集摘要.md"

    write_jsonl(records_path, records)
    requests_path.write_text("", encoding="utf-8")
    for record in records:
        write_request_row(requests_path, record)
    errors_path.write_text("", encoding="utf-8")

    summary = summarize_records(records, [])
    ratios = [
        float((record.get("metadata") or {}).get("budget_high_ratio_after") or 0)
        for record in records
    ]
    changed = sum(bool((record.get("metadata") or {}).get("budget_rebase")) for record in records)
    summary["budget_rebase"] = {
        "min_reach_ratio": args.min_reach_ratio,
        "changed": changed,
        "reach_budget_100": sum(ratio >= 1.0 for ratio in ratios),
        "reach_budget_100_rate": round(sum(ratio >= 1.0 for ratio in ratios) / len(ratios), 4)
        if ratios
        else 0,
    }
    write_json(summary_json_path, summary)
    write_summary_markdown(summary_md_path, summary)
    append_budget_rebase_summary(summary_md_path, summary["budget_rebase"])


def append_budget_rebase_summary(path: Path, item: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n## 预算重标\n\n")
        handle.write(f"- 重标样本数：{item['changed']}\n")
        handle.write(f"- 候选可达预算100%：{item['reach_budget_100']} 条\n")
        handle.write(f"- 候选可达预算100%比例：{item['reach_budget_100_rate'] * 100:.1f}%\n")
        handle.write(f"- 最低可达比例目标：{item['min_reach_ratio']}\n")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
