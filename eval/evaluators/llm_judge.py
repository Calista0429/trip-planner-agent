# eval/evaluators/llm_judge.py
"""LLM-as-judge evaluator. Scores delivered plan 0-5, normalized to [0,1]."""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from app.models.schemas import TripPlan, TripRequest

from deterministic import plan_from_run, request_from_example

_RUBRIC = (
    "你是挑剔但公正的旅行者。请仅评估这份行程计划本身：如果你真要照它出门，好用吗？\n"
    "从任务完成度、动线/体验、节奏、偏好与自由文本诉求契合度综合判断。\n"
    "先用3-5句证据说理，再打分。锚定：0无用 1严重不可用 2低于预期 3基本合格 4良好 5卓越。\n"
    "只输出一个 JSON：{\"reasoning\": \"...\", \"score\": <0-5整数>}。"
)


def _extract_judge_json(raw: str) -> dict:
    """Extract a JSON object from judge output (fenced block or bare JSON)."""
    # Try ```json ... ``` block first
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Try bare ``` ... ``` block
    m = re.search(r"```\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    # Try the whole string stripped
    return json.loads(raw.strip())


def build_judge_prompt(req: TripRequest, plan: TripPlan) -> str:
    return (
        f"{_RUBRIC}\n\n"
        f"用户请求：\n{req.model_dump_json(exclude_none=True)}\n\n"
        f"行程计划：\n{plan.model_dump_json(exclude_none=True)}\n"
    )


def parse_judge(raw: str) -> tuple[float, str]:
    try:
        obj = _extract_judge_json(raw)
    except Exception:
        return 0.0, f"unparseable judge output: {raw[:200]}"
    score = float(obj.get("score", 0) or 0)
    score = max(0.0, min(5.0, score))
    return score, str(obj.get("reasoning", ""))


def make_llm_judge(invoke_fn: Callable[[list[dict]], str] | None = None):
    if invoke_fn is None:
        from app.services.llm_service import get_llm

        _llm = get_llm()

        def invoke_fn(messages: list[dict]) -> str:  # noqa: F811
            return _llm.invoke(messages)

    def llm_judge(run: Any, example: Any) -> dict:
        plan = plan_from_run(run)
        if plan is None:
            return {"key": "llm_judge", "score": 0.0, "comment": "no plan"}
        req = request_from_example(example)
        prompt = build_judge_prompt(req, plan)
        raw = invoke_fn([{"role": "user", "content": prompt}])
        score, reason = parse_judge(raw)
        return {"key": "llm_judge", "score": round(score / 5.0, 4), "comment": reason}

    return llm_judge
