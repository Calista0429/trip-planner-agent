"""把 SFT 预算审计行切成可用、可修和淘汰名单。

输入来自显式传入的 audit_sft_budget_fit.py 生成的 audit_rows.jsonl。本脚本不修改原始
records.jsonl，只写审计派生产物，便于后续人工抽查或重建训练集。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


CATEGORY_LABELS = {
    "usable_budget_clean": "预算主集可用",
    "usable_budget_candidate_tight": "预算可用但候选偏紧",
    "repair_request_rebudget": "需重标请求预算",
    "repair_teacher_regen": "需重生成 teacher",
    "nonbudget_only": "仅适合非预算 SFT",
    "drop_or_full_regen": "预算训练淘汰或整条重做",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="切分 SFT 预算可用性")
    parser.add_argument("--audit-rows", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = read_jsonl(args.audit_rows)
    classified = [classify_row(row) for row in rows]
    summary = build_summary(classified)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.output_dir / "record_classification.jsonl", classified)
    write_csv(args.output_dir / "record_classification.csv", classified)
    write_json(args.output_dir / "summary.json", summary)
    write_id_lists(args.output_dir, classified)
    (args.output_dir / "sft_budget_usability_audit.md").write_text(
        render_report(summary, classified, args.audit_rows),
        encoding="utf-8",
    )

    print(f"audit_rows={args.audit_rows}")
    print(f"output_dir={args.output_dir}")
    print(f"report={args.output_dir / 'sft_budget_usability_audit.md'}")
    print(f"summary={args.output_dir / 'summary.json'}")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "record_id",
        "category",
        "label",
        "decision",
        "reason",
        "city",
        "budget_level",
        "strictness",
        "amount",
        "recommended_min",
        "recommended_max",
        "teacher_budget_total",
        "target_min",
        "target_max",
        "request_budget_status",
        "teacher_budget_status",
        "candidate_high_ratio",
        "candidate_reach_amount",
        "food_pois",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_id_lists(output_dir: Path, rows: list[dict[str, Any]]) -> None:
    groups: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        groups[str(row["category"])].append(str(row["record_id"]))
    for category in CATEGORY_LABELS:
        ids = sorted(groups.get(category, []))
        (output_dir / f"{category}_ids.txt").write_text(
            "".join(f"{record_id}\n" for record_id in ids),
            encoding="utf-8",
        )


def classify_row(row: dict[str, Any]) -> dict[str, Any]:
    request_ok = row["request_budget_status"] == "ok"
    teacher_ok = row["teacher_budget_status"] == "ok"
    no_budget_policy = row["teacher_budget_status"] == "no_budget_policy"
    candidate_ok = bool(row["candidate_reach_amount"])

    if request_ok and teacher_ok and candidate_ok:
        category = "usable_budget_clean"
        decision = "use"
        reason = "请求预算符合当前分档，teacher 预算在目标区间，候选池可支撑预算。"
    elif request_ok and teacher_ok:
        category = "usable_budget_candidate_tight"
        decision = "use_with_caution"
        reason = "请求和 teacher 预算都合格，但候选池高配估算低于用户预算，不适合训练用满预算。"
    elif no_budget_policy:
        category = "nonbudget_only"
        decision = "nonbudget_only"
        reason = "strictness=none，无预算目标区间；可保留作 schema/grounding，预算训练不使用。"
    elif request_ok:
        category = "repair_teacher_regen"
        decision = "repair"
        reason = "请求预算符合当前分档，但 teacher 预算低于目标区间，需要重生成 teacher。"
    elif teacher_ok:
        category = "repair_request_rebudget"
        decision = "repair"
        reason = "teacher 预算能贴合原请求目标，但请求金额不符合当前分档，需要重标请求预算/自由文本。"
    else:
        category = "drop_or_full_regen"
        decision = "drop_or_regenerate"
        reason = "请求预算和 teacher 预算至少两侧不匹配，预算训练建议淘汰或整条重做。"

    return {
        **row,
        "category": category,
        "label": CATEGORY_LABELS[category],
        "decision": decision,
        "reason": reason,
    }


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    category_counts = Counter(str(row["category"]) for row in rows)
    decision_counts = Counter(str(row["decision"]) for row in rows)
    by_level = summarize_groups(rows, "budget_level")
    by_level_strictness = summarize_groups(
        rows,
        lambda row: f"{row['budget_level']}/{row['strictness']}",
    )
    return {
        "total": total,
        "categories": {
            category: {
                "label": CATEGORY_LABELS[category],
                "count": category_counts.get(category, 0),
                "rate": round(category_counts.get(category, 0) / total, 4) if total else 0,
            }
            for category in CATEGORY_LABELS
        },
        "decisions": {
            name: {
                "count": count,
                "rate": round(count / total, 4) if total else 0,
            }
            for name, count in sorted(decision_counts.items())
        },
        "by_budget_level": by_level,
        "by_budget_level_strictness": by_level_strictness,
        "request_budget_status": status_summary(rows, "request_budget_status"),
        "teacher_budget_status": status_summary(rows, "teacher_budget_status"),
    }


def summarize_groups(rows: list[dict[str, Any]], key: str | Any) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        group_key = key(row) if callable(key) else row.get(key)
        groups[str(group_key)].append(row)
    return {
        group_key: {
            "count": len(items),
            "categories": {
                category: {
                    "count": count,
                    "rate": round(count / len(items), 4) if items else 0,
                }
                for category, count in sorted(Counter(item["category"] for item in items).items())
            },
        }
        for group_key, items in sorted(groups.items())
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


def rate(item: dict[str, Any]) -> str:
    return f"{item['rate'] * 100:.1f}% ({item['count']})"


def render_report(
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    audit_rows_path: Path,
) -> str:
    lines = [
        "# SFT 预算可用性审计",
        "",
        f"- audit_rows: `{audit_rows_path}`",
        f"- 样本数：{summary['total']}",
        "",
        "## 结论总览",
        "",
        "| 类别 | 含义 | 数量 | 建议 |",
        "|---|---|---:|---|",
    ]
    advice = {
        "usable_budget_clean": "直接进入预算主训练子集。",
        "usable_budget_candidate_tight": "可进预算控制子集，不建议用于训练“用足预算/高品质”。",
        "repair_request_rebudget": "重标 amount/free_text/budget_fit_policy 后再考虑。",
        "repair_teacher_regen": "保留请求和上下文，重生成 teacher。",
        "nonbudget_only": "只做非预算 schema/grounding 训练。",
        "drop_or_full_regen": "预算训练淘汰；需要时整条重做。",
    }
    for category, item in summary["categories"].items():
        lines.append(
            f"| {category} | {item['label']} | {rate(item)} | {advice[category]} |"
        )

    lines.extend([
        "",
        "## 按预算档位",
        "",
        "| 档位 | n | 主集可用 | 候选偏紧可用 | 需重标请求 | 需重生成teacher | 非预算 | 淘汰/重做 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for level, item in summary["by_budget_level"].items():
        categories = item["categories"]
        lines.append(
            f"| {level} | {item['count']} | "
            f"{category_count(categories, 'usable_budget_clean')} | "
            f"{category_count(categories, 'usable_budget_candidate_tight')} | "
            f"{category_count(categories, 'repair_request_rebudget')} | "
            f"{category_count(categories, 'repair_teacher_regen')} | "
            f"{category_count(categories, 'nonbudget_only')} | "
            f"{category_count(categories, 'drop_or_full_regen')} |"
        )

    lines.extend([
        "",
        "## 按档位和约束",
        "",
        "| 分组 | n | 主集可用 | 候选偏紧可用 | 需重标请求 | 需重生成teacher | 非预算 | 淘汰/重做 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for group, item in summary["by_budget_level_strictness"].items():
        categories = item["categories"]
        lines.append(
            f"| {group} | {item['count']} | "
            f"{category_count(categories, 'usable_budget_clean')} | "
            f"{category_count(categories, 'usable_budget_candidate_tight')} | "
            f"{category_count(categories, 'repair_request_rebudget')} | "
            f"{category_count(categories, 'repair_teacher_regen')} | "
            f"{category_count(categories, 'nonbudget_only')} | "
            f"{category_count(categories, 'drop_or_full_regen')} |"
        )

    lines.extend([
        "",
        "## 抽查优先级",
        "",
        "### 预算主集可用样本示例",
        "",
        "| record_id | city | level | strict | amount | recommended | teacher | high_ratio |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ])
    for row in [row for row in rows if row["category"] == "usable_budget_clean"][:20]:
        lines.append(sample_row(row))

    lines.extend([
        "",
        "### 预算训练优先淘汰/整条重做示例",
        "",
        "| record_id | city | level | strict | amount | recommended | teacher | high_ratio |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ])
    weak = sorted(
        [row for row in rows if row["category"] == "drop_or_full_regen"],
        key=lambda row: (
            row["request_budget_status"] == "ok",
            -abs(int(row["amount"]) - int(row["recommended_mid"])),
        ),
    )
    for row in weak[:20]:
        lines.append(sample_row(row))

    lines.extend([
        "",
        "## 文件",
        "",
        "- `record_classification.jsonl`：每条样本的分类和原因。",
        "- `record_classification.csv`：便于表格筛选的同内容 CSV。",
        "- `*_ids.txt`：按分类输出的 record_id 名单。",
        "",
        "## 口径",
        "",
        "- `预算主集可用`：请求预算符合当前分档，teacher budget 落在目标区间，候选池高配预算可达请求金额。",
        "- `预算可用但候选偏紧`：请求和 teacher 都合格，但候选池高配估算低于请求金额；适合预算控制，不适合训练用满预算。",
        "- `需重标请求预算`：teacher 能贴合原目标，但 amount/free_text 和当前分档不一致。",
        "- `需重生成 teacher`：请求预算已经合理，但 teacher budget 明显偏低。",
        "",
    ])
    return "\n".join(lines)


def category_count(categories: dict[str, Any], category: str) -> str:
    item = categories.get(category, {"count": 0, "rate": 0})
    return f"{item['rate'] * 100:.1f}% ({item['count']})"


def sample_row(row: dict[str, Any]) -> str:
    return (
        f"| {row['record_id']} | {row['city']} | {row['budget_level']} | {row['strictness']} | "
        f"{row['amount']} | {row['recommended_min']}-{row['recommended_max']} | "
        f"{row['teacher_budget_total']} | {float(row['candidate_high_ratio']):.2f} |"
    )


if __name__ == "__main__":
    main()
