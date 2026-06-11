"""刷新 frozen eval 记录中的 Planner prompt。

这个脚本不重新调用高德、Open-Meteo 或 Planner 模型，只使用已落盘的
request/planner_context 重新生成 system_prompt、compact_planner_context 和
planner_query。适合在 prompt 规则有小改动后，复用同一批工具快照跑 baseline。
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
LEGACY_SCRIPTS_DIR = SCRIPTS_DIR / "legacy"
EVAL_SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_SCRIPTS_DIR = SCRIPTS_DIR / "planner" / "data"
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path[:0] = [
    str(EVAL_SCRIPTS_DIR),
    str(DATA_SCRIPTS_DIR),
    str(SCRIPTS_DIR),
    str(LEGACY_SCRIPTS_DIR),
    str(BACKEND_DIR),
]

from shared.common import read_jsonl, write_json  # noqa: E402
from build_eval_set import summarize_records, write_request_row, write_summary_markdown  # noqa: E402
from app.agents.planner_query import build_planner_query  # noqa: E402
from app.agents.prompts import PLANNER_AGENT_PROMPT  # noqa: E402
from app.models.schemas import TripRequest  # noqa: E402
from app.planner.compact import compact_for_planner  # noqa: E402
from app.planner.policy import build_budget_fit_policy, build_route_policy  # noqa: E402


class FrozenContextBuilder:
    """给 build_planner_query 提供线上同名压缩接口。"""

    def compact_for_planner(self, planner_context: dict[str, Any]) -> dict[str, Any]:
        return compact_for_planner(planner_context)


def refresh_record(record: dict[str, Any]) -> dict[str, Any]:
    """刷新一条 frozen eval 记录中的 prompt 相关字段。"""
    request = TripRequest(**(record.get("request") or {}))
    planner_context = normalize_planner_context(record.get("planner_context") or {}, request)
    builder = FrozenContextBuilder()

    compact_context = builder.compact_for_planner(planner_context)
    planner_query = build_planner_query(builder, request, planner_context)
    compact_context_text = json.dumps(compact_context, ensure_ascii=False)
    raw_context_text = json.dumps(planner_context, ensure_ascii=False)

    refreshed = dict(record)
    refreshed["system_prompt"] = PLANNER_AGENT_PROMPT
    refreshed["planner_query"] = planner_query
    refreshed["compact_planner_context"] = compact_context
    refreshed["planner_context"] = planner_context
    refreshed["refreshed_at"] = datetime.now(timezone.utc).isoformat()
    refreshed["refresh_source_record"] = record.get("record_id")

    metadata = dict(refreshed.get("metadata") or {})
    metadata.update(
        {
            "prompt_chars": len(planner_query),
            "compact_context_chars": len(compact_context_text),
            "raw_context_chars": len(raw_context_text),
            "prompt_refresh": True,
            "prompt_refreshed_at": refreshed["refreshed_at"],
        }
    )
    tool_counts = dict(metadata.get("tool_counts") or {})
    tool_counts["route_hints"] = 0
    metadata["tool_counts"] = tool_counts
    refreshed["metadata"] = metadata
    return refreshed


def normalize_planner_context(planner_context: dict[str, Any], request: TripRequest) -> dict[str, Any]:
    """让旧 frozen records 对齐当前线上 PlannerContext 主线。"""
    context = copy.deepcopy(planner_context)
    context["route_policy"] = build_route_policy(request)

    snapshot = context.setdefault("tool_snapshot", {})
    snapshot["route_hints"] = []

    candidate_counts = dict(snapshot.get("candidate_counts") or {})
    candidate_counts["route_hints"] = 0
    snapshot["candidate_counts"] = candidate_counts

    tool_status = dict(snapshot.get("tool_status") or {})
    tool_status["routes"] = {
        "ok": True,
        "message": "disabled; planner uses poi address/district/location",
    }
    snapshot["tool_status"] = tool_status

    planner_constraints = context.setdefault("planner_constraints", {})
    planner_constraints["budget_fit_policy"] = build_budget_fit_policy(request)
    planner_constraints["route_policy"] = (
        "当前版本不提供路线hint；请根据候选POI的district、address和location"
        "自行安排顺路组合，避免明显跨区跳跃。"
    )
    return context


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """覆盖写 JSONL。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="刷新 frozen eval 的 Planner prompt")
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = [refresh_record(record) for record in read_jsonl(args.input_records)]

    output_dir: Path = args.output_dir
    records_path = output_dir / "records.jsonl"
    requests_path = output_dir / "requests.jsonl"
    summary_json_path = output_dir / "summary.json"
    summary_md_path = output_dir / "评估集摘要.md"

    write_jsonl(records_path, records)
    requests_path.parent.mkdir(parents=True, exist_ok=True)
    requests_path.write_text("", encoding="utf-8")
    for record in records:
        write_request_row(requests_path, record)

    summary = summarize_records(records, [])
    summary["source_records"] = str(args.input_records)
    summary["prompt_refresh"] = True
    write_json(summary_json_path, summary)
    write_summary_markdown(summary_md_path, summary)

    print(f"刷新完成: {len(records)} 条")
    print(f"records: {records_path}")
    print(f"summary: {summary_md_path}")


if __name__ == "__main__":
    main()
