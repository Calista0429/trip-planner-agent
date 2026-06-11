"""基于同一批 frozen eval records 生成 prompt 消融版本。

脚本只改 system_prompt 和 planner_query，不重新调用工具，也不改变
request/planner_context。这样可以把评估差异尽量收敛到 prompt 规则本身。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VARIANT_ORDER = [
    "attraction_dedupe_only",
    "attraction_source_guard_only",
    "attraction_dedupe_source_guard",
    "attraction_dedupe_source_self_check",
    "budget_hard",
    "budget_order",
    "budget_fewshot",
    "budget_symbolic",
    "budget_ledger",
    "budget_ledger_no_schema_numbers",
    "budget_relation_lite",
    "budget_relation_priority",
    "budget_relation_self_check",
    "room_person_price_lite",
    "room_person_price_full",
    "room_person_price_self_check",
    "budget_symbolic_meal_semantic",
    "meal_count_limit_symbolic",
    "meal_rotation_symbolic",
    "meal_grounded_diversity_symbolic",
]


MEAL_FALLBACK_RULE = """餐饮兜底补充:
- lunch/dinner 首选不同的真实 food_pois 候选；同一天 lunch 和 dinner 不要选择同一家餐厅，整趟行程不要每天反复使用同一家店、同一品牌或同一种单品。
- 只有当可用 food_pois 明显不足、忌口过滤后选择很少时，才允许少量复用真实 food_pois；复用时优先选择已使用次数最少的候选。
- lunch/dinner 绝不能写“无”、空字符串、“酒店晚餐”“酒店午餐”“民宿晚餐”“客栈晚餐”“酒店餐厅”“附近餐厅”“当地餐厅”等占位或住宿类餐饮。
- 酒店早餐/民宿早餐/客栈早餐作为 breakfast 可接受且可重复，不计入餐饮多样性惩罚；非住宿早餐不要连续多天固定同一家店或同一种早餐。
"""


MEAL_SEMANTIC_FALLBACK_RULE = """餐饮语义兜底补充:
- lunch/dinner 首选逐字复制 food_pois 中的真实餐厅 name/address/location/meal_cost_hint。
- 如果 food_pois 不能覆盖非常典型的本地餐饮场景，可以使用真实餐饮语义 fallback，例如“上海城隍庙小吃”“西安回民街小吃”“夜市小吃”“本地美食街”；但 name 必须明确包含小吃、夜市、美食、餐厅、饭店、酒家、茶社、面馆、粉店、火锅、烧烤、咖啡、甜品等餐饮语义，estimated_cost 参考同档位 food_pois 的 meal_cost_hint 估算，不能写 0。
- 绝不能把 hotel_pois 的酒店/宾馆/旅馆/民宿/客栈/公寓名称写成 meal.name；绝不能写“无”、空字符串、“酒店晚餐”“酒店午餐”“民宿晚餐”“客栈晚餐”“酒店餐厅”。
- 绝不能把非餐饮 POI 写成 meal.name，例如电子游艺厅、博物馆、景点、公园、商场、培训机构。无法判断 fallback 是否餐饮时，重复使用一个真实 food_pois。
"""


MEAL_COUNT_LIMIT_RULE = """餐饮多样性计数补充:
- 酒店早餐/民宿早餐/客栈早餐作为 breakfast 可接受，可重复，不计入餐饮重复。
- 同一天 lunch 和 dinner 必须是不同餐厅；如果 food_pois 至少有2个可用餐厅，不能让 lunch.name == dinner.name，也不能让两者只是同一品牌不同分店。
- 整趟行程中，非住宿早餐、lunch、dinner 的同一餐厅/同一品牌最多出现2次；如果 travel_days>=5 且 food_pois 可用候选少于10个，最多出现3次。
- 生成前在内部数一遍 meal.name/品牌出现次数；超过上限时，必须改用另一个真实 food_pois。
"""


MEAL_ROTATION_RULE = """餐饮候选轮转补充:
- 先在内部建立 used_meal_names 计数表，不输出这个表。
- 选择每一餐时，优先从 meal_roles 匹配当前餐别、avoid_risk_keywords 为空、price_level 合适的 food_pois 中选“已使用次数最少”的候选。
- lunch/dinner 优先轮换不同 source_bucket、cuisine_tags 和 district，避免每天固定同一批餐厅。
- 当多个候选都可用时，优先选择还没用过的餐厅；只有所有合适候选都用过后，才允许复用真实 food_pois。
- 酒店早餐/民宿早餐/客栈早餐可作为 breakfast 且可重复，不参与轮转惩罚。
"""


MEAL_GROUNDED_DIVERSITY_RULE = """餐饮 grounding 与多样性均衡补充:
- food_pois 是餐饮来源上限，lunch/dinner 不要为了多样性编造不存在的餐厅。
- 如果存在足够 food_pois，优先做到每天 lunch/dinner 不同店、跨天少重复；如果候选不足，允许复用真实 food_pois，但必须在 description 中说明“附近可用候选有限，因此复用该真实餐厅”。
- 允许使用真实语义餐饮 fallback 的范围很窄：仅限城市级典型美食街/夜市/小吃集合，例如“上海城隍庙小吃”“西安回民街小吃”；不能用“附近餐厅”“当地餐厅”“酒店晚餐”这类泛化词。
- 酒店早餐/民宿早餐/客栈早餐作为 breakfast 可接受，可重复，不计入餐饮多样性惩罚。
"""


ATTRACTION_DEDUPE_RULE = """景点全程去重补充:
- 不改变景点密度偏好：正常旅行每天可以安排 1-3 个景点；如果路线顺、体力允许、候选充足，安排 3 个景点是可以的。
- 但同一个景点 name 默认全程只能出现一次，不能跨天重复安排。
- 内部维护 used_attraction_names，不输出这个表；去重 key 忽略空格，并忽略中文/英文括号中的分店或补充说明。
- 每天选择 attractions 时，优先选择还没用过、并且来自 classic_pois/preference_pois/scenic_pois/experience_pois 的候选。
- 如果后续天想再次使用已用过的景点，必须改选另一个未使用的真实景点候选；宁可换成同区的轻量景点，也不要重复同名景点。
- 只有当真实景点候选已经不足以保证每天至少 1 个景点时，才允许复用；复用时必须在 description 里说明候选不足或返程/体力原因。
"""


ATTRACTION_SOURCE_GUARD_RULE = """景点来源防污染补充:
- attractions 只能从 classic_pois、preference_pois、scenic_pois、experience_pois 选择真实 POI。
- attraction.name 必须完全复制这些景点候选中的 name；attraction.ticket_price 必须复制对应候选的 ticket_price_hint。
- 禁止把 food_pois、hotel_pois 写进 attractions；餐厅、咖啡馆、米粉店、火锅店、酒家、饭店、酒店、民宿、客栈、旅舍只能用于 meals 或 hotel，不能作为景点。
- 当用户偏好包含美食、夜市、老字号、城市漫步、购物、艺术街区时，可以选择 preference_pois/scenic_pois 中的步行街、夜市、老街、古街、历史街区、商业街、艺术街区等景点候选；不要用 food_pois 中的具体餐厅/咖啡馆来补 attractions。
- 如果某个常识上像景点的名字没有出现在四个景点候选桶中，也不要编进 attractions；改用候选桶里最接近的真实 POI。
"""


ATTRACTION_SELF_CHECK_RULE = """景点输出前自检补充:
最终输出 JSON 前，内部按下面顺序自检，不要输出自检文本：
1. 扫描所有 days[].attractions[].name，确认每个 name 都来自 classic_pois/preference_pois/scenic_pois/experience_pois。
2. 如果发现 attractions 中有 food_pois 或 hotel_pois 名称，必须替换为未使用的真实景点候选；不能把餐厅/咖啡馆/酒店留在 attractions。
3. 扫描全程景点去重 key；如果同一个景点出现多次，保留第一次，后续重复项优先替换为同区或相邻区域的未使用景点候选。
4. 如果没有合适替换候选，可以删除后续重复项，但必须保证当天 attractions 仍有 1-3 个真实景点。
5. 自检后再次确认：每天 attractions 数量为 1-3，且默认没有同名景点跨天重复。
"""


BUDGET_HARD_RULE = """预算口径补充:
- hotel.estimated_cost 表示“全体同行每晚住宿费用”，不是单人价格；budget.total_hotels 必须等于所有非 null day.hotel.estimated_cost 按住宿晚数加总。同一酒店住 N 晚，就按每晚费用乘 N 晚。
- meal.estimated_cost 表示“全体同行这一餐总费用”，不是单人价格；budget.total_meals 必须等于所有 meal.estimated_cost 直接加总，不要再乘 party.total。
- attraction.ticket_price 表示“成人单人门票”；budget.total_attractions 必须等于所有已选景点 ticket_price 之和再乘以 PlannerContext.party.total。
- budget.total 必须只由四个分项重新加总得到：total_attractions + total_hotels + total_meals + total_transportation。不要凭感觉填总价，不要照抄示例数字。
"""


BUDGET_ORDER_RULE = """内部生成顺序补充:
1. 先从候选中确定每天的酒店、景点和三餐。
2. 再统计实际住宿晚数：最后一天 hotel=null 时不计住宿；最后一天仍入住时才计入一晚。
3. 再分别计算 total_attractions、total_hotels、total_meals、total_transportation。
4. 最后计算 budget.total，并只输出最终 JSON。
不要一边写每天行程一边顺手估 budget；budget 必须在所有 day 写完后统一复算。
"""


BUDGET_FEWSHOT_RULE = """预算算术口径示例:
如果 3 天 2 晚，2 人同行；酒店每晚 400，住宿 2 晚，则 total_hotels=800。
如果所选景点单人票价为 60 和 40，2 人同行，则 total_attractions=(60+40)*2=200。
如果三餐整组费用合计 520，则 total_meals=520，不再乘人数。
如果全程交通 180，则 total_transportation=180。
最终 total=800+200+520+180=1700。
这个示例只用于理解计算口径，绝不能复用这些数字到实际输出。
"""


BUDGET_SYMBOLIC_RULE = """预算算术口径示例:
- 酒店总价 = 每晚住宿费用 × 实际住宿晚数；最后一天 hotel=null 时不计住宿。
- 景点总价 = 所选景点成人单人门票之和 × PlannerContext.party.total。
- 餐饮总价 = 所有 breakfast/lunch/dinner 的整组 meal.estimated_cost 直接加总，不再乘人数。
- 总预算 = 景点总价 + 酒店总价 + 餐饮总价 + 全程本地交通。
这个示例只用于理解计算口径，不包含任何可复用数字；实际输出必须使用当前 PlannerContext 的候选价格和同行人数重新计算。
"""


BUDGET_LEDGER_RULE = """预算账本强约束:
- budget 不是新的规划内容，而是对已经输出的 days 数组做机械汇总。先完整写好 days，再回扫 days 里的字段计算 budget。
- total_hotels 只等于所有非 null day.hotel.estimated_cost 的逐项加总；如果最后一天 hotel=null，就不计入最后一天；不要按 travel_days、party.total 或用户预算重新乘。
- total_attractions 只等于所有 days[].attractions[].ticket_price 的逐项加总后再乘 PlannerContext.party.total；不要把已经乘过人数的结果再写进 attraction.ticket_price。
- total_meals 只等于所有 days[].meals[].estimated_cost 的逐项加总；meal.estimated_cost 已经是整组单餐费用，绝不能再乘 PlannerContext.party.total。
- total_transportation 是唯一允许估算的预算分项，必须是非负整数；估完后也必须参与最终加总。
- 最后一步只做这一件事：budget.total = total_attractions + total_hotels + total_meals + total_transportation。若发现 total 不一致，必须改 budget.total，而不是留下近似值。
- 如果 budget_fit_policy 或 hard 预算上限与预算账本冲突，先调整酒店/景点/餐厅选择，再重新回扫计算；不要通过少算酒店晚数、少乘门票人数、少加餐费来“凑预算”。
"""


BUDGET_RELATION_LITE_RULE = """预算语义关系补充:
- 这次优先保证预算口径关系正确，不要为了压低总价而少算人数、少算住宿晚数或把整组餐费写成单人价。
- 住宿费用必须体现天数关系：N 天通常 N-1 晚；最后一天 hotel=null 才不计住宿，其他有 hotel 的 day 都要体现一晚住宿费用。
- 景点费用必须体现人数关系：attraction.ticket_price 是成人单人门票；同行总人数越多，budget.total_attractions 应相应放大。
- 餐饮费用必须体现同行人数和预算档位：meal.estimated_cost 是整组人单餐费用，不是单人价。多人同行、舒适/高端预算时，午餐和晚餐不要写成明显偏低的小额单人餐费。
"""


BUDGET_RELATION_PRIORITY_RULE = """预算语义优先级补充:
- 如果无法同时做到预算总额完全精确和预算口径关系完全正确，优先保证口径关系：住宿晚数、景点门票人数、餐饮整组费用不能错。
- 不允许用“少算酒店晚数”“景点只算一个人”“多人正餐按单人价写”来让预算看起来更低。
- budget.total 可以后续由系统重新核算，但 day.hotel.estimated_cost、attraction.ticket_price、meal.estimated_cost 必须表达正确的业务语义。
- 输出前内部检查三句话：住了几晚？门票乘了几个人？每顿饭是不是整组费用？
"""


BUDGET_RELATION_SELF_CHECK_RULE = """预算语义自检补充:
最终输出 JSON 前，内部按下面顺序自检，不要把自检文本输出：
1. 住宿自检：统计所有非 null hotel 的 day 数，budget.total_hotels 是否大致覆盖这些晚数的住宿费用。
2. 门票自检：统计所有景点成人单人票价之和，并确认 budget.total_attractions 体现 PlannerContext.party.total。
3. 餐饮自检：检查 lunch/dinner 的 estimated_cost 是否是整组人费用；如果是多人同行，不要出现明显像单人价的正餐费用。
4. 档位自检：limited/economy 可以节省；standard/comfortable 要正常；premium/luxury 不要做成穷游。
"""


ROOM_PERSON_PRICE_LITE_RULE = """价格口径覆盖规则:
以下规则覆盖上文所有“酒店全体同行每晚费用、餐饮整组单餐费用”的旧说法。
- hotel.estimated_cost 表示“单间每晚房价”，按两人一间估算房间数：rooms = ceil(PlannerContext.party.total / 2)。
- meal.estimated_cost 表示“人均单餐费用”，不是整组费用。
- attraction.ticket_price 仍表示成人单人门票。
"""


ROOM_PERSON_PRICE_FULL_RULE = """两人一间与人均餐费预算规则:
以下规则覆盖上文所有旧预算口径。
- hotel.estimated_cost 必须复制 hotel_pois.estimated_cost_hint，含义是“单间每晚房价”。
- 酒店总价必须体现房间数和住宿晚数：budget.total_hotels = 所有非 null day.hotel.estimated_cost 之和 × rooms，其中 rooms = ceil(PlannerContext.party.total / 2)。
- meal.estimated_cost 必须复制 food_pois.meal_cost_hint 或合法 fallback，含义是“人均单餐费用”。
- 餐饮总价必须体现人数：budget.total_meals = 所有 day.meals[].estimated_cost 之和 × PlannerContext.party.total。
- attraction.ticket_price 是成人单人门票，budget.total_attractions = 所有 ticket_price 之和 × PlannerContext.party.total。
- budget.total 可以后续由系统重算；但酒店房间数、餐饮人均价、景点单人票价这些业务口径不能错。
"""


ROOM_PERSON_PRICE_SELF_CHECK_RULE = """两人一间与人均餐费自检:
最终输出 JSON 前，内部按下面顺序自检，不要输出自检文本：
1. 计算同行人数 party.total，并计算 rooms = ceil(party.total / 2)。
2. 检查 hotel.estimated_cost 是否是“单间每晚价”，total_hotels 是否大致体现 rooms × 住宿晚数。
3. 检查 meal.estimated_cost 是否是“人均单餐价”，多人同行时 total_meals 是否大致体现乘以 party.total。
4. 检查 attraction.ticket_price 是否是“成人单人门票”，景点预算是否体现 party.total。
5. 如果预算总额和这些口径冲突，优先保证业务口径正确，不要通过少算房间数、少乘人数来凑预算。
"""


VARIANT_RULES = {
    "attraction_dedupe_only": [ATTRACTION_DEDUPE_RULE],
    "attraction_source_guard_only": [ATTRACTION_SOURCE_GUARD_RULE],
    "attraction_dedupe_source_guard": [ATTRACTION_DEDUPE_RULE, ATTRACTION_SOURCE_GUARD_RULE],
    "attraction_dedupe_source_self_check": [
        ATTRACTION_DEDUPE_RULE,
        ATTRACTION_SOURCE_GUARD_RULE,
        ATTRACTION_SELF_CHECK_RULE,
    ],
    "budget_hard": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE],
    "budget_order": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE, BUDGET_ORDER_RULE],
    "budget_fewshot": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE, BUDGET_ORDER_RULE, BUDGET_FEWSHOT_RULE],
    "budget_symbolic": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE, BUDGET_ORDER_RULE, BUDGET_SYMBOLIC_RULE],
    "budget_ledger": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE, BUDGET_ORDER_RULE, BUDGET_LEDGER_RULE],
    "budget_ledger_no_schema_numbers": [MEAL_FALLBACK_RULE, BUDGET_HARD_RULE, BUDGET_ORDER_RULE, BUDGET_LEDGER_RULE],
    "budget_relation_lite": [MEAL_FALLBACK_RULE, BUDGET_RELATION_LITE_RULE],
    "budget_relation_priority": [MEAL_FALLBACK_RULE, BUDGET_RELATION_LITE_RULE, BUDGET_RELATION_PRIORITY_RULE],
    "budget_relation_self_check": [
        MEAL_FALLBACK_RULE,
        BUDGET_RELATION_LITE_RULE,
        BUDGET_RELATION_PRIORITY_RULE,
        BUDGET_RELATION_SELF_CHECK_RULE,
    ],
    "room_person_price_lite": [MEAL_FALLBACK_RULE, ROOM_PERSON_PRICE_LITE_RULE],
    "room_person_price_full": [MEAL_FALLBACK_RULE, ROOM_PERSON_PRICE_LITE_RULE, ROOM_PERSON_PRICE_FULL_RULE],
    "room_person_price_self_check": [
        MEAL_FALLBACK_RULE,
        ROOM_PERSON_PRICE_LITE_RULE,
        ROOM_PERSON_PRICE_FULL_RULE,
        ROOM_PERSON_PRICE_SELF_CHECK_RULE,
    ],
    "budget_symbolic_meal_semantic": [
        MEAL_SEMANTIC_FALLBACK_RULE,
        BUDGET_HARD_RULE,
        BUDGET_ORDER_RULE,
        BUDGET_SYMBOLIC_RULE,
    ],
    "meal_count_limit_symbolic": [
        MEAL_FALLBACK_RULE,
        MEAL_COUNT_LIMIT_RULE,
        BUDGET_HARD_RULE,
        BUDGET_ORDER_RULE,
        BUDGET_SYMBOLIC_RULE,
    ],
    "meal_rotation_symbolic": [
        MEAL_FALLBACK_RULE,
        MEAL_ROTATION_RULE,
        BUDGET_HARD_RULE,
        BUDGET_ORDER_RULE,
        BUDGET_SYMBOLIC_RULE,
    ],
    "meal_grounded_diversity_symbolic": [
        MEAL_FALLBACK_RULE,
        MEAL_GROUNDED_DIVERSITY_RULE,
        BUDGET_HARD_RULE,
        BUDGET_ORDER_RULE,
        BUDGET_SYMBOLIC_RULE,
    ],
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """读取 JSONL。"""
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """覆盖写 JSONL。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_rules(text: str, variant: str, title: str) -> str:
    """给 prompt 追加消融规则块。"""
    rules = "\n".join(VARIANT_RULES[variant])
    return f"{text.rstrip()}\n\n{title}（{variant}）:\n{rules.strip()}\n"


