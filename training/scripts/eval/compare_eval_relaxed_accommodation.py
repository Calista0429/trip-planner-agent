"""忽略 day.accommodation=null 后对比两个评估结果。

用途:

  .venv-training-py311/bin/python3 training/scripts/eval/compare_eval_relaxed_accommodation.py

这个脚本不会修改原始 generations.jsonl。它只在评估时把模型输出里的
days[*].accommodation 为 null 或缺失的情况临时补成请求里的住宿类型，
用于回答一个很具体的问题:

  如果先不计 accommodation=null 这个 schema 小坑，base 和 SFT 谁更好？
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from eval_rule_metrics import evaluate_output, summarize_results
from eval_utils import DEFAULT_EVAL_OUTPUT_DIR, DEFAULT_EVAL_RECORDS, load_records_by_id, read_jsonl, write_json
from app.planner.output import extract_json_object


def load_latest_generations(path: Path) -> dict[str, dict[str, Any]]:
    """读取 generations.jsonl，同一个 record_id 只保留最后一次生成。"""
    generations = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if record_id:
            generations[record_id] = row
    return generations


def repair_accommodation(data: dict[str, Any], request: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """临时修复 days[*].accommodation 为 null/缺失的问题。"""
    repaired = copy.deepcopy(data)
    days = repaired.get("days")
    if not isinstance(days, list):
        return repaired, 0

    fallback = str(request.get("accommodation") or "住宿类型未指定")
    count = 0
    for day in days:
        if not isinstance(day, dict):
            continue
        if "accommodation" not in day or day.get("accommodation") is None:
            day["accommodation"] = fallback
            count += 1
    return repaired, count


def relaxed_generation(record: dict[str, Any], generation: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """把 generation 转成修复后的临时 generation。"""
    if not generation.get("ok"):
        return generation, 0

    try:
        data = extract_json_object(generation.get("output", ""))
    except Exception:  # noqa: BLE001
        return generation, 0

    repaired, repaired_count = repair_accommodation(data, record.get("request") or {})
    if repaired_count <= 0:
        return generation, 0

    patched = dict(generation)
    patched["output"] = json.dumps(repaired, ensure_ascii=False)
    patched["output_chars"] = len(patched["output"])
    patched["accommodation_relaxed"] = True
    patched["accommodation_repaired_count"] = repaired_count
    return patched, repaired_count


def evaluate_model(records_by_id: dict[str, dict[str, Any]], generations_path: Path) -> dict[str, Any]:
    """评估单个模型输出。"""
    generations = load_latest_generations(generations_path)
    results = []
    repaired_records = 0
    repaired_days = 0

    for record_id, record in records_by_id.items():
        generation = generations.get(record_id)
        if generation is None:
            generation = {
                "record_id": record_id,
                "ok": False,
                "output": "",
                "error": "missing generation",
                "latency_seconds": None,
                "output_chars": 0,
            }

        patched_generation, repaired_count = relaxed_generation(record, generation)
        result = evaluate_output(record, patched_generation)
        result["accommodation_repaired_count"] = repaired_count
        if repaired_count:
            repaired_records += 1
            repaired_days += repaired_count
        results.append(result)

    summary = summarize_results(results)
    total = len(results)
    summary["relaxed_accommodation"] = {
        "enabled": True,
        "repaired_records": repaired_records,
        "repaired_days": repaired_days,
    }
    summary["end_to_end"] = build_end_to_end_summary(results, total)
    return {
        "generations_path": str(generations_path),
        "summary": summary,
        "results": results,
    }


def build_end_to_end_summary(results: list[dict[str, Any]], total: int) -> dict[str, Any]:
    """按 eval 总样本数统计端到端指标，避免 schema 失败样本被分母跳过。"""
    metric_keys = [
        "json_extract_ok",
        "schema_ok",
        "hard_pass",
        "weather_match",
        "attraction_count_ok",
        "middle_hotel_ok",
        "invalid_hotel_name_ok",
        "budget_consistent",
        "budget_arithmetic_consistent",
        "budget_within_user_budget",
        "budget_level_aligned",
        "budget_preference_aligned",
    ]
    out: dict[str, Any] = {
        "call_ok": rate_row(sum(1 for row in results if row.get("call_ok")), total),
    }
    for key in metric_keys:
        out[key] = rate_row(sum(1 for row in results if row.get("metrics", {}).get(key) is True), total)
    return out


def rate_row(pass_count: int, total: int) -> dict[str, Any]:
    """生成 pass/total/rate 三元组。"""
    return {
        "pass": pass_count,
        "total": total,
        "rate": round(pass_count / total, 4) if total else 0.0,
    }


def metric_text(item: dict[str, Any]) -> str:
    """格式化百分比。"""
    return f"{item['pass']}/{item['total']} ({item['rate']:.2%})"


def write_markdown(path: Path, report: dict[str, Any], left_name: str, right_name: str) -> None:
    """写对比 Markdown。"""
    left = report["models"][left_name]["summary"]
    right = report["models"][right_name]["summary"]

    lines = [
        "# Base vs SFT Relaxed Accommodation Comparison\n\n",
        "本报告在评估时临时修复 `days[*].accommodation = null/缺失`，用于观察去掉该 schema 小坑后两个模型的差异。\n\n",
        "## End-to-End Metrics\n\n",
        "| Metric | " + left_name + " | " + right_name + " |\n",
        "| --- | ---: | ---: |\n",
    ]
    for key in [
        "call_ok",
        "json_extract_ok",
        "schema_ok",
        "hard_pass",
        "weather_match",
        "attraction_count_ok",
        "middle_hotel_ok",
        "invalid_hotel_name_ok",
        "budget_consistent",
        "budget_arithmetic_consistent",
        "budget_within_user_budget",
        "budget_level_aligned",
        "budget_preference_aligned",
    ]:
        lines.append(f"| {key} | {metric_text(left['end_to_end'][key])} | {metric_text(right['end_to_end'][key])} |\n")

    lines.extend(
        [
            "\n## Relaxed Repair Counts\n\n",
            "| Model | Repaired Records | Repaired Days |\n",
            "| --- | ---: | ---: |\n",
            f"| {left_name} | {left['relaxed_accommodation']['repaired_records']} | {left['relaxed_accommodation']['repaired_days']} |\n",
            f"| {right_name} | {right['relaxed_accommodation']['repaired_records']} | {right['relaxed_accommodation']['repaired_days']} |\n",
            "\n## Conditional Metrics From Existing Summarizer\n\n",
            "这些指标沿用原规则评估汇总，部分分母只覆盖 schema 通过样本。\n\n",
            "```json\n",
            json.dumps(
                {
                    left_name: {
                        "boolean_metrics": left.get("boolean_metrics", {}),
                        "numeric_metrics": left.get("numeric_metrics", {}),
                        "failure_stages": left.get("failure_stages", {}),
                        "error_types": left.get("error_types", {}),
                        "latency": left.get("latency", {}),
                        "output_chars": left.get("output_chars", {}),
                    },
                    right_name: {
                        "boolean_metrics": right.get("boolean_metrics", {}),
                        "numeric_metrics": right.get("numeric_metrics", {}),
                        "failure_stages": right.get("failure_stages", {}),
                        "error_types": right.get("error_types", {}),
                        "latency": right.get("latency", {}),
                        "output_chars": right.get("output_chars", {}),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            "\n```\n",
        ]
    )
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="忽略 accommodation=null 后对比两个模型评估结果。")
    parser.add_argument("--records", type=Path, default=DEFAULT_EVAL_RECORDS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_EVAL_OUTPUT_DIR)
    parser.add_argument("--left-name", default="base_qwen25_7b")
    parser.add_argument("--right-name", default="sft_legacy_clean")
    parser.add_argument("--left-generations", type=Path, default=None)
    parser.add_argument("--right-generations", type=Path, default=None)
    parser.add_argument("--report-name", default="base_vs_sft_relaxed_accommodation")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records_by_id = load_records_by_id(args.records)
    comparison_dir = args.output_dir / "comparison"
    comparison_dir.mkdir(parents=True, exist_ok=True)

    left_generations = args.left_generations or args.output_dir / args.left_name / "generations.jsonl"
    right_generations = args.right_generations or args.output_dir / args.right_name / "generations.jsonl"

    report = {
        "records": str(args.records),
        "left_name": args.left_name,
        "right_name": args.right_name,
        "models": {
            args.left_name: evaluate_model(records_by_id, left_generations),
            args.right_name: evaluate_model(records_by_id, right_generations),
        },
    }

    json_path = comparison_dir / f"{args.report_name}.json"
    md_path = comparison_dir / f"{args.report_name}.md"
    write_json(json_path, report)
    write_markdown(md_path, report, args.left_name, args.right_name)
    print(f"relaxed comparison json: {json_path}")
    print(f"relaxed comparison md: {md_path}")


if __name__ == "__main__":
    main()
