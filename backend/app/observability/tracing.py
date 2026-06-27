"""LangSmith tracing seam.

A complete no-op unless ``LANGSMITH_TRACING`` is truthy AND the ``langsmith``
package is importable. Decorators degrade to identity pass-throughs so the
default planner flow is unchanged with zero added latency.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Mapping

logger = logging.getLogger(__name__)

_TRUTHY = {"1", "true", "yes", "on"}
_warned = False


def _env_on() -> bool:
    return os.getenv("LANGSMITH_TRACING", "").strip().lower() in _TRUTHY


def tracing_enabled() -> bool:
    """True only when the env switch is on and langsmith can be imported."""
    if not _env_on():
        return False
    try:
        import langsmith  # noqa: F401
    except Exception:
        return False
    return True


def init_tracing() -> None:
    """Call once at startup. Warns once if env is on but langsmith is missing."""
    global _warned
    if _env_on() and not tracing_enabled() and not _warned:
        logger.warning(
            "LANGSMITH_TRACING is set but the 'langsmith' package is not "
            "importable; tracing disabled."
        )
        _warned = True


def traceable(*dargs: Any, **dkwargs: Any) -> Callable:
    """Safe @traceable. Identity decorator when tracing is disabled."""

    def _decorator(func: Callable) -> Callable:
        if not tracing_enabled():
            return func
        from langsmith import traceable as _ls_traceable

        return _ls_traceable(*dargs, **dkwargs)(func)

    if len(dargs) == 1 and callable(dargs[0]) and not dkwargs:
        return _decorator(dargs[0])
    return _decorator


def wrap_client(client: Any) -> Any:
    """Wrap an OpenAI client with langsmith.wrap_openai when enabled."""
    if not tracing_enabled():
        return client
    try:
        from langsmith.wrappers import wrap_openai

        return wrap_openai(client)
    except Exception:
        logger.warning(
            "Failed to wrap OpenAI client for LangSmith; tokens will not be "
            "traced.",
            exc_info=True,
        )
        return client


def attach_run_metadata(metadata: Mapping[str, Any]) -> None:
    """Attach metadata to the current run tree (e.g. failures, status)."""
    if not tracing_enabled():
        return
    try:
        from langsmith.run_helpers import get_current_run_tree

        rt = get_current_run_tree()
        if rt is not None:
            rt.add_metadata(dict(metadata))
    except Exception:
        pass
