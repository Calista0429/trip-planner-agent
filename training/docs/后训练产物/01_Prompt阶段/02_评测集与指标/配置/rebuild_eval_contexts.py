"""Rebuild frozen eval PlannerContext snapshots.

This keeps the request distribution and record_id stable, but recollects the
PlannerContext with the current backend retrieval stack, then rebuilds the
compact context and Planner prompt. Use it when POI retrieval, pricing hints,
weather alignment, or context policy changes and old frozen eval records should
move to the new backend behavior without resampling requests.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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

from shared.common import load_project_env, read_jsonl, write_json, write_jsonl  # noqa: E402
from build_eval_set import (  # noqa: E402
    summarize_records,
    tool_counts,
    weather_provider,
    write_request_row,
    write_summary_markdown,
)
from generate_sft_data import (  # noqa: E402
    PLANNER_AGENT_PROMPT,
    apply_budget_fit_policy,
    budget_context_gate_audit,
    build_planner_query,
    date_bucket,
    get_worker_context_builder,
)
from app.models.schemas import TripRequest  # noqa: E402
from app.planner.amap import set_amap_qps_limit  # noqa: E402


DEFAULT_SOURCE_LABEL = "260511_high_end_poi_context_rebuild"


def rebuild_one_record(
    record: dict[str, Any],
    args: argparse.Namespace,
    amap_api_key: str,
    rebuilt_at: str,
) -> dict[str, Any]:
    """Recollect context and rebuild prompt for one frozen eval record."""
    request = TripRequest(**(record.get("request") or {}))
    builder = get_worker_context_builder(amap_api_key, args.historical_weather_provider)

    started_at = time.perf_counter()
    planner_context = builder.collect(request)
    apply_budget_fit_policy(planner_context, request)
    budget_audit = budget_context_gate_audit(request, planner_context)
    compact_context = builder.compact_for_planner(planner_context)
    planner_query = build_planner_query(builder, request, planner_context)
    elapsed = time.perf_counter() - started_at

    compact_context_text = json.dumps(compact_context, ensure_ascii=False)
    raw_context_text = json.dumps(planner_context, ensure_ascii=False)

    rebuilt = dict(record)
    rebuilt["system_prompt"] = PLANNER_AGENT_PROMPT
    rebuilt["planner_query"] = planner_query
    rebuilt["compact_planner_context"] = compact_context
    rebuilt["planner_context"] = planner_context
    rebuilt["context_rebuilt_at"] = rebuilt_at
    rebuilt["context_rebuild_label"] = args.source_label
    rebuilt["context_rebuild_source_records"] = str(args.input_records)
    rebuilt["context_rebuild_source_record_created_at"] = record.get("created_at")

    metadata = dict(rebuilt.get("metadata") or {})
    metadata.update(
        {
            "elapsed_seconds": round(elapsed, 3),
            "prompt_chars": len(planner_query),
            "compact_context_chars": len(compact_context_text),
            "raw_context_chars": len(raw_context_text),
            "weather_provider": weather_provider(planner_context),
            "date_bucket": date_bucket(request.model_dump()),
            "tool_counts": tool_counts(planner_context),
            "tool_status": (planner_context.get("tool_snapshot") or {}).get("tool_status", {}),
            "eval_metrics_version": "current",
            "expected_output_schema": "TripPlan",
            "budget_context_audit": budget_audit,
            "context_rebuilt": True,
            "context_rebuilt_at": rebuilt_at,
            "context_rebuild_label": args.source_label,
            "context_rebuild_source_records": str(args.input_records),
            "context_rebuild_source_record_created_at": record.get("created_at"),
        }
    )
    rebuilt["metadata"] = metadata
    return rebuilt


def select_records(records: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    """Apply start/limit selection for smoke rebuilds."""
    selected = records[args.start :]
    if args.limit is not None:
        selected = selected[: args.limit]
    return selected


def existing_record_ids(path: Path) -> set[str]:
    """Read existing output ids for resume mode."""
    return {str(row.get("record_id") or "") for row in read_jsonl(path)}


def write_requests(path: Path, records: list[dict[str, Any]]) -> None:
    """Rewrite requests.jsonl to match rebuilt records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
    for record in records:
        write_request_row(path, record)


