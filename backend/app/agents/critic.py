"""Critic Agent —— 行程草稿的两层评审，产出结构化 CritiqueReport。

第一层（确定性）：复用 planner.rerank 的指标，把"算得准的硬伤"（预算/真实性/
去重）翻译成 violations。零成本、可复现、零幻觉。
第二层（LLM）：只有第一层无 blocking 时才调用（门控省钱），评审规则判不了的
体验/意图问题（动线、节奏、同行适配、偏好契合、free_text 诉求）。

两层共用同一个 CritiqueReport schema，供 LangGraph 的 critic/revise 回路统一消费。
"""
from __future__ import annotations

import json
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field

from ..models.schemas import TripPlan, TripRequest
from ..planner.output import (
    candidate_names,
    is_lodging_breakfast_meal,
    name_in_candidates,
)
from ..planner.rerank import score_rerank_metrics, score_trip_plan_candidate
from .prompts import CRITIC_AGENT_PROMPT

SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"

# 第二层 LLM 允许的 code 封闭词表（越界/未知 code 丢弃）。
LLM_CRITIC_CODES = frozenset(
    {
        "geo_detour",
        "pacing_overload",
        "pacing_too_light",
        "persona_unfit",
        "preference_mismatch",
        "temporal_implausible",
        "meal_placement_odd",
        "narrative_incoherent",
        "freetext_unmet",
    }
)
_LLM_MAX_VIOLATIONS = 3


class Where(BaseModel):
    day_index: Optional[int] = None
    field: Optional[str] = None


class Violation(BaseModel):
    code: str
    severity: str = SEVERITY_WARNING
    where: Where = Field(default_factory=Where)
    detail: str = ""
    fix_hint: str = ""


class CritiqueReport(BaseModel):
    verdict: str  # "pass" | "revise"
    score: float = 0.0
    round: int = 0
    violations: list[Violation] = Field(default_factory=list)

    def has_blocking(self) -> bool:
        return any(v.severity == SEVERITY_BLOCKING for v in self.violations)

    def blocking_codes(self) -> frozenset[str]:
        """blocking violation 的 code 集合，供回路做防震荡对比。"""
        return frozenset(v.code for v in self.violations if v.severity == SEVERITY_BLOCKING)


class SupportsInvoke(Protocol):
    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str: ...


# ---------------------------------------------------------------------------
# 第一层：确定性 Critic（从 rerank 指标 + 候选池扫描翻译 violations）
# ---------------------------------------------------------------------------

def _snapshot(context: dict[str, Any] | None) -> dict[str, Any]:
    return (context.get("tool_snapshot") or {}) if isinstance(context, dict) else {}


def _grounding_offenders(
    plan: TripPlan, context: dict[str, Any] | None
) -> tuple[list[tuple[int, str]], list[tuple[int, str]], list[tuple[int, str]]]:
    """扫描计划，找出不在候选池里的 景点/酒店/餐厅 (day_index, name)。

    直接给出"哪天哪个被编造"，比单看 grounding_rate 更可执行；也避免
    "某类别为空导致 grounding_ok=False"被误判成幻觉。
    """
    snap = _snapshot(context)
    attr_cand = candidate_names(
        (snap.get("classic_pois") or [])
        + (snap.get("preference_pois") or [])
        + (snap.get("scenic_pois") or [])
        + (snap.get("experience_pois") or [])
    )
    hotel_cand = candidate_names(snap.get("hotel_pois") or [])
    food_cand = candidate_names(snap.get("food_pois") or [])

    bad_attr: list[tuple[int, str]] = []
    bad_hotel: list[tuple[int, str]] = []
    bad_meal: list[tuple[int, str]] = []
    for day in plan.days:
        for attraction in day.attractions:
            if not name_in_candidates(attraction.name, attr_cand):
                bad_attr.append((day.day_index, attraction.name))
        if day.hotel is not None and not name_in_candidates(day.hotel.name, hotel_cand):
            bad_hotel.append((day.day_index, day.hotel.name))
        for meal in day.meals:
            meal_type = str(meal.type or "").strip().lower()
            meal_name = str(meal.name or "")
            if is_lodging_breakfast_meal(meal_name, meal_type):
                continue
            if not name_in_candidates(meal_name, food_cand):
                bad_meal.append((day.day_index, meal_name))
    return bad_attr, bad_hotel, bad_meal


