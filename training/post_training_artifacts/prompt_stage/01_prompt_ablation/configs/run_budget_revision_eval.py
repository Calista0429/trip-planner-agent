#!/usr/bin/env python3
"""Run a two-pass budget revision experiment for planner outputs.

This script intentionally treats budget arithmetic as engineering work:

1. Read first-pass model generations.
2. Recompute budget from the selected hotel/attraction/meal item prices.
3. For samples whose recomputed budget is not aligned, call the same model with
   a budget-feedback revision prompt.
4. Postprocess the revised JSON by overwriting the budget ledger with the
   recomputed engineering budget, so downstream rule eval can use the existing
   TripPlan schema while metrics focus on item selection.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parents[4]
BACKEND_DIR = PROJECT_ROOT / "backend"
LEGACY_SCRIPTS_DIR = PROJECT_ROOT / "training/scripts/eval"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(LEGACY_SCRIPTS_DIR))

from app.models.schemas import TripPlan  # noqa: E402
from app.planner.output import extract_json_object  # noqa: E402
from eval_rule_metrics import evaluate_output, recompute_budget_from_selected_items  # noqa: E402
from eval_utils import (  # noqa: E402
    budget_alignment_details,
    budget_fit_policy,
    load_records_by_id,
    metric_rate,
    parse_trip_plan_output,
    read_jsonl,
    requested_budget_total,
    structured_party_size,
    write_json,
)


REVISION_SYSTEM_PROMPT = """你是旅行计划预算修正器。

你会收到 PlannerContext、一个已有 TripPlan，以及工程侧按候选价格重算出来的预算反馈。

你的职责：
1. 只修改必要的 hotel、attractions、meals，让行程更贴近 budget_feedback 的目标区间。
2. 不要自己解释预算计算过程；预算由工程侧最终回填。
3. 只能使用 PlannerContext.tool_snapshot 中的酒店、景点、餐饮候选。
4. 保持 city/start_date/end_date/days/weather_info 的日期结构不变。
5. 每天仍然必须有 1-3 个景点、breakfast/lunch/dinner 三餐。
6. 中间住宿日 hotel 不能为 null，且中间住宿日必须使用同一家酒店；最后一天可以 hotel=null。
7. day.accommodation 必须保持用户请求里的住宿类型。
8. lunch/dinner 必须使用 food_pois 中的真实餐厅名，同一天 lunch 和 dinner 不能相同。
9. hotel.distance 必须保持空字符串 ""，不要编造距离。
10. 为兼容当前 TripPlan schema，输出里仍保留 budget 字段，但工程侧会覆盖它；不要把精力放在预算加总。

输出要求：
- 只输出一个合法 JSON 对象。
- 第一个非空字符必须是 {，最后一个非空字符必须是 }。
- 不要输出 Markdown、代码块、解释、前言、后记或 <think>。
"""


REVISION_PATCH_SYSTEM_PROMPT = """你是旅行计划预算修正器。

你会收到 PlannerContext、已有 TripPlan 的简要选择、工程侧重算预算反馈，以及可替换候选。

你只输出一个 patch JSON，不要重写完整行程计划。工程侧会把 patch 应用到原计划并重新计算预算。

patch JSON 格式：
{
  "changes": [
    {"action": "replace_hotel", "name": "hotel_pois中的酒店名"},
    {"action": "replace_meal", "date": "YYYY-MM-DD", "meal_type": "lunch", "name": "food_pois中的餐厅名"},
    {"action": "replace_attraction", "date": "YYYY-MM-DD", "old_name": "原景点名", "name": "候选景点名"}
  ]
}

