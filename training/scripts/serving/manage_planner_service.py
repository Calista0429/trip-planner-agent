#!/usr/bin/env python3
"""Start/stop/status helper for the local trip planner model service.

The LLaMA-Factory launcher can leave a child ``llamafactory-cli`` process alive
if only the wrapper process is killed.  This helper starts the service in its
own process group and records both PID and PGID, so stop/restart can reliably
clean the whole tree.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PYTHON = PROJECT_ROOT / ".venv-training-py311/bin/python3"
SERVE_SCRIPT = PROJECT_ROOT / "training/scripts/serving/serve_planner_model.py"
STATE_DIR = PROJECT_ROOT / "training/outputs/model_service"
PID_DIR = STATE_DIR / "pids"
DEFAULT_LOG_DIR = PROJECT_ROOT / "training/outputs/qwen25_7b"

DEFAULT_PORT = 4396
DEFAULT_VARIANT = "base"
DEFAULT_BACKEND = "vllm"
DEFAULT_DEVICES = "4,5,6,7"
DEFAULT_API_MODEL = "trip-planner-base"


def pidfile_for(port: int) -> Path:
    return PID_DIR / f"planner_model_{port}.json"


def read_state(port: int) -> dict[str, Any] | None:
    path = pidfile_for(port)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_state(port: int, state: dict[str, Any]) -> None:
    PID_DIR.mkdir(parents=True, exist_ok=True)
    pidfile_for(port).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_state(port: int) -> None:
    pidfile_for(port).unlink(missing_ok=True)


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_capture(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)


def port_pids(port: int) -> set[int]:
    result = run_capture(["ss", "-ltnp"])
    pids: set[int] = set()
    marker = f":{port} "
    for line in result.stdout.splitlines():
        if marker not in line:
            continue
        # Example: users:(("llamafactory-cl",pid=3016077,fd=87))
        for chunk in line.split("pid=")[1:]:
            digits = []
            for char in chunk:
                if char.isdigit():
                    digits.append(char)
                else:
                    break
            if digits:
                pids.add(int("".join(digits)))
    return pids


def proc_info(pid: int) -> tuple[str, int, str] | None:
    result = run_capture(["ps", "-p", str(pid), "-o", "user=", "-o", "pgid=", "-o", "cmd="])
    if result.returncode != 0 or not result.stdout.strip():
        return None
    line = result.stdout.strip()
    parts = line.split(None, 2)
    if len(parts) < 3:
        return None
    user, pgid, cmd = parts
    return user, int(pgid), cmd


def safe_pgid_from_port_pid(pid: int) -> int | None:
    info = proc_info(pid)
    if info is None:
        return None
    user, pgid, cmd = info
    if user != getpass.getuser():
        return None
    safe_markers = [
        "helloagents-trip-planner",
        ".serve_qwen25_7b",
        "serve_planner_model.py",
        "llamafactory-cli api",
    ]
    if not any(marker in cmd for marker in safe_markers):
        return None
    return pgid


def wait_until_port_closed(port: int, timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not port_pids(port):
            return True
        time.sleep(0.5)
    return not port_pids(port)


def kill_pgid(pgid: int, sig: signal.Signals) -> bool:
    try:
        os.killpg(pgid, sig)
        return True
    except ProcessLookupError:
        return False
    except PermissionError as exc:
        print(f"permission denied killing pgid={pgid}: {exc}", file=sys.stderr)
        return False


def status(args: argparse.Namespace) -> int:
    state = read_state(args.port)
    print(f"port: {args.port}")
    if state:
        pid = int(state.get("pid", 0))
        pgid = int(state.get("pgid", 0))
        print(f"pidfile: {pidfile_for(args.port)}")
        print(f"state pid={pid} alive={process_alive(pid)} pgid={pgid} group_alive={process_group_alive(pgid)}")
        print(f"log: {state.get('log_file')}")
        print(f"cmd: {' '.join(state.get('cmd', []))}")
    else:
        print("pidfile: missing")

    pids = sorted(port_pids(args.port))
    if pids:
        print(f"listening pids: {', '.join(map(str, pids))}")
        for pid in pids:
            info = proc_info(pid)
            if info:
                user, pgid, cmd = info
                print(f"  pid={pid} user={user} pgid={pgid} cmd={cmd}")
    else:
        print("listening pids: none")
    return 0


def stop(args: argparse.Namespace) -> int:
    pgids: set[int] = set()
    state = read_state(args.port)
    if state:
        pgid = int(state.get("pgid", 0) or 0)
        if pgid and process_group_alive(pgid):
            pgids.add(pgid)

    for pid in port_pids(args.port):
        pgid = safe_pgid_from_port_pid(pid)
        if pgid:
            pgids.add(pgid)

    if not pgids:
        print(f"no local planner service found on port {args.port}")
        remove_state(args.port)
        return 0

    for pgid in sorted(pgids):
        print(f"stopping process group pgid={pgid} with SIGTERM")
        kill_pgid(pgid, signal.SIGTERM)

    if not wait_until_port_closed(args.port, args.timeout):
        print(f"port {args.port} still busy after {args.timeout}s")
        if args.kill:
            for pgid in sorted(pgids):
                print(f"forcing process group pgid={pgid} with SIGKILL")
                kill_pgid(pgid, signal.SIGKILL)
            wait_until_port_closed(args.port, 5)
        else:
            print("rerun stop with --kill if it refuses to exit", file=sys.stderr)
            return 1

    remove_state(args.port)
    print(f"stopped planner service on port {args.port}")
    return 0


def start(args: argparse.Namespace) -> int:
    existing = port_pids(args.port)
    if existing and not args.force:
        print(f"port {args.port} is already in use by pid(s): {', '.join(map(str, sorted(existing)))}", file=sys.stderr)
        print("run `status`, or `stop --kill`, or pass --force if you know what you are doing", file=sys.stderr)
        return 1

    log_file = args.log_file
    if log_file is None:
        DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = DEFAULT_LOG_DIR / f"serve_{args.port}_{args.api_model_name}.log"
    log_file = log_file.expanduser().resolve()
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(PYTHON),
        "-u",
        str(SERVE_SCRIPT),
        "--variant",
        args.variant,
        "--infer-backend",
        args.infer_backend,
        "--cuda-visible-devices",
        args.cuda_visible_devices,
        "--api-model-name",
        args.api_model_name,
        "--port",
        str(args.port),
    ]
    if args.model_path:
        cmd.extend(["--model-path", str(args.model_path)])
    if args.infer_backend == "vllm":
        cmd.extend(["--vllm-maxlen", str(args.vllm_maxlen), "--vllm-gpu-util", str(args.vllm_gpu_util)])
    if args.adapter_path:
        cmd.extend(["--adapter-path", str(args.adapter_path)])
    if args.no_adapter:
        cmd.append("--no-adapter")

    env = os.environ.copy()
    env.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

    with log_file.open("ab", buffering=0) as log:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )

    pgid = os.getpgid(proc.pid)
    state = {
        "pid": proc.pid,
        "pgid": pgid,
        "port": args.port,
        "variant": args.variant,
        "infer_backend": args.infer_backend,
        "cuda_visible_devices": args.cuda_visible_devices,
        "api_model_name": args.api_model_name,
        "model_path": str(args.model_path) if args.model_path else None,
        "log_file": str(log_file),
        "cmd": cmd,
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_state(args.port, state)
    print(f"started planner service pid={proc.pid} pgid={pgid} port={args.port}")
    print(f"log: {log_file}")
    print(f"endpoint: http://127.0.0.1:{args.port}/v1")
    print(f"api model: {args.api_model_name}")
    return 0


def restart(args: argparse.Namespace) -> int:
    stop_args = argparse.Namespace(port=args.port, timeout=args.timeout, kill=True)
    stop(stop_args)
    return start(args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the local trip planner model service.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--port", type=int, default=DEFAULT_PORT)

    status_parser = subparsers.add_parser("status", help="Show service status.")
    add_common(status_parser)
    status_parser.set_defaults(func=status)

    stop_parser = subparsers.add_parser("stop", help="Stop service by pidfile and port fallback.")
    add_common(stop_parser)
    stop_parser.add_argument("--timeout", type=float, default=20)
    stop_parser.add_argument("--kill", action="store_true", help="Escalate to SIGKILL if SIGTERM does not exit.")
    stop_parser.set_defaults(func=stop)

    start_parser = subparsers.add_parser("start", help="Start service in a managed process group.")
    add_common(start_parser)
    start_parser.add_argument("--variant", default=DEFAULT_VARIANT)
    start_parser.add_argument("--infer-backend", choices=["huggingface", "vllm", "sglang", "ktransformers"], default=DEFAULT_BACKEND)
    start_parser.add_argument("--cuda-visible-devices", "--devices", default=DEFAULT_DEVICES)
    start_parser.add_argument("--api-model-name", default=DEFAULT_API_MODEL)
    start_parser.add_argument("--model-path", type=Path, default=None, help="Base model path or HF repo id passed to serve_planner_model.py.")
    start_parser.add_argument("--adapter-path", type=Path, default=None)
    start_parser.add_argument("--no-adapter", action="store_true")
    start_parser.add_argument("--vllm-maxlen", type=int, default=32768)
    start_parser.add_argument("--vllm-gpu-util", type=float, default=0.85)
    start_parser.add_argument("--log-file", type=Path, default=None)
    start_parser.add_argument("--force", action="store_true", help="Start even if the port appears busy.")
    start_parser.set_defaults(func=start)

    restart_parser = subparsers.add_parser("restart", help="Stop then start service.")
    add_common(restart_parser)
    restart_parser.add_argument("--timeout", type=float, default=20)
    restart_parser.add_argument("--variant", default=DEFAULT_VARIANT)
    restart_parser.add_argument("--infer-backend", choices=["huggingface", "vllm", "sglang", "ktransformers"], default=DEFAULT_BACKEND)
    restart_parser.add_argument("--cuda-visible-devices", "--devices", default=DEFAULT_DEVICES)
    restart_parser.add_argument("--api-model-name", default=DEFAULT_API_MODEL)
    restart_parser.add_argument("--model-path", type=Path, default=None, help="Base model path or HF repo id passed to serve_planner_model.py.")
    restart_parser.add_argument("--adapter-path", type=Path, default=None)
    restart_parser.add_argument("--no-adapter", action="store_true")
    restart_parser.add_argument("--vllm-maxlen", type=int, default=32768)
    restart_parser.add_argument("--vllm-gpu-util", type=float, default=0.85)
    restart_parser.add_argument("--log-file", type=Path, default=None)
    restart_parser.add_argument("--force", action="store_true")
    restart_parser.set_defaults(func=restart)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