def _names(offenders: list[tuple[int, str]]) -> str:
    return "、".join(name for _, name in offenders)


def deterministic_violations(
    metrics: dict[str, Any],
    plan: TripPlan,
    request: TripRequest,
    context: dict[str, Any] | None,
) -> list[Violation]:
    """把 rerank 指标 + 候选池扫描翻译成 violations。"""
    out: list[Violation] = []

    # 预算硬约束
    if not metrics.get("budget_hard_constraint_ok", True):
        total = int(metrics.get("recomputed_budget_total") or 0)
        amount = int(request.budget_constraint.amount or 0)
        out.append(
            Violation(
                code="budget_overspend",
                severity=SEVERITY_BLOCKING,
                detail=f"硬预算 amount={amount}，按已选项重算 total={total}，超 {total - amount}",
                fix_hint="改选 food_pois/hotel_pois 里更低价的真实候选，不要修改任何单价",
            )
        )

    # 预算分项加总不一致
    if not metrics.get("budget_arithmetic_consistent", True):
        out.append(
            Violation(
                code="budget_math_mismatch",
                severity=SEVERITY_BLOCKING,
                where=Where(field="budget"),
                detail="budget 四个分项之和 ≠ budget.total",
                fix_hint="按 attractions+hotels+meals+transportation 重算并修正 budget.total",
            )
        )

    # 幻觉 POI（按 day 定位）
    bad_attr, bad_hotel, bad_meal = _grounding_offenders(plan, context)
    if bad_attr:
        out.append(
            Violation(
                code="hallucinated_attraction",
                severity=SEVERITY_BLOCKING,
                where=Where(day_index=bad_attr[0][0], field="attractions"),
                detail=f"以下景点不在候选池：{_names(bad_attr)}",
                fix_hint="替换为 classic_pois/preference_pois/scenic_pois/experience_pois 中的真实景点",
            )
        )
    if bad_hotel:
        out.append(
            Violation(
                code="hallucinated_hotel",
                severity=SEVERITY_BLOCKING,
                where=Where(day_index=bad_hotel[0][0], field="hotel"),
                detail=f"以下酒店不在候选池：{_names(bad_hotel)}",
                fix_hint="替换为 hotel_pois 中的真实酒店",
            )
        )
    if bad_meal:
        out.append(
            Violation(
                code="hallucinated_meal",
                severity=SEVERITY_BLOCKING,
                where=Where(day_index=bad_meal[0][0], field="meals"),
                detail=f"以下餐厅不在候选池：{_names(bad_meal)}",
                fix_hint="替换为 food_pois 中的真实餐厅；早餐可用住宿早餐",
            )
        )

    # 偏离预算档位区间（硬约束已过时）—— 提示性
    if metrics.get("budget_hard_constraint_ok", True) and not metrics.get("recomputed_budget_fit_ok", True):
        out.append(
            Violation(
                code="budget_off_target",
                severity=SEVERITY_WARNING,
                detail=f"未落入预算档位区间 [{metrics.get('budget_target_min_total')}, {metrics.get('budget_target_max_total')}]",
                fix_hint="选更贴合档位的真实候选，不要靠改单价或复用餐厅凑数",
            )
        )

    # 多样性 / 预算关系（提示性）
    if not metrics.get("meal_diversity_ok", True):
        out.append(
            Violation(
                code="meal_repeat",
                severity=SEVERITY_WARNING,
                detail="lunch/dinner 同天重样或整体复用过多",
                fix_hint="在 food_pois 里分散选不同餐厅",
            )
        )
    if not metrics.get("attraction_diversity_ok", True):
        out.append(
            Violation(
                code="attraction_repeat",
                severity=SEVERITY_WARNING,
                detail="同一景点被重复安排",
                fix_hint="替换重复项为候选池中其它景点",
            )
        )
    if not metrics.get("meal_cost_scale_ok", True):
        out.append(
            Violation(
                code="meal_cost_scale_low",
                severity=SEVERITY_WARNING,
                detail="高预算档位下正餐人均偏低",
                fix_hint="在 food_pois 里选更符合档位的正餐",
            )
        )

    return out


