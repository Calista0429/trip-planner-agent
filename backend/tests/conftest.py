"""Test infrastructure: sys.path injection + golden snapshot helper.

These golden (characterization/snapshot) tests do not assert that the business
logic is "correct"; they pin the *current* output of the pure functions under
`planner/` as a baseline. The planned LangGraph refactor keeps this domain logic
and rewrites only the outer orchestration -- if pricing/scoring is silently
broken while moving code around, the golden files fail immediately.

Usage:
    # First time, or when intentionally updating the baseline, regenerate golden
    UPDATE_GOLDEN=1 pytest
    # Normal regression run (missing golden fails loudly, never silently passes)
    pytest
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# Make `import app...` work from any cwd by putting the backend dir on sys.path.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

GOLDEN_DIR = Path(__file__).parent / "golden"
UPDATE_GOLDEN = os.getenv("UPDATE_GOLDEN") == "1"


def _to_jsonable(value: Any) -> Any:
    """Convert Pydantic models / dataclasses into a stable serializable shape."""
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in vars(value).items()}
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def _serialize(value: Any) -> str:
    return json.dumps(
        _to_jsonable(value),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        default=str,
    )


def assert_golden(name: str, value: Any) -> None:
    """Compare value against golden/<name>.json.

    - UPDATE_GOLDEN=1: write the file (regenerate baseline).
    - Otherwise: a missing file fails loudly (never silently passes); an existing
      file is compared as exact serialized strings.
    """
    path = GOLDEN_DIR / f"{name}.json"
    serialized = _serialize(value)

    if UPDATE_GOLDEN:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(serialized + "\n", encoding="utf-8")
        return

    if not path.exists():
        pytest.fail(
            f"Missing golden baseline: {path.relative_to(BACKEND_DIR)}\n"
            f"Generate it first with: UPDATE_GOLDEN=1 pytest"
        )

    expected = path.read_text(encoding="utf-8").rstrip("\n")
    assert serialized == expected, (
        f"Golden baseline mismatch: {name}\n"
        f"If this is an intentional logic change, regenerate with "
        f"UPDATE_GOLDEN=1 pytest and review the diff by hand."
    )


@pytest.fixture
def golden():
    """Expose assert_golden as a fixture for direct injection into tests."""
    return assert_golden
