#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../../../.."

PY=".venv-training-py311/bin/python3"
BASE_DIR="training/data/planner/sft"
AUDIT_DIR="training/outputs/eval/audits"
TEACHER_MODEL_PROVIDER="${TEACHER_MODEL_PROVIDER:-deepseek}"
TEACHER_MODEL="${TEACHER_MODEL:-}"
AMAP_QPS_LIMIT="${AMAP_QPS_LIMIT:-3}"

teacher_args=(--teacher-model-provider "${TEACHER_MODEL_PROVIDER}")
if [[ -n "${TEACHER_MODEL}" ]]; then
  teacher_args+=(--teacher-model "${TEACHER_MODEL}")
fi

run_one() {
  local name="$1"
  local start_index="$2"
  local count="$3"
  local target_successes="$4"
  local budget_mix="$5"
  local output_dir="${BASE_DIR}/${name}"
  local audit_root="${AUDIT_DIR}/${name}_records_audit"
  local fit_dir="${audit_root}/budget_fit"
  local usability_dir="${audit_root}/usability"

  echo "=== ${name} ==="
  echo "start=$(date -Is) target_successes=${target_successes} max_launches=${count} mix=${budget_mix}"

  "${PY}" training/scripts/planner/data/generate_sft_data.py \
    --count "${count}" \
    --target-successes "${target_successes}" \
    --start-index "${start_index}" \
    --request-source controlled \
    --date-mode mixed \
    --workers 50 \
    --sample-retries 3 \
    "${teacher_args[@]}" \
    --amap-qps-limit "${AMAP_QPS_LIMIT}" \
    --target-budget-mix "${budget_mix}" \
    --disallow-budget-strictness-none \
    --output-dir "${output_dir}"

  "${PY}" training/scripts/planner/audit/audit_sft_budget_fit.py \
    --records "${output_dir}/records.jsonl" \
    --output-dir "${fit_dir}"

  "${PY}" training/scripts/planner/audit/classify_sft_budget_usability.py \
    --audit-rows "${fit_dir}/audit_rows.jsonl" \
    --output-dir "${usability_dir}"

  echo "end=$(date -Is) output=${output_dir}"
}

run_one "260509_supplement_standard520_w50_no_none" 412000 760 520 "standard/soft=470,standard/hard=50"
run_one "260509_supplement_comfortable245_w50_no_none" 413000 380 245 "comfortable/soft=245"
run_one "260509_supplement_premium157_w50_no_none" 414000 520 157 "premium/soft=157"

echo "all_done=$(date -Is)"
