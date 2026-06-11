"""Generate readable LLM-judge reports for one eval run.

Outputs:
- baseline_strength_weakness_dashboard.md
- baseline_strength_weakness_dashboard.svg
- judge_top_bottom_readable_cases.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = ROOT / "training/outputs/eval"

SCORE_LABELS = [
    ("grounding_faithfulness", "工具忠实"),
    ("preference_satisfaction", "偏好满足"),
    ("coherence", "连贯性"),
    ("practicality", "可执行性"),
    ("overall_quality", "综合质量"),
    ("budget_reasonableness", "预算合理"),
]

RULE_METRICS = [
    ("json_extract_ok", "JSON可解析"),
    ("schema_ok", "Schema通过"),
    ("date_range_ok", "日期范围正确"),
    ("days_len_ok", "天数正确"),
    ("weather_match", "天气匹配"),
    ("hotel_budget_covers_nights", "酒店晚数覆盖"),
    ("attraction_count_ok", "景点数合规"),
    ("budget_preference_aligned", "预算档位对齐"),
    ("budget_arithmetic_consistent", "预算加总一致"),
    ("hard_pass", "Hard Pass"),
]

ISSUE_CATEGORIES = [
    ("偏好/负向约束", ["偏好", "需求", "约束", "避开", "避免", "违反", "未满足", "遗漏", "过敏", "不吃", "忌口", "排队", "商业化", "打卡"]),
    ("交通/路线/位置", ["路线", "动线", "交通", "跨区", "距离", "偏远", "顺路", "通勤", "步行", "移动", "位置", "返程"]),
    ("餐饮/美食", ["餐", "美食", "早餐", "午餐", "晚餐", "餐厅", "小吃", "菜", "饮食", "口味", "海鲜", "猪肉"]),
    ("酒店/住宿", ["酒店", "住宿", "民宿", "房", "入住", "换酒店", "位置偏", "低配"]),
    ("预算/费用", ["预算", "费用", "价格", "金额", "超出", "超支", "低于", "花费", "分项", "总价", "算术", "计算"]),
    ("工具/事实忠实", ["工具", "候选", "虚构", "编造", "不存在", "未使用", "grounding", "事实", "不在"]),
    ("天气/季节适配", ["天气", "雨", "高温", "低温", "室内", "户外", "季节", "防晒", "保暖"]),
]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def latest_by_id(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest = {}
    for row in rows:
        record_id = row.get("record_id")
        if record_id:
            latest[record_id] = row
    return latest


def extract_json_object(text: str) -> dict[str, Any] | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def block_bar(value: float, width: int = 20) -> str:
    value = max(0.0, min(1.0, value))
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


def pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:.2f}%"


def load_summary(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def bool_rate(rule_summary: dict[str, Any], key: str) -> float | None:
    metric = (rule_summary.get("summary") or {}).get("boolean_metrics", {}).get(key)
    if not metric:
        return None
    return metric.get("rate")


def issue_categories(issues: list[str]) -> list[str]:
    categories = []
    joined = "\n".join(str(item) for item in issues)
    for name, keywords in ISSUE_CATEGORIES:
        if any(keyword in joined for keyword in keywords):
            categories.append(name)
    if not categories and issues:
        categories.append("其他")
    return categories


def collect_issue_profile(judge_rows: list[dict[str, Any]]) -> tuple[Counter[str], dict[str, list[str]], int, int, int]:
    counter: Counter[str] = Counter()
    examples: dict[str, list[str]] = {}
    low_rows = 0
    issue_count = 0
    multi_hits = 0
    for row in judge_rows:
        if row.get("skipped"):
            continue
        scores = row.get("scores") or {}
        if float(scores.get("overall_quality") or 0) > 2:
            continue
        low_rows += 1
        issues = [str(item) for item in row.get("major_issues") or [] if str(item).strip()]
        issue_count += len(issues)
        for issue in issues:
            categories = issue_categories([issue])
            multi_hits += len(categories)
            for category in categories:
                counter[category] += 1
                examples.setdefault(category, [])
                if len(examples[category]) < 3:
                    examples[category].append(f"`{row.get('record_id')}` {issue}")
    return counter, examples, low_rows, issue_count, multi_hits


def render_dashboard(run_dir: Path, rule_report: dict[str, Any], judge_summary: dict[str, Any], judge_rows: list[dict[str, Any]]) -> str:
    scores_avg = judge_summary.get("scores_avg") or {}
    issue_counter, examples, low_rows, issue_count, multi_hits = collect_issue_profile(judge_rows)

    lines = [
        "# Planner No-Route Baseline 优势与不足图表",
        "",
        '<img src="baseline_strength_weakness_dashboard.svg" alt="Planner no-route baseline dashboard" width="100%" />',
        "",
        "## 一句话结论",
        "",
        "这一版 baseline 去掉了粗糙 `route_hints`，只把候选 POI 的区域、地址和坐标交给模型。结果显示：**硬协议更稳，软质量也略有提升**；短板仍集中在 **预算怎么花、交通/位置判断、餐饮落地、负向约束权衡**。因此 DPO 仍有价值，但不应再围绕 JSON/schema 做文章。",
        "",
        "## 规则硬指标通过率",
        "",
        "| 指标 | 通过率 | 图示 |",
        "| --- | ---: | --- |",
    ]
    for key, label in RULE_METRICS:
        rate = bool_rate(rule_report, key)
        lines.append(f"| {label} | {pct(rate)} | `{block_bar(rate or 0)}` |")

    lines.extend(
        [
            "",
            "## LLM Judge 分项均分（满分5）",
            "",
            f"Judge 覆盖率：{pct(judge_summary.get('judge_coverage'))}，judged={judge_summary.get('judged')} / total={judge_summary.get('total')}。",
            "",
            "| 维度 | 均分 | 折算百分比 | 图示 |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for key, label in SCORE_LABELS:
        score = float(scores_avg.get(key) or 0)
        ratio = score / 5
        lines.append(f"| {label} | {score:.4f} | {ratio * 100:.1f}% | `{block_bar(ratio)}` |")

    lines.extend(
        [
            "",
            "## 低分样本问题聚类",
            "",
            f"统计范围：`overall_quality <= 2` 的已 judge 样本；问题来源为强模型 `major_issues`，按关键词多标签计数。低分样本数：{low_rows}，问题条目数：{issue_count}，多标签命中：{multi_hits}。",
            "",
            "| 问题类别 | 命中次数 | 占多标签命中 |",
            "| --- | ---: | ---: |",
        ]
    )
    total_hits = sum(issue_counter.values()) or 1
    for category, count in issue_counter.most_common():
        lines.append(f"| {category} | {count} | {count / total_hits * 100:.1f}% |")

    lines.extend(["", "### 典型问题示例", ""])
    for category, rows in examples.items():
        lines.extend([f"#### {category}", ""])
        for row in rows:
            lines.append(f"- {row}")
        lines.append("")

    lines.extend(
        [
            "## 可作为下一步调参依据的表述",
            "",
            "- 去掉粗路线 hint 后，hard_pass、预算算术一致性、可执行性和综合质量均有提升，说明半成品工程信号会误导模型。",
            "- 当前 baseline 的硬协议能力已经足够进入 DPO；DPO 应优化合法计划之间的旅行质量排序。",
            "- 下一步重点看低分样本：交通/位置、餐饮、预算使用、负向约束，分别决定哪些该改 prompt/context/rule，哪些该进入 DPO pair。",
        ]
    )
    return "\n".join(lines) + "\n"


def render_svg(judge_summary: dict[str, Any], issue_counter: Counter[str]) -> str:
    scores = judge_summary.get("scores_avg") or {}
    score_items = [(label, float(scores.get(key) or 0)) for key, label in SCORE_LABELS]
    issue_items = issue_counter.most_common(7)

    width = 1200
    height = 760
    left_x = 70
    right_x = 650
    y0 = 120
    row_h = 58
    bar_w = 360
    max_issue = max([count for _, count in issue_items] or [1])

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="1200" height="760" fill="#f8fafc"/>',
        '<text x="60" y="56" font-size="30" font-family="Arial, sans-serif" font-weight="700" fill="#0f172a">Planner No-Route Baseline 问题画像</text>',
        '<text x="60" y="86" font-size="15" font-family="Arial, sans-serif" fill="#475569">LLM Judge scores and low-score issue clusters</text>',
        '<text x="70" y="116" font-size="20" font-family="Arial, sans-serif" font-weight="700" fill="#1e293b">Judge 分项均分 / 5</text>',
        '<text x="650" y="116" font-size="20" font-family="Arial, sans-serif" font-weight="700" fill="#1e293b">低分样本问题聚类</text>',
    ]

    for index, (label, score) in enumerate(score_items):
        y = y0 + 28 + index * row_h
        filled = int(bar_w * score / 5)
        parts.extend(
            [
                f'<text x="{left_x}" y="{y}" font-size="15" font-family="Arial, sans-serif" fill="#334155">{label}</text>',
                f'<rect x="{left_x + 110}" y="{y - 15}" width="{bar_w}" height="18" rx="4" fill="#e2e8f0"/>',
                f'<rect x="{left_x + 110}" y="{y - 15}" width="{filled}" height="18" rx="4" fill="#2563eb"/>',
                f'<text x="{left_x + 485}" y="{y}" font-size="15" font-family="Arial, sans-serif" fill="#0f172a">{score:.2f}</text>',
            ]
        )

    for index, (label, count) in enumerate(issue_items):
        y = y0 + 28 + index * row_h
        filled = int(bar_w * count / max_issue)
        parts.extend(
            [
                f'<text x="{right_x}" y="{y}" font-size="15" font-family="Arial, sans-serif" fill="#334155">{label}</text>',
                f'<rect x="{right_x + 125}" y="{y - 15}" width="{bar_w}" height="18" rx="4" fill="#e2e8f0"/>',
                f'<rect x="{right_x + 125}" y="{y - 15}" width="{filled}" height="18" rx="4" fill="#f97316"/>',
                f'<text x="{right_x + 500}" y="{y}" font-size="15" font-family="Arial, sans-serif" fill="#0f172a">{count}</text>',
            ]
        )

    parts.extend(
        [
            '<rect x="60" y="610" width="1080" height="90" rx="8" fill="#eff6ff" stroke="#bfdbfe"/>',
            '<text x="86" y="646" font-size="17" font-family="Arial, sans-serif" font-weight="700" fill="#1e3a8a">结论</text>',
            '<text x="86" y="674" font-size="15" font-family="Arial, sans-serif" fill="#1e40af">去掉粗 route_hints 后，规则 hard_pass 和多数 judge 软指标提升；DPO 应聚焦预算、动线、餐饮和约束权衡。</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts)


def request_text(record: dict[str, Any]) -> str:
    request = record.get("request") or {}
    control = record.get("control_spec") or {}
    profile = (record.get("planner_context") or {}).get("preference_profile") or {}
    lines = [
        f"城市/日期：{request.get('city')} | {request.get('start_date')} -> {request.get('end_date')} | {request.get('travel_days')} 天",
        f"同行人数：{request.get('party')}",
        f"交通/住宿：{request.get('transportation')} / {request.get('accommodation')}",
        f"预算约束：{request.get('budget_constraint')}",
        f"原始偏好：{' / '.join(request.get('preferences') or [])}",
        f"自由文本：{request.get('free_text_input') or '无'}",
        f"正向偏好：{' / '.join(profile.get('positive_preferences') or control.get('positive_preferences') or []) or '无'}",
        f"负向约束：{' / '.join(profile.get('negative_constraints') or control.get('negative_constraints') or []) or '无'}",
        f"饮食：想吃/饮食偏好={' / '.join(profile.get('diet_positive') or control.get('diet_positive') or []) or '无'}；避免={' / '.join(profile.get('diet_avoid') or control.get('diet_avoid') or []) or '无'}",
        f"人群约束：{profile.get('traveler_constraints') or control.get('traveler_constraints') or {}}",
        f"难度/压力类型：{control.get('difficulty')} / {control.get('stress_type')}",
    ]
    return "\n".join(lines)


def render_plan(output: str) -> str:
    plan = extract_json_object(output)
    if not plan:
        return (output or "")[:3000]

    budget = plan.get("budget") or {}
    weather_rows = []
    for row in plan.get("weather_info") or []:
        weather_rows.append(
            f"{row.get('date')} {row.get('day_weather')}/{row.get('night_weather')} "
            f"{row.get('day_temp')}/{row.get('night_temp')}"
        )

    lines = [
        f"城市/日期：{plan.get('city')} | {plan.get('start_date')} -> {plan.get('end_date')} | {len(plan.get('days') or [])} 天",
        (
            f"预算：总计={budget.get('total')}元，景点={budget.get('total_attractions')}元，"
            f"酒店={budget.get('total_hotels')}元，餐饮={budget.get('total_meals')}元，"
            f"交通={budget.get('total_transportation')}元"
        ),
        f"天气：{' / '.join(weather_rows)}",
        f"总体建议：{plan.get('overall_suggestions') or ''}",
        "",
    ]

    for day in plan.get("days") or []:
        lines.append(f"D{int(day.get('day_index') or 0) + 1} {day.get('date')}：{day.get('description')}")
        lines.append(f"交通：{day.get('transportation')} | accommodation={day.get('accommodation')}")
        hotel = day.get("hotel")
        if hotel:
            lines.append(
                f"住宿：{hotel.get('name')} | {hotel.get('estimated_cost')}元/晚 | "
                f"{hotel.get('type', '')} | {hotel.get('distance', '')} | {hotel.get('address', '')}"
            )
        else:
            lines.append("住宿：无")
        attractions = []
        for item in day.get("attractions") or []:
            attractions.append(
                f"{item.get('name')}({item.get('ticket_price')}元, {item.get('visit_duration')}分钟, {item.get('category', '')})"
            )
        lines.append(f"景点：{' / '.join(attractions) if attractions else '无'}")
        meals = []
        for meal in day.get("meals") or []:
            meals.append(f"{meal.get('type')}:{meal.get('name')}({meal.get('estimated_cost')}元)")
        lines.append(f"餐饮：{' / '.join(meals) if meals else '无'}")
        lines.append("")
    return "\n".join(lines).strip()


def render_judge(row: dict[str, Any]) -> str:
    scores = row.get("scores") or {}
    issues = row.get("major_issues") or []
    lines = [
        (
            "分数："
            f"综合={scores.get('overall_quality')} | 偏好={scores.get('preference_satisfaction')} | "
            f"可执行={scores.get('practicality')} | 工具忠实={scores.get('grounding_faithfulness')} | "
            f"预算={scores.get('budget_reasonableness')} | 连贯={scores.get('coherence')}"
        ),
        "主要问题：",
    ]
    lines.extend([f"- {issue}" for issue in issues] or ["- 无"])
    lines.append(f"评价：{row.get('rationale') or ''}")
    return "\n".join(lines)


def render_top_bottom(records: dict[str, dict[str, Any]], generations: dict[str, dict[str, Any]], judge_rows: list[dict[str, Any]]) -> str:
    valid = [row for row in judge_rows if row.get("ok") and not row.get("skipped")]
    valid.sort(key=lambda row: (float((row.get("scores") or {}).get("overall_quality") or 0), row.get("record_id") or ""))
    bottom = valid[:10]
    top = list(reversed(valid[-10:]))

    lines = [
        "# Top/Bottom 可读案例",
        "",
        "说明：按最新 judge 记录去重；模型输出已从 JSON 渲染为中文行程摘要，便于人工审查。",
        "",
    ]

    for title, rows in [("最高分 Top 10", top), ("最低分 Bottom 10", bottom)]:
        lines.extend([f"## {title}", ""])
        for index, row in enumerate(rows, start=1):
            record_id = row.get("record_id")
            record = records.get(record_id, {})
            generation = generations.get(record_id, {})
            lines.extend(
                [
                    f"### {index}. {record_id}",
                    "",
                    "#### 用户输入",
                    "",
                    "```text",
                    request_text(record),
                    "```",
                    "",
                    "#### 模型输出（可读版）",
                    "",
                    "```text",
                    render_plan(generation.get("output") or ""),
                    "```",
                    "",
                    "#### 强模型评分",
                    "",
                    "```text",
                    render_judge(row),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 LLM judge dashboard 和 Top/Bottom 可读案例")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--generations", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir: Path = args.run_dir

    records = latest_by_id(read_jsonl(args.records))
    generations = latest_by_id(read_jsonl(args.generations))
    judge_rows = list(latest_by_id(read_jsonl(run_dir / "judge_scores.jsonl")).values())
    judge_summary = load_summary(run_dir / "judge_summary.json")
    rule_report = load_summary(run_dir / "rule_eval_report.json")

    issue_counter, _, _, _, _ = collect_issue_profile(judge_rows)
    dashboard_md = render_dashboard(run_dir, rule_report, judge_summary, judge_rows)
    dashboard_svg = render_svg(judge_summary, issue_counter)
    top_bottom = render_top_bottom(records, generations, judge_rows)

    write_text(run_dir / "baseline_strength_weakness_dashboard.md", dashboard_md)
    write_text(run_dir / "baseline_strength_weakness_dashboard.svg", dashboard_svg)
    write_text(run_dir / "judge_top_bottom_readable_cases.md", top_bottom)

    print(f"dashboard: {run_dir / 'baseline_strength_weakness_dashboard.md'}")
    print(f"svg: {run_dir / 'baseline_strength_weakness_dashboard.svg'}")
    print(f"top/bottom: {run_dir / 'judge_top_bottom_readable_cases.md'}")


if __name__ == "__main__":
    main()
