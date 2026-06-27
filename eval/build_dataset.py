"""Freeze the ~30 human-eval requests into a LangSmith dataset jsonl.

Source: out/human_eval/plan_*.json (each has a full 'request'). Run once;
commit the resulting eval/datasets/human_eval_30.jsonl.
"""
from __future__ import annotations

import glob
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "eval", "datasets", "human_eval_30.jsonl")


def main() -> None:
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, "out", "human_eval", "plan_*.json"))):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        req = data["request"]
        bc = req.get("budget_constraint") or {}
        party = req.get("party") or {}
        rows.append(
            {
                "inputs": {"request": req},
                "outputs": {
                    "budget_amount": bc.get("amount"),
                    "budget_strictness": bc.get("strictness"),
                    "travel_days": req.get("travel_days"),
                },
                "metadata": {
                    "city": req.get("city"),
                    "travel_days": req.get("travel_days"),
                    "party_total": party.get("total"),
                    "tier": bc.get("strictness"),
                    "source": "human_eval_30",
                },
            }
        )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
