#!/usr/bin/env python3
"""Prepare train-only PlannerSoft-oriented DPO context records.

This builds a stable prompt/context pool for the second RL/DPO stage.  It
reuses train-only planner records, excludes frozen eval requests, and creates a
fixed issue distribution around planner_soft_pass failure modes.
"""

from __future__ import annotations

import argparse
import copy
import json
import random
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = PROJECT_ROOT / "backend"
BESTOFN_DIR = PROJECT_ROOT / "training/scripts/planner/bestofn"
sys.path[:0] = [str(BACKEND_DIR), str(BESTOFN_DIR)]

from app.agents.planner_query import build_planner_query  # noqa: E402
from app.agents.prompts import PLANNER_AGENT_PROMPT  # noqa: E402
from app.models.schemas import TripRequest  # noqa: E402
from app.planner.compact import compact_for_planner  # noqa: E402
from app.planner.policy import build_budget_fit_policy, build_route_policy  # noqa: E402
import prepare_high_confidence_dpo_contexts as base  # noqa: E402


DEFAULT_QUOTAS = {
    "below_target_min": 680,
    "above_hard_user_budget": 680,
    "above_target_max": 300,
    "meal_diversity": 230,
    "attraction_diversity": 190,
    "hard_valid_stability": 190,
    "meal_scale_guardrail": 130,
}

LOCAL_CANDIDATE_SPECS = [
    {"label": "local_t02", "temperature": 0.2, "count": 3},
    {"label": "local_t07", "temperature": 0.7, "count": 3},
]