规则：
1. 只能输出一个合法 JSON 对象，不能输出 Markdown、解释、代码块或 <think>。
2. 只能使用候选列表中的 name，必须完全复制。
3. 超预算时优先替换酒店、正餐、高价景点为更便宜候选。
4. 预算用太少时优先升级酒店、正餐或增加体验质量更好的付费景点替换。
5. 不要修改日期、天数、天气、day.accommodation。
6. 不要删除当天所有景点；replace_attraction 只能一换一。
7. changes 最多 8 条；如果无需修改，输出 {"changes": []}。
"""


def normalize_base_url(base_url: str) -> str:
    value = base_url.rstrip("/")
    if not value.endswith("/v1"):
        value = f"{value}/v1"
    return value


def build_client(args: argparse.Namespace) -> OpenAI:
    timeout = httpx.Timeout(args.timeout, connect=args.connect_timeout)
    http_client = httpx.Client(timeout=timeout, trust_env=args.trust_env)
    return OpenAI(
        api_key=args.api_key or os.getenv("EVAL_API_KEY") or os.getenv("OPENAI_API_KEY") or "EMPTY",
        base_url=normalize_base_url(args.base_url),
        max_retries=0,
        http_client=http_client,
    )


def unique_generations(path: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        record_id = row.get("record_id")
        if record_id:
            rows[record_id] = row
    return rows


def compact_context(record: dict[str, Any]) -> dict[str, Any]:
    return record.get("planner_context") or record.get("compact_planner_context") or {}


def budget_status(record: dict[str, Any], budget_eval: dict[str, Any]) -> str:
    total = int(budget_eval.get("total") or 0)
    requested = requested_budget_total(record)
    policy = budget_fit_policy(record)
    strictness = str(requested.get("strictness") or budget_eval.get("strictness") or "none")
    if strictness == "hard" and requested.get("available") and total > int(requested.get("total") or 0):
        return "over_hard_budget"
    try:
        target_min = int(policy.get("target_min_total") or 0)
        target_max = int(policy.get("target_max_total") or 0)
    except Exception:  # noqa: BLE001
        target_min = 0
        target_max = 0
    if target_max > 0 and total > target_max:
        return "over_target"
    if target_min > 0 and 0 < total < target_min:
        return "under_target"
    if not budget_eval.get("user_constraint_ok"):
        return "over_budget"
    if not budget_eval.get("level_aligned"):
        return "level_mismatch"
    return "not_aligned"


def build_budget_feedback(record: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    budget = result.get("recomputed_budget") or {}
    budget_eval = result.get("recomputed_budget_eval") or {}
    requested = requested_budget_total(record)
    policy = budget_fit_policy(record)
    status = budget_status(record, budget_eval)
    total = int(budget_eval.get("total") or budget.get("total") or 0)
    target_min = int(policy.get("target_min_total") or 0) if policy else 0
    target_max = int(policy.get("target_max_total") or 0) if policy else 0
    requested_total = int(requested.get("total") or 0)

    if status.startswith("over"):
        repair_goal = [
            "优先替换为更便宜但仍符合住宿类型的酒店",
            "替换高价 lunch/dinner 餐厅，保持餐饮来自 food_pois",
            "替换高价付费景点为同偏好低价或免费景点",
            "保持每天 1-3 个景点，不要删空当天行程",
        ]
    elif status.startswith("under"):
        repair_goal = [
            "优先升级住宿或正餐，让体验匹配预算档位",
            "增加或替换为更符合偏好的付费景点/体验",
            "不要为了省钱显著低于预算目标区间",
            "保持所有 POI 来自工具候选",
        ]
    else:
        repair_goal = [
            "小幅调整酒店、餐饮或付费景点，使重算预算进入目标区间",
            "保留原计划中已经合理且顺路的部分",
            "保持所有 POI 来自工具候选",
        ]

    return {
        "status": status,
        "computed_total": total,
        "computed_per_person_day": budget_eval.get("per_person_day"),
        "requested_budget_total": requested_total,
        "budget_level": budget_eval.get("budget_level"),
        "strictness": budget_eval.get("strictness"),
        "target_min_total": target_min,
        "target_max_total": target_max,
        "cost_breakdown": {
            "hotels": budget.get("total_hotels", 0),
            "attractions": budget.get("total_attractions", 0),
            "meals": budget.get("total_meals", 0),
            "transportation": budget.get("total_transportation", 0),
        },
        "repair_goal": repair_goal,
        "do_not_do": [
            "不要修改旅行日期和天数",
            "不要输出预算计算过程",
            "不要使用工具候选之外的酒店、景点、餐厅",
            "不要把 hotel.distance 写成伪精确距离",
        ],
    }


def build_revision_user_prompt(record: dict[str, Any], plan: dict[str, Any], feedback: dict[str, Any]) -> str:
    payload = {
        "task": "根据预算反馈修正已有 TripPlan。只替换必要的酒店、景点、餐饮，使工程侧重算预算更贴合目标。",
        "planner_context": compact_context(record),
        "budget_feedback": feedback,
        "previous_plan": plan,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_plan_data(output: str) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = extract_json_object(output)
    except Exception as exc:  # noqa: BLE001
        return None, f"json_extract: {exc}"
    if not isinstance(data, dict):
        return None, "json_extract: not an object"
    return data, None


def parse_any_json_object(output: str) -> tuple[dict[str, Any] | None, str | None]:
    decoder = json.JSONDecoder()
    candidates = []
    text = output.strip()
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end != -1:
            candidates.append(text[start:end].strip())
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end != -1:
            candidates.append(text[start:end].strip())
    candidates.append(text)
    for candidate in candidates:
        if not candidate.startswith("{"):
            continue
        try:
            data, end_index = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if candidate[end_index:].strip():
            continue
        if isinstance(data, dict):
            return data, None
    return None, "json_extract: no complete json object"


def candidate_rows(record: dict[str, Any], groups: list[str]) -> list[dict[str, Any]]:
    snapshot = (compact_context(record).get("tool_snapshot") or {})
    rows = []
    seen = set()
    for group in groups:
        for item in snapshot.get(group, []) or []:
            name = item.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            rows.append(item)
    return rows


def compact_candidates(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    hotels = []
    for item in candidate_rows(record, ["hotel_pois"]):
        hotels.append(
            {
                "name": item.get("name"),
                "district": item.get("district"),
                "type": item.get("type"),
                "estimated_cost_hint": item.get("estimated_cost_hint"),
                "rating": item.get("rating"),
            }
        )
    foods = []
    for item in candidate_rows(record, ["food_pois"]):
        foods.append(
            {
                "name": item.get("name"),
                "district": item.get("district"),
                "type": item.get("type"),
                "meal_cost_hint": item.get("meal_cost_hint"),
                "matched_keyword": item.get("matched_keyword"),
                "rating": item.get("rating"),
            }
        )
    attractions = []
    for item in candidate_rows(record, ["classic_pois", "preference_pois", "scenic_pois", "experience_pois"]):
        attractions.append(
            {
                "name": item.get("name"),
                "district": item.get("district"),
                "type": item.get("type"),
                "ticket_price_hint": item.get("ticket_price_hint"),
                "matched_keyword": item.get("matched_keyword"),
                "source_bucket": item.get("source_bucket"),
                "rating": item.get("rating"),
            }
        )
    return {
        "hotel_pois": hotels,
        "food_pois": foods,
        "attraction_pois": attractions,
    }


def selected_items(plan: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for day in plan.get("days") or []:
        rows.append(
            {
                "date": day.get("date"),
                "hotel": (day.get("hotel") or {}).get("name") if isinstance(day.get("hotel"), dict) else None,
                "attractions": [item.get("name") for item in day.get("attractions") or []],
                "meals": [
                    {
                        "type": meal.get("type"),
                        "name": meal.get("name"),
                        "estimated_cost": meal.get("estimated_cost"),
                    }
                    for meal in day.get("meals") or []
                ],
            }
        )
    return {"days": rows}


def build_patch_user_prompt(record: dict[str, Any], plan: dict[str, Any], feedback: dict[str, Any]) -> str:
    payload = {
        "task": "只输出预算修正 patch，不要输出完整 TripPlan。",
        "request": (compact_context(record).get("request") or record.get("request") or {}),
        "party": compact_context(record).get("party") or {},
        "budget_feedback": feedback,
        "selected_items": selected_items(plan),
        "candidates": compact_candidates(record),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def hotel_from_candidate(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name") or "",
        "address": item.get("address") or "",
        "location": item.get("location"),
        "price_range": item.get("price_range") or "",
        "rating": item.get("rating"),
        "distance": "",
        "type": item.get("type") or "",
        "estimated_cost": item.get("estimated_cost_hint") or item.get("estimated_cost") or 0,
    }


def meal_from_candidate(item: dict[str, Any], meal_type: str, old_meal: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": meal_type,
        "name": item.get("name") or "",
        "address": item.get("address"),
        "location": item.get("location"),
        "description": (old_meal or {}).get("description") or item.get("type") or "",
        "estimated_cost": item.get("meal_cost_hint") or item.get("estimated_cost") or 0,
    }


def attraction_from_candidate(item: dict[str, Any], old_attraction: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": item.get("name") or "",
        "address": item.get("address") or "",
        "location": item.get("location"),
        "visit_duration": (old_attraction or {}).get("visit_duration") or 90,
        "description": (old_attraction or {}).get("description") or item.get("type") or "",
        "category": item.get("type") or (old_attraction or {}).get("category") or "",
        "rating": item.get("rating"),
        "photos": item.get("photos") or [],
        "poi_id": item.get("poi_id") or "",
        "image_url": item.get("image_url"),
        "ticket_price": item.get("ticket_price_hint") or item.get("ticket_price") or 0,
    }


def apply_patch_changes(record: dict[str, Any], plan: dict[str, Any], patch_data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    new_plan = json.loads(json.dumps(plan, ensure_ascii=False))
    hotel_map = {item.get("name"): item for item in candidate_rows(record, ["hotel_pois"]) if item.get("name")}
    food_map = {item.get("name"): item for item in candidate_rows(record, ["food_pois"]) if item.get("name")}
    attraction_map = {
        item.get("name"): item
        for item in candidate_rows(record, ["classic_pois", "preference_pois", "scenic_pois", "experience_pois"])
        if item.get("name")
    }
    changes = patch_data.get("changes")
    if not isinstance(changes, list):
        return new_plan, {"applied": 0, "skipped": [{"reason": "changes_not_list"}]}

    applied = 0
    skipped = []
    days = new_plan.get("days") or []
    days_by_date = {day.get("date"): day for day in days if isinstance(day, dict)}
    expected_accommodation = (record.get("request") or {}).get("accommodation")

    for change in changes[:8]:
        if not isinstance(change, dict):
            skipped.append({"change": change, "reason": "change_not_object"})
            continue
        action = change.get("action")
        name = change.get("name")
        if action == "replace_hotel":
            item = hotel_map.get(name)
            if not item:
                skipped.append({"change": change, "reason": "hotel_not_found"})
                continue
            hotel = hotel_from_candidate(item)
            for index, day in enumerate(days):
                if index < len(days) - 1:
                    day["hotel"] = hotel
                if expected_accommodation:
                    day["accommodation"] = expected_accommodation
            applied += 1
        elif action == "replace_meal":
            item = food_map.get(name)
            date = change.get("date")
            meal_type = str(change.get("meal_type") or "").lower()
            day = days_by_date.get(date)
            if not item or not day or meal_type not in {"breakfast", "lunch", "dinner"}:
                skipped.append({"change": change, "reason": "meal_target_not_found"})
                continue
            meals = day.get("meals") or []
            replaced = False
            for index, meal in enumerate(meals):
                if str(meal.get("type") or "").lower() == meal_type:
                    meals[index] = meal_from_candidate(item, meal_type, meal)
                    replaced = True
                    break
            if not replaced:
                meals.append(meal_from_candidate(item, meal_type))
            day["meals"] = meals
            applied += 1
        elif action == "replace_attraction":
            item = attraction_map.get(name)
            date = change.get("date")
            old_name = change.get("old_name")
            day = days_by_date.get(date)
            if not item or not day:
                skipped.append({"change": change, "reason": "attraction_target_not_found"})
                continue
            attractions = day.get("attractions") or []
            if not attractions:
                skipped.append({"change": change, "reason": "day_has_no_attractions"})
                continue
            target_index = 0
            if old_name:
                for index, attraction in enumerate(attractions):
                    if attraction.get("name") == old_name:
                        target_index = index
                        break
            attractions[target_index] = attraction_from_candidate(item, attractions[target_index])
            day["attractions"] = attractions[:3]
            applied += 1
        else:
            skipped.append({"change": change, "reason": "unknown_action"})

    for day in days:
        if expected_accommodation:
            day["accommodation"] = expected_accommodation
        hotel = day.get("hotel")
        if isinstance(hotel, dict):
            hotel["distance"] = ""

    return new_plan, {"applied": applied, "skipped": skipped}


def overwrite_budget_with_engineering_total(record: dict[str, Any], plan: dict[str, Any], transport_budget: int) -> dict[str, Any]:
    plan = json.loads(json.dumps(plan, ensure_ascii=False))
    budget = plan.get("budget")
    if not isinstance(budget, dict):
        budget = {}
    budget["total_transportation"] = max(0, int(transport_budget or 0))
    plan["budget"] = budget
    plan["budget"] = recompute_budget_from_selected_items(record, plan, budget)
    return plan


def postprocess_output(record: dict[str, Any], output: str, transport_budget: int) -> tuple[str, str | None]:
    data, error = parse_plan_data(output)
    if data is None:
        return output, error
    data = overwrite_budget_with_engineering_total(record, data, transport_budget)
    try:
        TripPlan(**data)
    except Exception as exc:  # noqa: BLE001
        return json.dumps(data, ensure_ascii=False), f"schema: {exc}"
    return json.dumps(data, ensure_ascii=False), None


def should_revise(before_result: dict[str, Any]) -> bool:
    metrics = before_result.get("metrics") or {}
    if not before_result.get("call_ok") or not metrics.get("schema_ok"):
        return False
    return not bool(metrics.get("recomputed_budget_fit_ok"))


def guarded_accept_patch(
    record: dict[str, Any],
    before_result: dict[str, Any],
    candidate_output: str,
    args: argparse.Namespace,
) -> tuple[bool, dict[str, Any], list[str]]:
    if not args.accept_guard:
        result = evaluate_output(record, {"ok": True, "output": candidate_output, "latency_seconds": 0})
        return True, result, []

    after_result = evaluate_output(record, {"ok": True, "output": candidate_output, "latency_seconds": 0})
    before_metrics = before_result.get("metrics") or {}
    after_metrics = after_result.get("metrics") or {}
    reasons = []

    budget_improved = (
        (not before_metrics.get("recomputed_budget_fit_ok") and after_metrics.get("recomputed_budget_fit_ok"))
        or (not before_metrics.get("recomputed_budget_hard_ok") and after_metrics.get("recomputed_budget_hard_ok"))
    )
    if not budget_improved:
        reasons.append("budget_not_improved_to_pass")

    no_regress_keys = [
        "json_extract_ok",
        "schema_ok",
        "city_ok",
        "date_range_ok",
        "days_len_ok",
        "day_dates_ok",
        "weather_dates_ok",
        "day_index_ok",
        "accommodation_type_ok",
        "middle_hotel_ok",
        "invalid_hotel_name_ok",
        "hotel_grounding_ok",
        "hotel_distance_placeholder_ok",
        "attraction_count_ok",
        "attraction_grounding_ok",
        "meal_complete",
        "meal_specific_ok",
        "meal_valid_semantics_ok",
        "meal_grounding_ok",
        "location_object_ok",
        "weather_match",
        "attraction_diversity_ok",
        "meal_diversity_ok",
    ]
    for key in no_regress_keys:
        if before_metrics.get(key) is True and after_metrics.get(key) is not True:
            reasons.append(f"regress:{key}")

    return not reasons, after_result, reasons


def process_one(
    record: dict[str, Any],
    first_generation: dict[str, Any],
    args: argparse.Namespace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    started = time.perf_counter()
    before_result = evaluate_output(record, first_generation)
    before_plan, _, _, _ = parse_trip_plan_output(first_generation.get("output", ""))
    before_plan_data = before_plan.model_dump() if before_plan is not None else None
    transport_budget = int((before_result.get("recomputed_budget") or {}).get("total_transportation") or 0)

    row: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_name": args.model_name,
        "api_model": args.api_model,
        "record_id": record["record_id"],
        "request": record.get("request") or {},
        "control_spec": record.get("control_spec") or {},
        "first_pass_model_name": first_generation.get("model_name"),
        "first_pass_ok": bool(first_generation.get("ok")),
        "before_recomputed_budget": before_result.get("recomputed_budget"),
        "before_recomputed_budget_eval": before_result.get("recomputed_budget_eval"),
        "revision_attempted": False,
    }

    raw_row = dict(row)
    raw_output = first_generation.get("output", "")

    if not should_revise(before_result) or before_plan_data is None:
        reason = "budget_already_fit" if before_result.get("metrics", {}).get("recomputed_budget_fit_ok") else "not_revisable"
        postprocessed_output, postprocess_error = postprocess_output(record, raw_output, transport_budget)
        row.update(
            {
                "ok": postprocess_error is None,
                "output": postprocessed_output,
                "output_chars": len(postprocessed_output),
                "latency_seconds": round(time.perf_counter() - started, 3),
                "finish_reason": "skipped",
                "revision_skip_reason": reason,
                "postprocess_error": postprocess_error,
            }
        )
        raw_row.update(row)
        raw_row["output"] = raw_output
        raw_row["output_chars"] = len(raw_output)
        return row, raw_row

    feedback = build_budget_feedback(record, before_result)
    client = build_client(args)
    try:
        if args.revision_mode == "patch":
            response = client.chat.completions.create(
                model=args.api_model,
                messages=[
                    {"role": "system", "content": REVISION_PATCH_SYSTEM_PROMPT},
                    {"role": "user", "content": build_patch_user_prompt(record, before_plan_data, feedback)},
                ],
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                stream=False,
            )
            raw_output = response.choices[0].message.content or ""
            patch_data, patch_error = parse_any_json_object(raw_output)
            patch_report = {"applied": 0, "skipped": []}
            revised_plan = before_plan_data
            if patch_data is None:
                patch_error = patch_error or "patch_parse_failed"
            else:
                revised_plan, patch_report = apply_patch_changes(record, before_plan_data, patch_data)
            revised_plan = overwrite_budget_with_engineering_total(record, revised_plan, transport_budget)
            postprocessed_output = json.dumps(revised_plan, ensure_ascii=False)
            try:
                TripPlan(**revised_plan)
                postprocess_error = None
            except Exception as exc:  # noqa: BLE001
                postprocess_error = f"schema: {exc}"
            if patch_error and not postprocess_error:
                # Patch parse failure means no revision was applied, but the
                # original plan remains evaluable. Keep it as a diagnostic, not
                # a generation failure.
                postprocess_error = None
            patch_accepted = False
            patch_reject_reasons: list[str] = []
            if postprocess_error is not None:
                patch_reject_reasons = [postprocess_error]
                original_plan = overwrite_budget_with_engineering_total(record, before_plan_data, transport_budget)
                postprocessed_output = json.dumps(original_plan, ensure_ascii=False)
                postprocess_error = None
            elif patch_report.get("applied", 0) > 0:
                patch_accepted, _, patch_reject_reasons = guarded_accept_patch(
                    record,
                    before_result,
                    postprocessed_output,
                    args,
                )
                if not patch_accepted:
                    original_plan = overwrite_budget_with_engineering_total(record, before_plan_data, transport_budget)
                    postprocessed_output = json.dumps(original_plan, ensure_ascii=False)
        else:
            response = client.chat.completions.create(
                model=args.api_model,
                messages=[
                    {"role": "system", "content": REVISION_SYSTEM_PROMPT},
                    {"role": "user", "content": build_revision_user_prompt(record, before_plan_data, feedback)},
                ],
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                stream=False,
            )
            raw_output = response.choices[0].message.content or ""
            postprocessed_output, postprocess_error = postprocess_output(record, raw_output, transport_budget)
            patch_data = None
            patch_error = None
            patch_report = {"applied": 0, "skipped": []}
            patch_accepted = False
            patch_reject_reasons = []
        row.update(
            {
                "ok": postprocess_error is None,
                "output": postprocessed_output,
                "output_chars": len(postprocessed_output),
                "latency_seconds": round(time.perf_counter() - started, 3),
                "finish_reason": response.choices[0].finish_reason,
                "revision_attempted": True,
                "revision_mode": args.revision_mode,
                "budget_feedback": feedback,
                "patch": patch_data,
                "patch_error": patch_error,
                "patch_report": patch_report,
                "patch_accepted": patch_accepted,
                "patch_reject_reasons": patch_reject_reasons,
                "raw_output_chars": len(raw_output),
                "postprocess_error": postprocess_error,
            }
        )
        raw_row.update(
            {
                "ok": True,
                "output": raw_output,
                "output_chars": len(raw_output),
                "latency_seconds": row["latency_seconds"],
                "finish_reason": response.choices[0].finish_reason,
                "revision_attempted": True,
                "revision_mode": args.revision_mode,
                "budget_feedback": feedback,
                "patch": patch_data,
                "patch_error": patch_error,
                "patch_report": patch_report,
                "patch_accepted": patch_accepted,
                "patch_reject_reasons": patch_reject_reasons,
                "postprocess_error": postprocess_error,
            }
        )
    except Exception as exc:  # noqa: BLE001
        row.update(
            {
                "ok": False,
                "output": "",
                "output_chars": 0,
                "latency_seconds": round(time.perf_counter() - started, 3),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "revision_attempted": True,
                "revision_mode": args.revision_mode,
                "budget_feedback": feedback,
            }
        )
        raw_row.update(row)
    return row, raw_row


def evaluate_rows(records_by_id: dict[str, dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for row in rows:
        record = records_by_id.get(row.get("record_id"))
        if record:
            results.append(evaluate_output(record, row))
    return results


def composite_pass(metrics: dict[str, Any], keys: list[str]) -> bool:
    return all(metrics.get(key) is True for key in keys)


def summarize_experiment(
    records_by_id: dict[str, dict[str, Any]],
    first_generations_by_id: dict[str, dict[str, Any]],
    after_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    after_by_id = {row["record_id"]: row for row in after_rows if row.get("record_id")}
    record_ids = [record_id for record_id in after_by_id if record_id in first_generations_by_id]
    before_results = [
        evaluate_output(records_by_id[record_id], first_generations_by_id[record_id])
        for record_id in record_ids
        if record_id in records_by_id
    ]
    after_results = evaluate_rows(records_by_id, [after_by_id[record_id] for record_id in record_ids])

    draft_core_keys = [
        "json_extract_ok",
        "schema_ok",
        "city_ok",
        "date_range_ok",
        "days_len_ok",
        "day_dates_ok",
        "weather_dates_ok",
        "day_index_ok",
        "accommodation_type_ok",
        "meal_complete",
        "meal_specific_ok",
        "meal_valid_semantics_ok",
        "attraction_count_ok",
        "attraction_grounding_ok",
        "middle_hotel_ok",
        "invalid_hotel_name_ok",
        "hotel_grounding_ok",
        "hotel_distance_placeholder_ok",
        "location_object_ok",
        "weather_match",
    ]
    planner_draft_keys = draft_core_keys + ["meal_grounding_ok"]
    tracked = {
        "planner_draft_hard_pass": planner_draft_keys,
        "budget_selection_ok": ["recomputed_budget_fit_ok"],
        "draft_budget_fit_pass": planner_draft_keys + ["recomputed_budget_fit_ok"],
        "recomputed_budget_hard_ok": ["recomputed_budget_hard_ok"],
        "meal_grounding_ok": ["meal_grounding_ok"],
        "attraction_grounding_ok": ["attraction_grounding_ok"],
        "attraction_diversity_ok": ["attraction_diversity_ok"],
        "meal_diversity_ok": ["meal_diversity_ok"],
    }

    def rates(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out = {}
        for name, keys in tracked.items():
            passed = sum(composite_pass(row.get("metrics") or {}, keys) for row in results)
            out[name] = {
                "pass": passed,
                "total": len(results),
                "rate": metric_rate(passed, len(results)),
            }
        return out

    attempted = sum(1 for row in after_rows if row.get("revision_attempted"))
    accepted = sum(1 for row in after_rows if row.get("patch_accepted"))
    skipped_fit = sum(1 for row in after_rows if row.get("revision_skip_reason") == "budget_already_fit")
    failed_calls = sum(1 for row in after_rows if not row.get("ok"))

    return {
        "total": len(record_ids),
        "revision_attempted": attempted,
        "patch_accepted": accepted,
        "revision_skipped_budget_already_fit": skipped_fit,
        "failed_or_unparseable_after_postprocess": failed_calls,
        "before": rates(before_results),
        "after": rates(after_results),
    }


def write_markdown_report(path: Path, summary: dict[str, Any], args: argparse.Namespace) -> None:
    lines = [
        f"# Budget Revision Eval: {args.model_name}\n\n",
        f"- records: `{args.records}`\n",
        f"- first_generations: `{args.first_generations}`\n",
        f"- output_file: `{args.output_file}`\n",
        f"- raw_output_file: `{args.raw_output_file}`\n",
        f"- base_url: `{normalize_base_url(args.base_url)}`\n",
        f"- workers: {args.workers}\n",
        f"- revision_mode: `{args.revision_mode}`\n",
        f"- accept_guard: {args.accept_guard}\n",
        f"- total compared: {summary['total']}\n",
        f"- revision_attempted: {summary['revision_attempted']}\n",
        f"- patch_accepted: {summary.get('patch_accepted', 0)}\n",
        f"- skipped_budget_already_fit: {summary['revision_skipped_budget_already_fit']}\n",
        f"- failed_or_unparseable_after_postprocess: {summary['failed_or_unparseable_after_postprocess']}\n\n",
        "## Before vs After\n\n",
        "| Metric | Before | After | Delta |\n",
        "| --- | ---: | ---: | ---: |\n",
    ]
    for metric, before in summary["before"].items():
        after = summary["after"].get(metric, {"pass": 0, "total": 0, "rate": 0})
        delta = after["rate"] - before["rate"]
        lines.append(
            f"| `{metric}` | {before['pass']}/{before['total']} = {before['rate']:.2%} | "
            f"{after['pass']}/{after['total']} = {after['rate']:.2%} | {delta:+.2%} |\n"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run budget-feedback revision eval.")
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--first-generations", type=Path, required=True)
    parser.add_argument("--model-name", required=True)
    parser.add_argument("--api-model", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "training/outputs/eval")
    parser.add_argument("--output-file", type=Path, default=None)
    parser.add_argument("--raw-output-file", type=Path, default=None)
    parser.add_argument("--report-json", type=Path, default=None)
    parser.add_argument("--report-md", type=Path, default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--revision-mode", choices=["patch", "full_plan"], default="patch")
    parser.add_argument("--no-accept-guard", dest="accept_guard", action="store_false")
    parser.set_defaults(accept_guard=True)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=12000)
    parser.add_argument("--timeout", type=float, default=660)
    parser.add_argument("--connect-timeout", type=float, default=10)
    parser.add_argument("--trust-env", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.output_dir / args.model_name
    run_dir.mkdir(parents=True, exist_ok=True)
    args.output_file = args.output_file or (run_dir / "budget_revision_generations.postprocessed.jsonl")
    args.raw_output_file = args.raw_output_file or (run_dir / "budget_revision_generations.raw.jsonl")
    args.report_json = args.report_json or (run_dir / "budget_revision_report.json")
    args.report_md = args.report_md or (run_dir / "budget_revision_report.md")

    records_by_id = load_records_by_id(args.records)
    first_generations_by_id = unique_generations(args.first_generations)
    record_ids = [record_id for record_id in records_by_id if record_id in first_generations_by_id]
    if args.limit > 0:
        record_ids = record_ids[: args.limit]

    print(
        f"budget revision eval: model={args.model_name}, records={len(record_ids)}, "
        f"workers={args.workers}, base_url={normalize_base_url(args.base_url)}",
        flush=True,
    )

    rows: list[dict[str, Any]] = []
    raw_rows: list[dict[str, Any]] = []
    if args.workers <= 1:
        for index, record_id in enumerate(record_ids, start=1):
            row, raw_row = process_one(records_by_id[record_id], first_generations_by_id[record_id], args)
            rows.append(row)
            raw_rows.append(raw_row)
            print(
                f"progress {index}/{len(record_ids)} revised={sum(r.get('revision_attempted') for r in rows)} "
                f"ok={sum(bool(r.get('ok')) for r in rows)} last={record_id}",
                flush=True,
            )
    else:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(process_one, records_by_id[record_id], first_generations_by_id[record_id], args): record_id
                for record_id in record_ids
            }
            for index, future in enumerate(as_completed(futures), start=1):
                row, raw_row = future.result()
                rows.append(row)
                raw_rows.append(raw_row)
                print(
                    f"progress {index}/{len(record_ids)} revised={sum(r.get('revision_attempted') for r in rows)} "
                    f"ok={sum(bool(r.get('ok')) for r in rows)} last={row.get('record_id')}",
                    flush=True,
                )

    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    with args.output_file.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    with args.raw_output_file.open("w", encoding="utf-8") as file:
        for row in raw_rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = summarize_experiment(records_by_id, first_generations_by_id, rows)
    write_json(args.report_json, summary)
    write_markdown_report(args.report_md, summary, args)
    print(f"postprocessed generations: {args.output_file}")
    print(f"raw generations: {args.raw_output_file}")
    print(f"report json: {args.report_json}")
    print(f"report md: {args.report_md}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
