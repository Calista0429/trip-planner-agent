"""按 control_spec / 天气来源切片汇总评估结果。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval_utils import (
    DEFAULT_EVAL_OUTPUT_DIR,
    DEFAULT_EVAL_RECORDS,
    average,
    group_record_ids_by_slice,
    load_records_by_id,
    metric_rate,
    read_jsonl,
    write_json,
)


KEY_BOOLEAN_METRICS = [
    "hard_pass",
    "schema_ok",
    "weather_match",
    "attraction_count_ok",
    "middle_hotel_ok",
    "invalid_hotel_name_ok",
    "meal_complete",
]

KEY_NUMERIC_METRICS = [
    "attraction_grounding_rate",
    "hotel_grounding_rate",
]


def parse_model_report(value: str) -> tuple[str, Path]:
    """解析 label=path。"""
    if "=" not in value:
        path = Path(value)
        return path.parent.name, path
    label, path = value.split("=", 1)
    return label, Path(path)


def load_rule_results(path: Path) -> dict[str, dict[str, Any]]:
    """读取 rule_eval_report.json 的逐样本结果。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {row["record_id"]: row for row in data.get("results", [])}


def load_judge_scores(path: Path | None) -> dict[str, dict[str, Any]]:
    """读取 judge_scores.jsonl。"""
    if not path:
        return {}
    return {row["record_id"]: row for row in read_jsonl(path)}


def load_pairwise(path: Path | None) -> dict[str, dict[str, Any]]:
    """读取 pairwise jsonl。"""
    if not path:
        return {}
    return {row["record_id"]: row for row in read_jsonl(path)}


def summarize_slice(
    record_ids: set[str],
    rule_results: dict[str, dict[str, Any]],
    judge_scores: dict[str, dict[str, Any]],
    pairwise_rows: dict[str, dict[str, Any]],
    pairwise_label: str,
) -> dict[str, Any]:
    """汇总单个切片。"""
    rows = [rule_results[record_id] for record_id in record_ids if record_id in rule_results]
    summary: dict[str, Any] = {"count": len(rows)}
    for metric in KEY_BOOLEAN_METRICS:
        values = [row.get("metrics", {}).get(metric) for row in rows if metric in row.get("metrics", {})]
        summary[metric] = metric_rate(sum(1 for value in values if value), len(values)) if values else 0.0
    for metric in KEY_NUMERIC_METRICS:
        values = [row.get("metrics", {}).get(metric) for row in rows if metric in row.get("metrics", {})]
        summary[metric] = average([float(value) for value in values]) if values else 0.0

    judge_values = [
        row.get("scores", {}).get("overall_quality", 0)
        for record_id, row in judge_scores.items()
        if record_id in record_ids and row.get("ok")
    ]
    if judge_values:
        summary["judge_overall_quality"] = average([float(value) for value in judge_values])

    if pairwise_rows:
        wins = 0
        losses = 0
        ties = 0
        total = 0
        for record_id, row in pairwise_rows.items():
            if record_id not in record_ids:
                continue
            total += 1
            winner = row.get("winner")
            if winner == pairwise_label:
                wins += 1
            elif winner == "tie":
                ties += 1
            else:
                losses += 1
        if total:
            summary["pairwise_total"] = total
            summary["pairwise_win_rate"] = metric_rate(wins, total)
            summary["pairwise_tie_rate"] = metric_rate(ties, total)
            summary["pairwise_loss_rate"] = metric_rate(losses, total)
    return summary


def write_markdown(path: Path, report: dict[str, Any]) -> None:
    """写 Markdown。"""
    lines = ["# Slice Eval Report\n\n"]
    for model_name, model_report in report["models"].items():
        lines.append(f"## {model_name}\n\n")
        for slice_name, values in model_report["slices"].items():
            lines.append(f"### {slice_name}\n\n")
            lines.append("| Value | Count | Hard Pass | Weather | Attr Ground | Hotel Ground | Judge Overall | Pairwise Win |\n")
            lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |\n")
            for value, summary in sorted(values.items(), key=lambda item: str(item[0])):
                lines.append(
                    f"| {value} | {summary.get('count', 0)} | "
                    f"{summary.get('hard_pass', 0):.2%} | "
                    f"{summary.get('weather_match', 0):.2%} | "
                    f"{summary.get('attraction_grounding_rate', 0):.2%} | "
                    f"{summary.get('hotel_grounding_rate', 0):.2%} | "
                    f"{summary.get('judge_overall_quality', 0):.2f} | "
                    f"{summary.get('pairwise_win_rate', 0):.2%} |\n"
                )
            lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按切片汇总 rule/judge/pairwise 评估。")
    parser.add_argument("--records", type=Path, default=DEFAULT_EVAL_RECORDS)
    parser.add_argument("--model-report", action="append", required=True, help="格式: model=rule_eval_report.json")
    parser.add_argument("--judge", action="append", default=[], help="格式: model=judge_scores.jsonl")
    parser.add_argument("--pairwise", type=Path, default=None)
    parser.add_argument(
        "--pairwise-win-label",
        default="right",
        choices=["left", "right"],
        help="pairwise 中当前关注模型对应 left/right 哪一侧",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT_DIR / "comparison")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-md", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records_by_id = load_records_by_id(args.records)
    slice_groups = group_record_ids_by_slice(records_by_id)
    judge_by_model = {label: load_judge_scores(path) for label, path in (parse_model_report(item) for item in args.judge)}
    pairwise_rows = load_pairwise(args.pairwise)

    report = {
        "records": str(args.records),
        "models": {},
    }
    for item in args.model_report:
        model_name, path = parse_model_report(item)
        rule_results = load_rule_results(path)
        model_data = {"rule_report": str(path), "slices": {}}
        for slice_name, values in slice_groups.items():
            model_data["slices"][slice_name] = {
                value: summarize_slice(
                    record_ids,
                    rule_results,
                    judge_by_model.get(model_name, {}),
                    pairwise_rows,
                    args.pairwise_win_label,
                )
                for value, record_ids in values.items()
            }
        report["models"][model_name] = model_data

    output_json = args.output_json or (args.output_dir / "slice_report.json")
    output_md = args.output_md or (args.output_dir / "slice_report.md")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_json, report)
    write_markdown(output_md, report)
    print(f"slice json: {output_json}")
    print(f"slice md: {output_md}")


if __name__ == "__main__":
    main()
