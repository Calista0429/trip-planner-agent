import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "eval"))

DATASET = os.path.join(ROOT, "eval", "datasets", "human_eval_30.jsonl")


def test_dataset_rows_have_required_shape():
    rows = [json.loads(line) for line in open(DATASET, encoding="utf-8") if line.strip()]
    assert len(rows) == 30
    for row in rows:
        assert "request" in row["inputs"]
        req = row["inputs"]["request"]
        assert req.get("city")
        assert req.get("travel_days")
        assert "budget_amount" in row["outputs"]
        assert row["metadata"]["source"] == "human_eval_30"


def test_load_examples_maps_rows():
    import upload_dataset  # eval/upload_dataset.py via sys.path

    examples = upload_dataset.load_examples(DATASET)
    assert len(examples) == 30
    assert examples[0]["inputs"]["request"]["city"]