def strip_numeric_schema_example(text: str) -> str:
    """移除 system prompt 中带具体数字的 JSON 示例，避免预算数字污染。"""
    start = text.find("字段结构示例:")
    end = text.find("\n\n规划规则:", start)
    if start < 0 or end < 0:
        return text
    replacement = """字段结构要求:
必须输出符合 TripPlan schema 的顶层 JSON 对象，字段包括 city/start_date/end_date/days/weather_info/overall_suggestions/budget。
不要在提示词里模仿任何示例数字；所有日期、名称、价格、预算都必须来自当前 PlannerContext 和最终 days 数组。"""
    return f"{text[:start].rstrip()}\n\n{replacement}{text[end:]}"


def build_variant_records(records: list[dict[str, Any]], variant: str, source_records: Path) -> list[dict[str, Any]]:
    """构造某个 prompt variant 的 records。"""
    now = datetime.now(timezone.utc).isoformat()
    output = []
    for record in records:
        row = dict(record)
        system_prompt = str(row.get("system_prompt") or "")
        if variant == "budget_ledger_no_schema_numbers":
            system_prompt = strip_numeric_schema_example(system_prompt)
        row["system_prompt"] = append_rules(system_prompt, variant, "Prompt 消融附加系统规则")
        row["planner_query"] = append_rules(str(row.get("planner_query") or ""), variant, "Prompt 消融附加执行规则")
        row["prompt_variant"] = variant
        row["prompt_variant_source_records"] = str(source_records)
        row["prompt_variant_created_at"] = now

        metadata = dict(row.get("metadata") or {})
        metadata.update(
            {
                "prompt_variant": variant,
                "prompt_variant_source_records": str(source_records),
                "prompt_chars": len(row["planner_query"]),
                "system_prompt_chars": len(row["system_prompt"]),
                "prompt_variant_created_at": now,
            }
        )
        row["metadata"] = metadata
        output.append(row)
    return output


