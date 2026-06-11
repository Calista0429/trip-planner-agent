#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -lt 3 ]]; then
  echo "usage: $0 LOG_FILE PID_CSV PORT_CSV" >&2
  exit 2
fi

LOG_FILE="$1"
PID_CSV="$2"
PORT_CSV="$3"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
cd "${PROJECT_ROOT}"

mkdir -p "$(dirname "${LOG_FILE}")"

IFS=',' read -r -a PIDS <<< "${PID_CSV}"
IFS=',' read -r -a PORTS <<< "${PORT_CSV}"

ts() {
  date "+%F %T"
}

echo "[$(ts)] watcher started; pids=${PID_CSV}; ports=${PORT_CSV}" >> "${LOG_FILE}"

SERVICE_PGIDS=()
for port in "${PORTS[@]}"; do
  state_file="training/outputs/model_service/pids/planner_model_${port}.json"
  if [[ ! -f "${state_file}" ]]; then
    continue
  fi
  pgid="$(
    .venv-training-py311/bin/python3 - "${state_file}" <<'PY_INNER' || true
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    state = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)
pgid = state.get("pgid")
if pgid:
    print(pgid)
PY_INNER
  )"
  if [[ -n "${pgid}" ]]; then
    SERVICE_PGIDS+=("${pgid}")
  fi
done
echo "[$(ts)] service_pgids=${SERVICE_PGIDS[*]:-none}" >> "${LOG_FILE}"

while true; do
  alive=0
  for pid in "${PIDS[@]}"; do
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      alive=$((alive + 1))
    fi
  done
  echo "[$(ts)] alive_local_generators=${alive}" >> "${LOG_FILE}"
  if [[ "${alive}" -eq 0 ]]; then
    break
  fi
  sleep 60
done

echo "[$(ts)] local generators finished; stopping vLLM services" >> "${LOG_FILE}"
for port in "${PORTS[@]}"; do
  if [[ -z "${port}" ]]; then
    continue
  fi
  .venv-training-py311/bin/python3 training/scripts/serving/manage_planner_service.py stop \
    --port "${port}" \
    --timeout 30 \
    --kill >> "${LOG_FILE}" 2>&1 || true
done

if [[ "${#SERVICE_PGIDS[@]}" -gt 0 ]]; then
  echo "[$(ts)] verifying real GPU-owning process groups" >> "${LOG_FILE}"
  .venv-training-py311/bin/python3 - "${SERVICE_PGIDS[@]}" >> "${LOG_FILE}" 2>&1 <<'PY_CLEANUP' || true
import os
import signal
import subprocess
import sys
import time

pgids = {int(value) for value in sys.argv[1:] if value.strip()}
if not pgids:
    raise SystemExit(0)

def pgid_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

def gpu_pids_for_pgids() -> list[tuple[int, int, str, str]]:
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    rows: list[tuple[int, int, str, str]] = []
    for line in result.stdout.splitlines():
        parts = [part.strip() for part in line.split(",", 2)]
        if len(parts) < 3:
            continue
        try:
            pid = int(parts[0])
            pgid = os.getpgid(pid)
        except (ProcessLookupError, PermissionError, ValueError):
            continue
        if pgid in pgids:
            rows.append((pid, pgid, parts[1], parts[2]))
    return rows

for pid, pgid, name, mem in gpu_pids_for_pgids():
    print(f"residual_gpu_process before cleanup: pid={pid} pgid={pgid} name={name} used_memory_mib={mem}", flush=True)

for pgid in sorted(pgids):
    if pgid_alive(pgid):
        print(f"cleanup SIGTERM pgid={pgid}", flush=True)
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass

time.sleep(5)
for pgid in sorted(pgids):
    if pgid_alive(pgid):
        print(f"cleanup SIGKILL pgid={pgid}", flush=True)
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

time.sleep(3)
leftovers = gpu_pids_for_pgids()
if leftovers:
    for pid, pgid, name, mem in leftovers:
        print(f"WARNING residual_gpu_process after cleanup: pid={pid} pgid={pgid} name={name} used_memory_mib={mem}", flush=True)
else:
    print("gpu_process_cleanup_verified=true", flush=True)
PY_CLEANUP
fi

echo "[$(ts)] watcher done" >> "${LOG_FILE}"