# ---------------------------------------------------------------------------
# 第二层：LLM Critic（体验/意图评审）
# ---------------------------------------------------------------------------

def build_critic_user_message(
    plan: TripPlan, request: TripRequest, context: dict[str, Any] | None
) -> str:
    snap = _snapshot(context)
    party = request.party
    na = len(
        (snap.get("classic_pois") or [])
        + (snap.get("preference_pois") or [])
        + (snap.get("scenic_pois") or [])
        + (snap.get("experience_pois") or [])
    )
    nf = len(snap.get("food_pois") or [])
    nh = len(snap.get("hotel_pois") or [])
    compact = plan.model_dump_json(exclude_none=True)
    return (
        f"用户画像：城市={request.city}；同行={party.total}人 "
        f"(成人{party.adults}/儿童{party.children}/长辈{party.elders}, {party.companion_type})；"
        f"偏好={'、'.join(request.preferences or [])}；"
        f"额外要求={request.free_text_input or '无'}\n"
        f"候选可用性(仅供 fix_hint 参考)：景点{na} 餐厅{nf} 酒店{nh}\n"
        f"待评审行程(JSON)：{compact}"
    )


def _parse_llm_violations(raw: str) -> list[Violation]:
    """从 LLM 输出里抽出第一个 JSON 对象并解析为 violations（容错、过滤越界 code）。"""
    text = raw or ""
    start = text.find("{")
    if start == -1:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except (ValueError, json.JSONDecodeError):
        return []
    violations: list[Violation] = []
    for item in obj.get("violations", []) or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code", "")).strip()
        if code not in LLM_CRITIC_CODES:
            continue  # 丢弃越界/未知 code
        where = item.get("where") or {}
        violations.append(
            Violation(
                code=code,
                severity=SEVERITY_BLOCKING if item.get("severity") == SEVERITY_BLOCKING else SEVERITY_WARNING,
                where=Where(
                    day_index=where.get("day_index") if isinstance(where, dict) else None,
                    field=where.get("field") if isinstance(where, dict) else None,
                ),
                detail=str(item.get("detail", "")),
                fix_hint=str(item.get("fix_hint", "")),
            )
        )
        if len(violations) >= _LLM_MAX_VIOLATIONS:
            break
    return violations


def llm_violations(
    plan: TripPlan,
    request: TripRequest,
    context: dict[str, Any] | None,
    llm: SupportsInvoke,
    *,
    timeout: int = 120,
) -> list[Violation]:
    messages = [
        {"role": "system", "content": CRITIC_AGENT_PROMPT},
        {"role": "user", "content": build_critic_user_message(plan, request, context)},
    ]
    try:
        raw = llm.invoke(messages, temperature=0.0, timeout=timeout)
    except Exception:  # noqa: BLE001 - LLM Critic 是尽力而为，失败不应中断回路
        return []
    return _parse_llm_violations(raw)


# ---------------------------------------------------------------------------
# Critic Agent：编排两层
# ---------------------------------------------------------------------------

class CriticAgent:
    """两层评审编排：确定性优先 + LLM 门控。"""

    def __init__(self, llm: Optional[SupportsInvoke] = None):
        self._llm = llm

    def review(
        self,
        plan: TripPlan,
        request: TripRequest,
        context: dict[str, Any] | None = None,
        *,
        round: int = 0,
    ) -> CritiqueReport:
        metrics = score_trip_plan_candidate(plan, request, context or {})
        score = score_rerank_metrics(metrics)
        violations = deterministic_violations(metrics, plan, request, context)

        # 门控：第一层有 blocking 时不调 LLM（不给还超预算/编数据的草稿评审美感）。
        det_has_blocking = any(v.severity == SEVERITY_BLOCKING for v in violations)
        if not det_has_blocking and self._llm is not None:
            violations = violations + llm_violations(plan, request, context, self._llm)

        verdict = "revise" if any(v.severity == SEVERITY_BLOCKING for v in violations) else "pass"
        return CritiqueReport(verdict=verdict, score=score, round=round, violations=violations)