class FrozenContextBuilder:
    """Adapter for build_planner_query."""

    def compact_for_planner(self, planner_context: dict[str, Any]) -> dict[str, Any]:
        return compact_for_planner(planner_context)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def request(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("request") or {}


def control(row: dict[str, Any]) -> dict[str, Any]:
    return row.get("control_spec") or {}


def budget_level(row: dict[str, Any]) -> str:
    return base.budget_level(row)


def strictness(row: dict[str, Any]) -> str:
    return base.strictness(row)


def budget_amount(row: dict[str, Any]) -> int:
    return base.budget_amount(row)


def travel_days(row: dict[str, Any]) -> int:
    return base.travel_days(row)


def party_total(row: dict[str, Any]) -> int:
    return base.party_total(row)


def text_blob(row: dict[str, Any]) -> str:
    return base.text_blob(row)


def accommodation(row: dict[str, Any]) -> str:
    return str(request(row).get("accommodation") or "")


def budget_context_audit(row: dict[str, Any]) -> dict[str, Any]:
    return (row.get("metadata") or {}).get("budget_context_audit") or {}


def high_budget_ratio(row: dict[str, Any]) -> float:
    try:
        return float(budget_context_audit(row).get("high_budget_ratio") or 0)
    except (TypeError, ValueError):
        return 0.0


def can_reach_target_min(row: dict[str, Any]) -> bool:
    audit = budget_context_audit(row)
    if "can_reach_target_min" not in audit:
        return True
    return bool(audit.get("can_reach_target_min"))


def can_reach_target_mid(row: dict[str, Any]) -> bool:
    audit = budget_context_audit(row)
    if "can_reach_target_mid" not in audit:
        return True
    return bool(audit.get("can_reach_target_mid"))


def rich_budget_pressure(row: dict[str, Any]) -> bool:
    text = text_blob(row)
    return (
        party_total(row) >= 3
        or travel_days(row) >= 4
        or any(term in accommodation(row) for term in ("高端酒店", "舒适型酒店", "民宿"))
        or any(term in text for term in ("亲子", "老人", "主题乐园", "海滨度假", "打车", "高价", "商务"))
    )


def category_match(row: dict[str, Any], category: str) -> bool:
    level = budget_level(row)
    strict = strictness(row)
    amount = budget_amount(row)
    days = travel_days(row)
    text = text_blob(row)

    if category == "below_target_min":
        return (
            amount > 0
            and level in {"standard", "comfortable", "premium", "luxury"}
            and strict in {"soft", "hard"}
            and can_reach_target_min(row)
            and (can_reach_target_mid(row) or high_budget_ratio(row) >= 0.72 or any(term in text for term in ("用足", "高端", "美食")))
        )

    if category == "above_hard_user_budget":
        return amount > 0 and strict in {"soft", "hard"} and (
            rich_budget_pressure(row)
            or level in {"limited", "standard", "comfortable"}
            or days >= 3
        )

    if category == "above_target_max":
        return amount > 0 and strict in {"soft", "hard"} and rich_budget_pressure(row)

    if category == "meal_diversity":
        return base.dining_signal(row) and (days >= 3 or party_total(row) >= 2)

    if category == "attraction_diversity":
        return days >= 4 or any(term in text for term in ("第一次来", "历史文化", "城市漫步", "自然风光", "博物馆", "小众", "艺术"))

    if category == "hard_valid_stability":
        return amount > 0 and level != "unknown"

    if category == "meal_scale_guardrail":
        return level in {"premium", "luxury"} and base.dining_signal(row)

    raise KeyError(category)


def budget_text(level: str, amount: int, strict: str) -> str:
    level_zh = {
        "limited": "有限预算",
        "standard": "标准预算",
        "comfortable": "舒适预算",
        "premium": "高预算",
        "luxury": "豪华预算",
    }.get(level, level)
    strict_zh = {"hard": "硬预算，不能超过", "soft": "软预算，尽量贴近", "none": "无严格预算"}.get(strict, strict)
    return f"本轮预算约束以结构化 budget_constraint 为准：总预算{amount}元，{level_zh}，{strict_zh}。"


def rewritten_free_text(row: dict[str, Any], level: str, amount: int, strict: str) -> str:
    ctrl = control(row)
    positives = ctrl.get("positive_preferences") or request(row).get("preferences") or []
    negatives = ctrl.get("negative_constraints") or ctrl.get("avoid") or []
    parts = [budget_text(level, amount, strict)]
    if positives:
        parts.append("偏好：" + "、".join(str(item) for item in positives))
    if negatives:
        parts.append("尽量避开：" + "、".join(str(item) for item in negatives))
    diet = ctrl.get("diet")
    if diet and diet != "无":
        parts.append(f"饮食要求：{diet}")
    return "；".join(parts) + "。"


def transformed_budget(row: dict[str, Any], category: str) -> tuple[str, int, str]:
    level = budget_level(row)
    amount = budget_amount(row)
    strict = strictness(row)

    if category == "below_target_min":
        return level, amount, "soft"
    if category == "above_hard_user_budget":
        return level, amount, "hard"
    if category == "above_target_max":
        return level, amount, "soft"
    return level, amount, strict


def normalize_context(record: dict[str, Any]) -> dict[str, Any]:
    request_model = TripRequest(**(record.get("request") or {}))
    context = copy.deepcopy(record.get("planner_context") or {})
    request_dict = request_model.model_dump()

    context["request"] = {
        key: request_dict.get(key)
        for key in ("city", "start_date", "end_date", "travel_days", "transportation", "accommodation", "preferences", "free_text_input")
        if key in request_dict
    }
    context["party"] = request_dict.get("party") or {}
    context["budget_constraint"] = request_dict.get("budget_constraint") or {}
    context["route_policy"] = build_route_policy(request_model)

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
    planner_constraints["budget_fit_policy"] = build_budget_fit_policy(request_model)
    planner_constraints["route_policy"] = (
        "当前版本不提供路线hint；请根据候选POI的district、address和location"
        "自行安排顺路组合，避免明显跨区跳跃。"
    )
    return context


def refresh_prompt(record: dict[str, Any]) -> dict[str, Any]:
    context = normalize_context(record)
    request_model = TripRequest(**(record.get("request") or {}))
    builder = FrozenContextBuilder()
    compact_context = builder.compact_for_planner(context)
    planner_query = build_planner_query(builder, request_model, context)
    refreshed = dict(record)
    refreshed["system_prompt"] = PLANNER_AGENT_PROMPT
    refreshed["planner_context"] = context
    refreshed["compact_planner_context"] = compact_context
    refreshed["planner_query"] = planner_query
    return refreshed


def transform_record(row: dict[str, Any], category: str, record_id: str) -> dict[str, Any]:
    item = copy.deepcopy(row)
    source_record_id = item.get("record_id")
    source_path = item.pop("_high_conf_dpo_source_path", None)
    level, amount, strict = transformed_budget(row, category)

    req = dict(item.get("request") or {})
    budget = dict(req.get("budget_constraint") or {})
    budget.update({"amount": amount, "scope": "total", "currency": budget.get("currency") or "CNY", "budget_level": level, "strictness": strict})
    req["budget_constraint"] = budget
    req["free_text_input"] = rewritten_free_text(row, level, amount, strict)
    item["request"] = req

    ctrl = dict(item.get("control_spec") or {})
    ctrl.update({"budget_level": level, "budget_amount": amount, "budget_strictness": strict})
    item["control_spec"] = ctrl
    item["record_id"] = record_id

    metadata = dict(item.get("metadata") or {})
    metadata.update(
        {
            "dpo_context_source_record_id": source_record_id,
            "dpo_context_source_path": source_path,
            "dpo_context_bucket": category,
            "dpo_context_bucket_reason": category_reason(item, category),
            "dpo_context_target_distribution": DEFAULT_QUOTAS,
            "dpo_candidate_plan": {
                "local": LOCAL_CANDIDATE_SPECS,
                "local_total": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS),
                "mimo": {"label": "mimo_strong", "temperature": [0.2, 0.7], "count": 2},
                "total_planned_candidates": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS) + 2,
            },
            "budget_relabel": {
                "category": category,
                "source_budget_level": budget_level(row),
                "source_budget_amount": budget_amount(row),
                "source_budget_strictness": strictness(row),
                "budget_level": level,
                "budget_amount": amount,
                "budget_strictness": strict,
            },
            "prompt_refresh": True,
            "prompt_refreshed_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    item["metadata"] = metadata
    return refresh_prompt(item)


def category_reason(row: dict[str, Any], category: str) -> str:
    pieces = [
        f"budget={budget_level(row)}/{strictness(row)}/{budget_amount(row)}",
        f"days={travel_days(row)}",
        f"party={party_total(row)}",
        f"accommodation={accommodation(row)}",
        f"city_tier={base.city_tier(row)}",
        f"pace={base.pace(row)}",
    ]
    reasons = {
        "below_target_min": "budget under-use pressure",
        "above_hard_user_budget": "hard budget boundary pressure",
        "above_target_max": "budget over-use pressure",
        "meal_diversity": "meal diversity pressure",
        "attraction_diversity": "attraction diversity pressure",
        "hard_valid_stability": "hard-valid stability replay",
        "meal_scale_guardrail": "premium/luxury meal-scale guardrail",
    }
    return f"{reasons.get(category, category)}: " + ", ".join(pieces)


def request_signature(row: dict[str, Any]) -> str:
    return base.request_signature(row)


def select_rows(pool: list[dict[str, Any]], quotas: dict[str, int], seed: int, id_prefix: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    output_signatures: set[str] = set()
    selected_counts: Counter = Counter()
    raw_candidate_counts: Counter = Counter()

    for category, quota in quotas.items():
        candidates = [row for row in pool if category_match(row, category)]
        raw_candidate_counts[category] = len(candidates)
        rng.shuffle(candidates)
        for row in candidates:
            if selected_counts[category] >= quota:
                break
            record_id = f"{id_prefix}_{len(selected):06d}__{category}__{row.get('record_id')}"
            item = transform_record(row, category, record_id)
            signature = request_signature(item)
            if signature in output_signatures:
                continue
            output_signatures.add(signature)
            selected.append(item)
            selected_counts[category] += 1

    if len(selected) < sum(quotas.values()):
        remaining = list(pool)
        rng.shuffle(remaining)
        for row in remaining:
            if len(selected) >= sum(quotas.values()):
                break
            category = "hard_valid_stability"
            record_id = f"{id_prefix}_{len(selected):06d}__fill__{row.get('record_id')}"
            item = transform_record(row, category, record_id)
            signature = request_signature(item)
            if signature in output_signatures:
                continue
            output_signatures.add(signature)
            selected.append(item)
            selected_counts["fill_other"] += 1

    return selected, {
        "selected_counts": dict(selected_counts),
        "raw_candidate_counts": dict(raw_candidate_counts),
    }


def distribution(rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    getters: dict[str, Callable[[dict[str, Any]], str]] = {
        "dpo_context_bucket": lambda row: str((row.get("metadata") or {}).get("dpo_context_bucket", "unknown")),
        "budget_level": budget_level,
        "strictness": strictness,
        "travel_days": lambda row: str(travel_days(row)),
        "party_total": lambda row: str(party_total(row)),
        "companion_type": base.companion_type,
        "city_tier": base.city_tier,
        "diet": base.diet,
        "pace": base.pace,
    }
    result: dict[str, dict[str, int]] = {}
    for key, getter in getters.items():
        result[key] = dict(Counter(getter(row) for row in rows))
    return result


def parse_quota(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("quota must be CATEGORY=COUNT")
    key, count = value.split("=", 1)
    try:
        return key, int(count)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("quota count must be an integer") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare PlannerSoft DPO context records.")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "training/data/planner/dpo/260518_planner_soft2400/records.jsonl")
    parser.add_argument("--summary-output", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=20260518)
    parser.add_argument("--id-prefix", default="dpo_ps2400_260518")
    parser.add_argument("--source", action="append", default=None)
    parser.add_argument("--eval-source", action="append", default=None)
    parser.add_argument("--quota", type=parse_quota, action="append", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    sources = [base.project_path(path) for path in (args.source or base.DEFAULT_SOURCES)]
    eval_sources = [base.project_path(path) for path in (args.eval_source or base.DEFAULT_EVAL_SOURCES)]
    quotas = dict(args.quota or DEFAULT_QUOTAS.items())
    pool, pool_summary = base.load_pool(sources, eval_sources)
    rows, selection_summary = select_rows(pool, quotas, args.seed, args.id_prefix)

    write_jsonl(args.output, rows)
    summary = {
        "output": str(args.output),
        "selected": len(rows),
        "seed": args.seed,
        "id_prefix": args.id_prefix,
        "quotas": quotas,
        "candidate_plan": {
            "local": LOCAL_CANDIDATE_SPECS,
            "local_total": sum(spec["count"] for spec in LOCAL_CANDIDATE_SPECS),
            "mimo_total": 2,
        },
        "distribution": distribution(rows),
        **selection_summary,
        **pool_summary,
    }
    summary_path = args.summary_output or (args.output.parent / "records_summary.json")
    write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
