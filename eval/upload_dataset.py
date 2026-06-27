"""Push the curated dataset to LangSmith (idempotent by dataset name)."""
from __future__ import annotations

import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datasets", "human_eval_30.jsonl")


def load_examples(path: str = DEFAULT_PATH) -> list[dict]:
    examples = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                examples.append(json.loads(line))
    return examples


def upload(dataset_name: str = "human_eval_30", path: str = DEFAULT_PATH) -> None:
    from langsmith import Client

    client = Client()
    examples = load_examples(path)

    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(dataset_name=dataset_name)

    client.create_examples(
        dataset_id=dataset.id,
        inputs=[e["inputs"] for e in examples],
        outputs=[e.get("outputs") for e in examples],
        metadata=[e.get("metadata") for e in examples],
    )
    print(f"uploaded {len(examples)} examples to dataset '{dataset_name}'")


if __name__ == "__main__":
    upload()
