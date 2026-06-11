"""Merge multi-run generations with backend rerank logic."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval_utils import (
    DEFAULT_EVAL_RECORDS,
    append_jsonl,
    load_records_by_id,
    model_run_dir,
    read_jsonl,
    write_json,
)
from app.models.schemas import TripRequest, TripPlan
from app.planner.output import (
    enrich_trip_plan_poi_details,
    extract_json_object,
    validate_trip_plan_shape,
)
from app.planner.rerank import rerank_trip_plan_candidates


def parse_candidate_arg(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            f"--candidate 格式必须是 label=path，收到: {raw}"
        )
    label, path = raw.split("=", 1)
    label = label.strip()
    if not label:
        raise argparse.ArgumentTypeError(f"candidate label 不能为空: {raw}")
    return label, Path(path.strip())


def load_latest_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if record_id:
            rows[record_id] = row
    return rows


def parse_trip_plan_candidate(
    output: str,
    request: TripRequest,
    planner_context: dict[str, Any],
) -> TripPlan:
    data = extract_json_object(output)
    trip_plan = TripPlan(**data)
    if planner_context:
        enrich_trip_plan_poi_details(trip_plan, planner_context)
    validate_trip_plan_shape(trip_plan, request, planner_context)
    return trip_plan


def build_row_from_selected(
    *,
    model_name: str,
    record: dict[str, Any],
    candidate_label: str,
    candidate_row: dict[str, Any],
    selected_plan: TripPlan,
    rerank_meta: dict[str, Any],
) -> dict[str, Any]:
    output = json.dumps(selected_plan.model_dump(), ensure_ascii=False)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": model_name,
        "api_model": f"rerank:{candidate_label}",
        "record_id": record["record_id"],
        "request": record.get("request", {}),
        "control_spec": record.get("control_spec", {}),
        "prompt_chars": len(record.get("planner_query", "")),
        "max_tokens": candidate_row.get("max_tokens", 0),
        "ok": True,
        "output": output,
        "output_chars": len(output),
        "latency_seconds": candidate_row.get("latency_seconds"),
        "finish_reason": "rerank_selected",
        "rerank_meta": rerank_meta,
    }


def build_row_from_fallback(
    *,
    model_name: str,
    record: dict[str, Any],
    candidate_label: str,
    candidate_row: dict[str, Any] | None,
    reason: str,
) -> dict[str, Any]:
    if candidate_row is None:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_name": model_name,
            "api_model": f"rerank:{candidate_label}",
            "record_id": record["record_id"],
            "request": record.get("request", {}),
            "control_spec": record.get("control_spec", {}),
            "prompt_chars": len(record.get("planner_query", "")),
            "max_tokens": 0,
            "ok": False,
            "output": "",
            "output_chars": 0,
            "latency_seconds": 0.0,
            "error_type": "RerankNoCandidate",
            "error": reason,
            "finish_reason": "rerank_no_candidate",
            "rerank_meta": {"selected": "none", "reason": reason},
        }

    row = dict(candidate_row)
    row["timestamp"] = datetime.now(timezone.utc).isoformat()
    row["model_name"] = model_name
    row["api_model"] = f"rerank:{candidate_label}"
    row["request"] = record.get("request", {})
    row["control_spec"] = record.get("control_spec", {})
    row["prompt_chars"] = len(record.get("planner_query", ""))
    row["rerank_meta"] = {"selected": "fallback_raw_output", "reason": reason}
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 backend rerank 规则合并多路 generations。")
    parser.add_argument("--records", type=Path, default=DEFAULT_EVAL_RECORDS)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--candidate",
        action="append",
        type=parse_candidate_arg,
        required=True,
        help="候选 generations，格式 label=path，可重复传多次",
    )
    parser.add_argument("--output-file", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records_by_id = load_records_by_id(args.records)
    records = list(records_by_id.values())
    run_dir = model_run_dir(args.model_name, args.output_dir)
    output_file = args.output_file or (run_dir / "generations.jsonl")
    metadata_file = run_dir / "generation_config.json"

    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        output_file.unlink()

    candidate_labels: list[str] = []
    candidate_rows: list[dict[str, dict[str, Any]]] = []
    for label, path in args.candidate:
        candidate_labels.append(label)
        candidate_rows.append(load_latest_rows(path))

    write_json(
        metadata_file,
        {
            "model_name": args.model_name,
            "records": str(args.records),
            "total_records": len(records),
            "candidates": [
                {"label": label, "path": str(path)}
                for label, path in args.candidate
            ],
            "merge_mode": "backend_rerank",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    status_counter: Counter[str] = Counter()
    valid_counter = 0
    invalid_counter = 0

    for index, record in enumerate(records, start=1):
        record_id = record["record_id"]
        request = TripRequest(**(record.get("request") or {}))
        planner_context = (record.get("planner_context") or {})

        valid_candidates: list[tuple[int, TripPlan]] = []
        valid_candidate_meta: dict[int, tuple[str, dict[str, Any]]] = {}
        first_existing_row: tuple[str, dict[str, Any]] | None = None

        for attempt, (label, rows_by_id) in enumerate(zip(candidate_labels, candidate_rows), start=1):
            row = rows_by_id.get(record_id)
            if row is None:
                continue
            if first_existing_row is None:
                first_existing_row = (label, row)
            if not row.get("ok"):
                continue
            output = str(row.get("output") or "")
            if not output.strip():
                continue
            try:
                trip_plan = parse_trip_plan_candidate(output, request, planner_context)
            except Exception:  # noqa: BLE001
                invalid_counter += 1
                continue

            valid_counter += 1
            valid_candidates.append((attempt, trip_plan))
            valid_candidate_meta[attempt] = (label, row)

        if valid_candidates:
            ranked = rerank_trip_plan_candidates(valid_candidates, request, planner_context)
            best = ranked[0]
            best_label, best_row = valid_candidate_meta[best.attempt]
            rerank_meta = {
                "selected_attempt": best.attempt,
                "selected_label": best_label,
                "selected_score": best.score,
                "selected_metrics": best.metrics,
                "candidate_count": len(candidate_labels),
                "valid_candidate_count": len(valid_candidates),
                "ranked": [
                    {
                        "attempt": item.attempt,
                        "score": item.score,
                        "metrics": item.metrics,
                        "label": valid_candidate_meta[item.attempt][0],
                    }
                    for item in ranked
                ],
            }
            row = build_row_from_selected(
                model_name=args.model_name,
                record=record,
                candidate_label=best_label,
                candidate_row=best_row,
                selected_plan=best.trip_plan,
                rerank_meta=rerank_meta,
            )
            status_counter["rerank_selected"] += 1
        else:
            if first_existing_row is None:
                row = build_row_from_fallback(
                    model_name=args.model_name,
                    record=record,
                    candidate_label="none",
                    candidate_row=None,
                    reason="all_candidate_rows_missing",
                )
                status_counter["no_candidate_rows"] += 1
            else:
                label, candidate_row = first_existing_row
                row = build_row_from_fallback(
                    model_name=args.model_name,
                    record=record,
                    candidate_label=label,
                    candidate_row=candidate_row,
                    reason="no_valid_trip_plan_after_parse_validate",
                )
                status_counter["fallback_raw_output"] += 1

        append_jsonl(output_file, row)
        if index % 20 == 0 or index == len(records):
            print(
                f"progress {index}/{len(records)} "
                f"selected={status_counter['rerank_selected']} "
                f"fallback={status_counter['fallback_raw_output']} "
                f"missing={status_counter['no_candidate_rows']}",
                flush=True,
            )

    summary = {
        "records": len(records),
        "status_counter": dict(status_counter),
        "valid_candidates_seen": valid_counter,
        "invalid_candidates_seen": invalid_counter,
        "output_file": str(output_file),
    }
    write_json(run_dir / "rerank_merge_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