def write_summary(path: Path, variant: str, records: list[dict[str, Any]], source_records: Path) -> None:
    """写一份很短的中文说明，方便之后回看。"""
    lines = [
        f"# Prompt 消融记录：{variant}",
        "",
        f"- 来源 records：`{source_records}`",
        f"- 样本数：{len(records)}",
        "- 改动范围：只追加 system_prompt 和 planner_query 规则，不改变 request/planner_context/tool_snapshot。",
        "- 共同餐饮规则：lunch/dinner 宁可重复真实 food_pois，也不能写无、空、酒店晚餐或泛化餐厅。",
        "",
        "## 附加规则",
        "",
        "```text",
        "\n".join(VARIANT_RULES[variant]).strip(),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 prompt 消融 frozen records")
    parser.add_argument("--input-records", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, default=Path("training/data/planner"))
    parser.add_argument("--name-prefix", default="eval_harder_food_bucket_meal_ablation")
    parser.add_argument("--variants", default=",".join(VARIANT_ORDER))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = read_jsonl(args.input_records)
    variants = [item.strip() for item in args.variants.split(",") if item.strip()]
    unknown = [item for item in variants if item not in VARIANT_RULES]
    if unknown:
        raise ValueError(f"未知 variant: {unknown}; 可选: {sorted(VARIANT_RULES)}")

    for variant in variants:
        output_dir = args.output_root / f"{args.name_prefix}_{variant}_no_route"
        output_records = build_variant_records(records, variant, args.input_records)
        write_jsonl(output_dir / "records.jsonl", output_records)
        write_summary(output_dir / "prompt消融说明.md", variant, output_records, args.input_records)
        print(f"{variant}: {len(output_records)} -> {output_dir / 'records.jsonl'}")


if __name__ == "__main__":
    main()