def summarize_budget_context(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize context budget reachability audits across rebuilt records."""
    audits = [
        (record.get("metadata") or {}).get("budget_context_audit") or {}
        for record in records
        if (record.get("metadata") or {}).get("budget_context_audit")
    ]
    ratios = [float(audit.get("high_budget_ratio") or 0) for audit in audits]
    by_level: dict[str, list[float]] = defaultdict(list)
    target_min_pass = Counter()
    target_mid_pass = Counter()
    for audit in audits:
        level = str(audit.get("budget_level") or "unknown")
        by_level[level].append(float(audit.get("high_budget_ratio") or 0))
        if audit.get("can_reach_target_min"):
            target_min_pass[level] += 1
        if audit.get("can_reach_target_mid"):
            target_mid_pass[level] += 1

    def ratio_stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"count": 0, "min": 0, "avg": 0, "max": 0}
        return {
            "count": len(values),
            "min": round(min(values), 3),
            "avg": round(sum(values) / len(values), 3),
            "max": round(max(values), 3),
        }

    by_level_summary = {}
    for level, values in sorted(by_level.items()):
        summary = ratio_stats(values)
        summary["can_reach_target_min"] = target_min_pass[level]
        summary["can_reach_target_mid"] = target_mid_pass[level]
        by_level_summary[level] = summary

    return {
        **ratio_stats(ratios),
        "can_reach_target_min": sum(1 for audit in audits if audit.get("can_reach_target_min")),
        "can_reach_target_mid": sum(1 for audit in audits if audit.get("can_reach_target_mid")),
        "by_budget_level": by_level_summary,
    }


def write_rebuild_notes(path: Path, records: list[dict[str, Any]], summary: dict[str, Any], args: argparse.Namespace) -> None:
    """Write a concise human-readable rebuild note."""
    budget_summary = summary.get("budget_context_gate") or {}
    lines = [
        "# Eval Context Rebuild",
        "",
        f"- source_records: `{args.input_records}`",
        f"- output_records: `{path.parent / 'records.jsonl'}`",
        f"- source_label: `{args.source_label}`",
        f"- records: {len(records)}",
        f"- high_budget_ratio avg: {budget_summary.get('avg', 0)}",
        f"- can_reach_target_min: {budget_summary.get('can_reach_target_min', 0)} / {budget_summary.get('count', 0)}",
        f"- can_reach_target_mid: {budget_summary.get('can_reach_target_mid', 0)} / {budget_summary.get('count', 0)}",
        "",
        "## By Budget Level",
        "",
        "| level | count | min | avg | max | target_min | target_mid |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for level, item in (budget_summary.get("by_budget_level") or {}).items():
        lines.append(
            "| "
            f"{level} | {item.get('count', 0)} | {item.get('min', 0)} | "
            f"{item.get('avg', 0)} | {item.get('max', 0)} | "
            f"{item.get('can_reach_target_min', 0)} | {item.get('can_reach_target_mid', 0)} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Requests and record_id values are preserved from the source records.",
            "- PlannerContext, compact PlannerContext, system prompt and planner_query are rebuilt with the current backend code.",
            "- Use these rebuilt records for future model generation and rule eval when comparing runs after retrieval changes.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def guard_output_path(args: argparse.Namespace) -> None:
    """Avoid accidental in-place overwrite of source records."""
    input_records = args.input_records.resolve()
    output_records = (args.output_dir / "records.jsonl").resolve()
    if input_records == output_records and not args.allow_in_place:
        raise ValueError(
            "output records path equals input records path; pass --allow-in-place "
            "only if you intentionally want to replace the source dataset"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild frozen eval PlannerContext snapshots.")
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--allow-in-place", action="store_true")
    parser.add_argument("--source-label", default=DEFAULT_SOURCE_LABEL)
    parser.add_argument("--amap-qps-limit", type=float, default=3)
    parser.add_argument(
        "--historical-weather-provider",
        choices=["open-meteo", "none"],
        default="open-meteo",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    guard_output_path(args)
    load_project_env()
    set_amap_qps_limit(args.amap_qps_limit)

    amap_api_key = os.getenv("AMAP_MAPS_API_KEY") or os.getenv("AMAP_API_KEY")
    if not amap_api_key:
        raise RuntimeError("Missing AMAP_MAPS_API_KEY or AMAP_API_KEY")

    source_records = read_jsonl(args.input_records)
    selected_records = select_records(source_records, args)
    records_path = args.output_dir / "records.jsonl"
    requests_path = args.output_dir / "requests.jsonl"
    errors_path = args.output_dir / "errors.jsonl"
    summary_json_path = args.output_dir / "summary.json"
    summary_md_path = args.output_dir / "评估集摘要.md"
    rebuild_notes_path = args.output_dir / "上下文重建说明.md"

    existing_ids = existing_record_ids(records_path) if args.resume else set()
    existing_rows = read_jsonl(records_path) if args.resume else []
    existing_by_id = {str(row.get("record_id") or ""): row for row in existing_rows}
    work_items = [
        record
        for record in selected_records
        if str(record.get("record_id") or "") not in existing_ids
    ]
    rebuilt_at = datetime.now(timezone.utc).isoformat()

    print(
        f"Rebuilding eval contexts: input={args.input_records}, output={args.output_dir}, "
        f"records={len(selected_records)}, pending={len(work_items)}, workers={args.workers}",
        flush=True,
    )

    rebuilt_by_id: dict[str, dict[str, Any]] = dict(existing_by_id)
    errors: list[dict[str, Any]] = []
    ok = 0
    failed = 0

    if args.workers <= 1:
        for progress_index, record in enumerate(work_items, start=1):
            record_id = str(record.get("record_id") or "")
            try:
                rebuilt = rebuild_one_record(record, args, amap_api_key, rebuilt_at)
                rebuilt_by_id[record_id] = rebuilt
                ok += 1
                print(f"progress: {progress_index}/{len(work_items)} ok={ok} failed={failed} last={record_id}", flush=True)
            except Exception as exc:  # noqa: BLE001
                failed += 1
                error = {
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "record_id": record_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                errors.append(error)
                print(f"progress: {progress_index}/{len(work_items)} ok={ok} failed={failed} error={record_id}: {exc}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            futures = {
                executor.submit(rebuild_one_record, record, args, amap_api_key, rebuilt_at): record
                for record in work_items
            }
            for progress_index, future in enumerate(as_completed(futures), start=1):
                source = futures[future]
                record_id = str(source.get("record_id") or "")
                try:
                    rebuilt = future.result()
                    rebuilt_by_id[record_id] = rebuilt
                    ok += 1
                    print(
                        f"progress: {progress_index}/{len(work_items)} ok={ok} failed={failed} last={record_id}",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    error = {
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "record_id": record_id,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                    errors.append(error)
                    print(f"progress: {progress_index}/{len(work_items)} ok={ok} failed={failed} error={record_id}: {exc}", flush=True)

    output_records = [
        rebuilt_by_id[str(record.get("record_id") or "")]
        for record in selected_records
        if str(record.get("record_id") or "") in rebuilt_by_id
    ]
    write_jsonl(records_path, output_records)
    write_requests(requests_path, output_records)
    write_jsonl(errors_path, errors)

    summary = summarize_records(output_records, errors)
    summary["context_rebuild"] = {
        "source_records": str(args.input_records),
        "source_label": args.source_label,
        "rebuilt_at": rebuilt_at,
        "selected_records": len(selected_records),
        "pending_records": len(work_items),
        "ok": ok,
        "failed": failed,
    }
    summary["budget_context_gate"] = summarize_budget_context(output_records)
    write_json(summary_json_path, summary)
    write_summary_markdown(summary_md_path, summary)
    write_rebuild_notes(rebuild_notes_path, output_records, summary, args)

    print(f"Done: ok={ok}, failed={failed}, output_records={len(output_records)}")
    print(f"records: {records_path}")
    print(f"requests: {requests_path}")
    print(f"errors: {errors_path}")
    print(f"summary: {summary_md_path}")
    print(f"notes: {rebuild_notes_path}")


if __name__ == "__main__":
    main()
