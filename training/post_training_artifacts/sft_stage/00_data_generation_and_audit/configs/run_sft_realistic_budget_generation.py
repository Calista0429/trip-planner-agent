"""Generate SFT records with the current budget request distribution.

This is a safe wrapper around generate_sft_data.py. It writes to an explicit
output directory instead of appending to training/data/planner/sft/records.jsonl.
It only materializes artifacts for the current run and does not depend on
archived clean sets or historical audit outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS_DIR = PROJECT_ROOT / "training" / "scripts"
EVAL_SCRIPT_DIR = SCRIPTS_DIR / "planner" / "eval"
if str(EVAL_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_SCRIPT_DIR))
DEFAULT_START_INDEX = 300000
DEFAULT_SEED = 42
_write_lock = threading.Lock()


import generate_sft_data as sft  # noqa: E402
from build_eval_set import choose_eval_budget_amount, replace_budget_amount_text  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate current-budget SFT records")
    parser.add_argument("--count", type=int, default=20, help="最多提交的 base 请求数")
    parser.add_argument("--target-successes", type=int, default=20, help="目标成功样本数；0 表示不追成功数")
    parser.add_argument("--max-submissions", type=int, default=80, help="追成功数时最多提交多少个不同请求")
    parser.add_argument("--start-index", type=int, default=DEFAULT_START_INDEX)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--date-mode", choices=["future", "mixed", "past"], default="mixed")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument(
        "--teacher-model-provider",
        "--data-gen-provider",
        dest="data_gen_provider",
        choices=["env", "deepseek", "mimo"],
        default=None,
        help="强模型配置 profile；默认使用 DATA_GEN_* / DeepSeek 环境变量，mimo 使用 MIMO_* 配置。",
    )
    parser.add_argument(
        "--teacher-model",
        "--data-gen-model",
        dest="data_gen_model",
        default=None,
        help="覆盖具体强模型 model id；不传则使用所选 provider 的环境变量默认值。",
    )
    parser.add_argument(
        "--amap-qps-limit",
        type=float,
        default=None,
        help="高德 HTTP API 进程内 QPS 限制；默认使用 AMAP_QPS_LIMIT 环境变量或 3，0 表示关闭限速。",
    )
    parser.add_argument("--sample-retries", type=int, default=3)
    parser.add_argument("--budget-context-min-ratio", type=float, default=0.95)
    parser.add_argument("--budget-context-retry-stride", type=int, default=1000)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-output-tokens", type=int, default=0)
    parser.add_argument("--output-base-tokens", type=int, default=int(os.getenv("PLANNER_OUTPUT_BASE_TOKENS", "5000")))
    parser.add_argument("--output-tokens-per-day", type=int, default=int(os.getenv("PLANNER_OUTPUT_TOKENS_PER_DAY", "2600")))
    parser.add_argument("--output-retry-tokens", type=int, default=int(os.getenv("PLANNER_OUTPUT_RETRY_TOKENS", "2000")))
    parser.add_argument("--output-tokens-cap", type=int, default=int(os.getenv("PLANNER_MAX_OUTPUT_TOKENS_CAP", "24000")))
    parser.add_argument("--historical-weather-provider", choices=["open-meteo", "none"], default="open-meteo")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.request_source = "controlled_realistic_budget"
    args.dry_run_requests = False
    args.dry_run_context = False
    sft.load_project_env()
    sft.configure_amap_qps_limit(args.amap_qps_limit)
    amap_api_key = os.getenv("AMAP_MAPS_API_KEY") or os.getenv("AMAP_API_KEY")
    if not amap_api_key:
        raise RuntimeError("缺少 AMAP_MAPS_API_KEY 或 AMAP_API_KEY")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(
        "开始生成 current-budget SFT records: "
        f"target={args.target_successes or args.count}, max_submissions={max_submission_count(args)}, "
        f"workers={args.workers}, teacher_provider={args.data_gen_provider or 'env'}, "
        f"teacher_model={args.data_gen_model or 'provider_default'}, output={args.output_dir}",
        flush=True,
    )

    ok, failed, launched = run_generation(args, amap_api_key)
    records = read_jsonl(records_path(args))
    train_rows, val_rows = split_train_val([sft.make_lf_row(row) for row in records], args.val_ratio)
    write_json(args.output_dir / "llamafactory_train.json", train_rows)
    write_json(args.output_dir / "llamafactory_val.json", val_rows)

    summary = build_summary(args, records, ok, failed, launched, len(train_rows), len(val_rows))
    write_json(args.output_dir / "summary.json", summary)
    (args.output_dir / "数据集说明.md").write_text(render_readme(summary), encoding="utf-8")

    print(
        "完成: "
        f"ok={ok}, failed={failed}, launched={launched}, records={len(records)}, "
        f"train={len(train_rows)}, val={len(val_rows)}",
        flush=True,
    )
    print(f"records={records_path(args)}")
    print(f"errors={errors_path(args)}")
    print(f"summary={args.output_dir / 'summary.json'}")


def max_submission_count(args: argparse.Namespace) -> int:
    if args.target_successes > 0:
        return max(args.max_submissions, args.target_successes)
    return args.count


def run_generation(args: argparse.Namespace, amap_api_key: str) -> tuple[int, int, int]:
    target_successes = args.target_successes if args.target_successes > 0 else args.count
    max_submissions = max_submission_count(args)
    pending: dict[Any, int] = {}
    next_offset = 0
    ok = 0
    failed = 0
    launched = 0
    max_workers = max(1, int(args.workers))

    def submit_next(executor: ThreadPoolExecutor) -> bool:
        nonlocal next_offset, launched
        if next_offset >= max_submissions:
            return False
        if args.target_successes > 0 and ok >= target_successes:
            return False
        index = args.start_index + next_offset
        next_offset += 1
        future = executor.submit(generate_one_by_index, index, args, amap_api_key)
        pending[future] = index
        launched += 1
        return True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while len(pending) < max_workers and submit_next(executor):
            pass
        while pending:
            for future in as_completed(list(pending)):
                index = pending.pop(future)
                try:
                    record = future.result()
                    append_jsonl(records_path(args), record)
                    append_jsonl(
                        requests_path(args),
                        record["request"] | {"request_id": record["record_id"], "control_spec": record.get("control_spec", {})},
                    )
                    ok += 1
                    print(f"progress: ok={ok}/{target_successes} failed={failed} launched={launched} last={record['record_id']}", flush=True)
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    append_jsonl(
                        errors_path(args),
                        {
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "record_id": sft.format_request_id(index),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    print(f"progress: ok={ok}/{target_successes} failed={failed} launched={launched} error={exc}", flush=True)

                if ok >= target_successes:
                    continue
                while len(pending) < max_workers and submit_next(executor):
                    pass
                break

    return ok, failed, launched


def generate_one_by_index(index: int, args: argparse.Namespace, amap_api_key: str) -> dict[str, Any]:
    request_id = sft.format_request_id(index)
    last_error: Exception | None = None
    candidate_index = index
    retry_stride = max(int(args.budget_context_retry_stride or args.count or 1), 1)
    for attempt in range(1, args.sample_retries + 1):
        try:
            raw_request = build_realistic_budget_request(candidate_index, args)
            record = sft.generate_one(raw_request, args, amap_api_key, sample_attempt=attempt)
            record["metadata"]["sample_attempt"] = attempt
            if candidate_index != index:
                record["metadata"]["base_request_id"] = request_id
            return record
        except sft.BudgetContextUnreachableError as exc:
            last_error = exc
            print(f"⚠️  {request_id} 第 {attempt}/{args.sample_retries} 次失败: {exc}", flush=True)
            candidate_index += retry_stride
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            print(f"⚠️  {request_id} 第 {attempt}/{args.sample_retries} 次失败: {exc}", flush=True)
    raise RuntimeError(f"{request_id} 样本生成失败: {last_error}") from last_error


def build_realistic_budget_request(index: int, args: argparse.Namespace) -> dict[str, Any]:
    base_args = argparse.Namespace(**vars(args))
    base_args.request_source = "controlled"
    raw = sft.generate_controlled_request(index, base_args)
    item = dict(raw)
    spec = dict(item.get("control_spec") or {})
    budget_constraint = dict(item.get("budget_constraint") or {})
    old_amount = int(budget_constraint.get("amount") or spec.get("budget_amount") or 0)
    old_level = str(budget_constraint.get("budget_level") or spec.get("budget_level") or "standard")
    budget_level = "premium" if old_level == "luxury" else old_level
    party = item.get("party") or {}
    city_tier = str(spec.get("city_tier") or sft.infer_city_tier(str(item.get("city") or "")))
    rng = random.Random(args.seed * 2017 + index)
    amount = choose_eval_budget_amount(
        rng,
        budget_level,
        int(party.get("total") or 1),
        int(item.get("travel_days") or 1),
        str(item.get("accommodation") or "舒适型酒店"),
        str(item.get("transportation") or "公共交通"),
        city_tier,
    )
    budget_constraint = sft.build_budget_constraint(
        rng,
        budget_level,
        amount,
        strictness=str(budget_constraint.get("strictness") or "soft"),
    )
    item["budget_constraint"] = budget_constraint
    item["free_text_input"] = replace_budget_amount_text(str(item.get("free_text_input") or ""), old_amount, amount)
    item["source"] = "controlled_realistic_budget"
    spec.update(
        {
            "budget_level": budget_level,
            "budget_amount": amount,
            "budget_strictness": budget_constraint["strictness"],
            "sft_budget_party_mode": "linear_person_shared_transport",
            "sft_budget_policy_version": "current_budget",
        }
    )
    item["control_spec"] = spec
    return item


def build_summary(
    args: argparse.Namespace,
    records: list[dict[str, Any]],
    ok: int,
    failed: int,
    launched: int,
    train_count: int,
    val_count: int,
) -> dict[str, Any]:
    budgets = [int(((row.get("request") or {}).get("budget_constraint") or {}).get("amount") or 0) for row in records]
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(args.output_dir),
        "request_source": "controlled_realistic_budget",
        "budget_policy_version": "current_budget",
        "teacher_model_provider": args.data_gen_provider or "env",
        "teacher_model": args.data_gen_model or "provider_default",
        "ok": ok,
        "failed": failed,
        "launched": launched,
        "records": len(records),
        "llamafactory_train": train_count,
        "llamafactory_val": val_count,
        "budget_level": dict(Counter(((row.get("control_spec") or {}).get("budget_level") or "unknown") for row in records)),
        "strictness": dict(Counter((((row.get("request") or {}).get("budget_constraint") or {}).get("strictness") or "unknown") for row in records)),
        "budget_amount": {
            "min": min(budgets) if budgets else 0,
            "p50": int(statistics.median(budgets)) if budgets else 0,
            "max": max(budgets) if budgets else 0,
        },
    }


def render_readme(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# SFT generation run",
            "",
            "按当前预算口径生成的 SFT 数据。",
            "",
            "## 口径",
            "",
            "- 请求分布沿用 controlled 近似真实分布。",
            "- 预算金额使用当前 `current_budget` 口径：餐饮/门票/体验按真实人数线性增长，住宿按两人一间，市内交通按队伍共享估算。",
            "- `luxury` 请求在本轮折到 `premium`，与当前预算训练口径保持一致。",
            "- 生成前启用候选池预算 gate，默认 `high_budget_ratio >= 0.95`。",
            "",
            "## 文件",
            "",
            f"- records：`{summary['output_dir']}/records.jsonl` ({summary['records']} 条)",
            f"- errors：`{summary['output_dir']}/errors.jsonl`",
            f"- LLaMAFactory train/val：{summary['llamafactory_train']} / {summary['llamafactory_val']}",
            "",
        ]
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def split_train_val(rows: list[dict[str, Any]], val_ratio: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows = list(rows)
    rng = random.Random(20260427)
    rng.shuffle(rows)
    val_size = max(1, int(len(rows) * val_ratio)) if len(rows) > 1 else 0
    return rows[val_size:], rows[:val_size]


def records_path(args: argparse.Namespace) -> Path:
    return args.output_dir / "records.jsonl"


def requests_path(args: argparse.Namespace) -> Path:
    return args.output_dir / "requests.jsonl"


def errors_path(args: argparse.Namespace) -> Path:
    return args.output_dir / "errors.jsonl"


if __name__ == "__main__":
    main()
