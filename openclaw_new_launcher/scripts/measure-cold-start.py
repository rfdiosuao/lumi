#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure OpenClaw cold start time")
    parser.add_argument("--root", default=str(Path.cwd()), help="Launcher root directory")
    parser.add_argument("--timeout-sec", type=int, default=600, help="Startup timeout in seconds")
    parser.add_argument("--stop-after-measure", action="store_true", help="Stop process after measurement")
    parser.add_argument("--output-path", default="", help="Where to write JSON output")
    return parser.parse_args()


def discover_python_root(root: Path) -> Path:
    candidates = [
        root / "python",
        root / "OpenClawFiles" / "_up_" / "python",
        root / "OpenClawFiles" / "python",
        root / "_up_" / "python",
    ]
    for candidate in candidates:
        if (candidate / "core" / "paths.py").exists():
            return candidate
    raise FileNotFoundError(f"Cannot locate launcher python package under {root}")


def load_service(root: Path):
    python_root = discover_python_root(root)
    sys.path.insert(0, str(python_root))

    from core.paths import AppPaths
    from core.constants import APP_PORT
    from services.process import OpenClawProcessService

    paths = AppPaths.discover()
    logs: list[str] = []

    def append_log(text: str) -> None:
        logs.append(text.rstrip("\r\n"))
        print(text, end="")

    def ui_call(*_args, **_kwargs) -> None:
        return None

    return paths, APP_PORT, OpenClawProcessService(paths, append_log, ui_call), logs


def read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    os.chdir(root)
    os.environ["OPENCLAW_STARTUP_TIMEOUT_SEC"] = str(args.timeout_sec)

    paths, app_port, service, logs = load_service(root)
    if service._is_port_listening(app_port):
        raise RuntimeError(f"OpenClaw port {app_port} is already listening. Close the running service before measuring cold start.")

    snapshot_path = Path(paths.data_dir) / "logs" / "openclaw-startup-snapshot.json"
    start = time.perf_counter()
    error = ""
    try:
        service.start()
    except Exception as exc:
        error = str(exc)
    elapsed_ms = int((time.perf_counter() - start) * 1000)

    status = service.status()
    snapshot = read_json_if_exists(snapshot_path)
    result = {
        "root": str(root),
        "pythonRoot": str(discover_python_root(root)),
        "snapshotPath": str(snapshot_path),
        "measuredColdStartMs": elapsed_ms,
        "startupState": status.get("startupState"),
        "startupElapsedSec": status.get("startupElapsedSec"),
        "startupTimeoutSec": status.get("startupTimeoutSec"),
        "startupError": error or status.get("startupError") or snapshot.get("error", ""),
        "startupStage": status.get("startupStage") or (snapshot.get("startupTimeline") or [{}])[-1].get("stage"),
        "pid": status.get("pid"),
        "portReady": status.get("portReady"),
        "running": status.get("running"),
        "processAlive": status.get("processAlive"),
        "snapshot": snapshot,
        "logsTail": logs[-40:],
    }

    output_path = Path(args.output_path) if args.output_path else Path(paths.data_dir) / "logs" / "cold-start-measurement.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Cold start measured: {elapsed_ms} ms"
        f" (state={result['startupState']}, ready={result['portReady']}) -> {output_path}"
    )

    if args.stop_after_measure:
        try:
            service.stop()
        except Exception as stop_error:
            print(f"WARNING: failed to stop service: {stop_error}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
