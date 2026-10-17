#!/usr/bin/env python3
"""Isolated Go test diagnostics for the B0/B1 Termux WaitDelay incident.

Runs only the four observed failing Skybind packages (never an Android APK
build). Keeps raw Go test events private and fails when a package fails.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

SUSPECTS = (
    "./internal/paths",
    "./internal/mounts/policy",
    "./internal/mounts/lifecycle",
    "./internal/opevents",
)


def cmd_text(args: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(args, cwd=cwd, stderr=subprocess.DEVNULL,
                                       timeout=10, text=True).strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unavailable"


def private_write(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
    except BaseException:
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", choices=SUSPECTS, action="append",
                        help="Run one named package; repeat for multiple (default: all four)")
    parser.add_argument("--timeout-seconds", type=int, default=180,
                        help="Maximum wall time for one Go package (default: 180)")
    parser.add_argument("--output-dir", type=Path, default=Path("build/evidence/go-waitdelay"))
    parser.add_argument("--stop-on-failure", action="store_true")
    args = parser.parse_args()
    if not 75 <= args.timeout_seconds <= 1800:
        parser.error("--timeout-seconds must be in [75, 1800]")
    root = Path(__file__).resolve().parents[3]
    if not (root / "go.mod").is_file():
        parser.error("go.mod not found at expected Skybind repository root")
    out = args.output_dir.absolute()
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(out, 0o700)
    packages = tuple(dict.fromkeys(args.package or SUSPECTS))
    manifest = {
        "schema": "skybind-go-waitdelay-diag-v1", "qualified": False,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "go_version": cmd_text(["go", "version"], root),
        "goos": cmd_text(["go", "env", "GOOS"], root),
        "goarch": cmd_text(["go", "env", "GOARCH"], root),
        "source_commit": cmd_text(["git", "rev-parse", "HEAD"], root),
        "package_results": [],
    }
    for i, package in enumerate(packages, 1):
        argv = ["go", "test", "-json", "-count=1", "-p", "1", "-timeout=120s", package]
        path = out / (package.removeprefix("./").replace("/", "_") + ".jsonl")
        started = time.monotonic()
        print(f"[{i}/{len(packages)}] {package}: running isolated Go test", flush=True)
        timed_out = False
        try:
            # Redirect stdout/stderr directly into one file. There is no Python
            # output pipe that a surviving test child could hold open.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(fd, "wb") as log:
                try:
                    proc = subprocess.Popen(argv, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                            start_new_session=True)
                    try:
                        rc = proc.wait(timeout=args.timeout_seconds)
                    except subprocess.TimeoutExpired:
                        timed_out = True
                        os.killpg(proc.pid, signal.SIGKILL)
                        rc = proc.wait()
                except OSError as exc:
                    log.write(f"launch error: {type(exc).__name__}: {exc}\n".encode())
                    rc = 127
        except OSError as exc:
            print(f"Could not securely create output: {type(exc).__name__}", file=sys.stderr)
            return 2
        payload = path.read_bytes()
        result = {
            "package": package, "command": argv, "exit_code": rc,
            "timed_out": timed_out, "elapsed_seconds": round(time.monotonic() - started, 3),
            "waitdelay_seen": b"WaitDelay expired" in payload,
            "go_test_io_incomplete_seen": b"Test I/O incomplete" in payload,
            "log": path.name, "log_sha256": hashlib.sha256(payload).hexdigest(),
        }
        manifest["package_results"].append(result)
        print(f"  {'PASS' if rc == 0 else 'FAILED'} exit={rc} elapsed={result['elapsed_seconds']}s "
              f"waitdelay={result['waitdelay_seen']} log={path.name}", flush=True)
        if rc and args.stop_on_failure:
            break
    manifest["all_passed"] = len(manifest["package_results"]) == len(packages) and all(
        r["exit_code"] == 0 for r in manifest["package_results"]
    )
    private_write(out / "summary.json", (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    print(f"Summary: {out / 'summary.json'}", flush=True)
    return 0 if manifest["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
