"""Critic Agent 两层评审测试（全离线：确定性层 + 注入 FakeLLM）。"""

from app.agents.critic import SEVERITY_BLOCKING, CriticAgent

from .builders import bad_ungrounded_plan, good_grounded_plan, make_context, make_request

GOOD_CONTEXT = make_context(
    attraction_names=["故宫博物院"],
    hotel_names=["如家酒店"],
    food_names=["庆丰包子铺", "四季民福烤鸭", "南门涮肉"],
)
EMPTY_CONTEXT = make_context(attraction_names=[], hotel_names=[], food_names=[])


class RecordingLLM:
    """记录调用次数的假 LLM。"""

    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def invoke(self, messages, **kwargs):
        self.calls += 1
        return self.response


def test_deterministic_blocks_and_gates_out_llm():
    req = make_request()
    plan = bad_ungrounded_plan(req)
    llm = RecordingLLM('{"verdict":"pass","violations":[]}')

    report = CriticAgent(llm=llm).review(plan, req, EMPTY_CONTEXT)

    assert report.verdict == "revise"
    codes = {v.code for v in report.violations}
    assert "budget_overspend" in codes
    assert "hallucinated_attraction" in codes
    # 门控：第一层有 blocking → 绝不调 LLM
    assert llm.calls == 0


def test_clean_plan_runs_llm_and_passes():
    req = make_request()
    plan = good_grounded_plan(req)
    llm = RecordingLLM('{"verdict":"pass","violations":[]}')

    report = CriticAgent(llm=llm).review(plan, req, GOOD_CONTEXT)

    assert llm.calls == 1  # 规则干净 → 调用 LLM
    assert report.verdict == "pass"
    assert report.violations == []


def test_llm_blocking_violation_surfaces():
    req = make_request()
    plan = good_grounded_plan(req)
    llm = RecordingLLM(
        'noise {"verdict":"revise","violations":[{"code":"persona_unfit",'
        '"severity":"blocking","where":{"day_index":0,"field":"attractions"},'
        '"detail":"带娃不适配","fix_hint":"换亲子点"}]} trailing'
    )

    report = CriticAgent(llm=llm).review(plan, req, GOOD_CONTEXT)

    assert report.verdict == "revise"
    assert any(
        v.code == "persona_unfit" and v.severity == SEVERITY_BLOCKING
        for v in report.violations
    )
    assert report.blocking_codes() == frozenset({"persona_unfit"})


def test_llm_unknown_code_discarded():
    req = make_request()
    plan = good_grounded_plan(req)
    llm = RecordingLLM('{"verdict":"revise","violations":[{"code":"made_up","severity":"blocking"}]}')

    report = CriticAgent(llm=llm).review(plan, req, GOOD_CONTEXT)

    # 越界 code 丢弃 → 无 blocking → pass
    assert report.verdict == "pass"
    assert report.violations == []


def test_no_llm_means_rules_only_pass():
    req = make_request()
    plan = good_grounded_plan(req)

    report = CriticAgent(llm=None).review(plan, req, GOOD_CONTEXT)

    assert report.verdict == "pass"
    assert not report.has_blocking()
