"""旅行规划API路由"""

import asyncio
import os

from fastapi import APIRouter, HTTPException
from ...models.schemas import (
    TripRequest,
    TripPlanResponse,
    ErrorResponse
)
from ...config import get_settings
from ...agents.trip_planner_agent import get_trip_planner_agent

router = APIRouter(prefix="/trip", tags=["旅行规划"])


def _plan_with_legacy_agent(request: TripRequest):
    """Run the legacy MultiAgentTripPlanner and return (plan, status, message)."""
    agent = get_trip_planner_agent()
    trip_plan = agent.plan_trip(request)
    status = getattr(agent, "last_generation_status", "unknown")
    message = getattr(agent, "last_generation_message", "") or "旅行计划生成完成"
    return trip_plan, status, message


def _plan_with_graph(request: TripRequest):
    """Run the LangGraph pipeline and return (plan, status, message)."""
    from ...graph.service import generate_trip_plan

    result = generate_trip_plan(request)
    return result.plan, result.status, result.message


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        settings = get_settings()
        use_graph = settings.use_langgraph_planner
        backend = "langgraph" if use_graph else "legacy-agent"

        print(f"\n{'='*60}")
        print(f"[trip] incoming plan request (backend={backend})")
        print(f"   city: {request.city}")
        print(f"   dates: {request.start_date} - {request.end_date}")
        print(f"   days: {request.travel_days}")
        print(f"{'='*60}\n")

        # Both planners do blocking LLM work; run them off the event loop.
        planner = _plan_with_graph if use_graph else _plan_with_legacy_agent
        trip_plan, generation_status, generation_message = await asyncio.to_thread(
            planner, request
        )

        if generation_status == "fallback_success":
            print(f"[trip] returning fallback response: {generation_message}\n")
        else:
            print(f"[trip] returning response: {generation_message}\n")

        return TripPlanResponse(
            success=True,
            message=generation_message,
            data=trip_plan
        )

    except Exception as e:
        print(f"[trip] failed to generate plan: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """Lightweight liveness check reporting the active planner backend.

    Deliberately avoids constructing the planner/LLM clients so polling stays
    cheap and never 503s on transient init issues. (The previous version read
    agent.agent.name, an attribute MultiAgentTripPlanner never had, so it always
    crashed.)
    """
    settings = get_settings()
    backend = "langgraph" if settings.use_langgraph_planner else "legacy-agent"
    llm_configured = bool(os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))

    return {
        "status": "healthy",
        "service": "trip-planner",
        "backend": backend,
        "amap_configured": bool(settings.amap_api_key),
        "llm_configured": llm_configured,
    }
