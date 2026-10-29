#!/usr/bin/env python3
"""API-05 personal-device qualification evidence collector (non-mutating).

No gateway activation, mount mutation, privileged policy edits, or APK installs.
A source-test PASS is never promoted to real-device acceptance.
"""
from __future__ import annotations

import argparse
import errno
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import sys
import tempfile

SCHEMA = "skybind-api05-personal-evidence-v1"
QUERY = "\0skybind-api04-bkx-query-v1"
MUTATION = "\0skybind-api04-mutations-v1"
POLICIES = {
    "query": "/data/adb/skybind/api04-bkx-policy-v1.json",
    "mutation": "/data/adb/skybind/api04-mutation-policy-v1.json",
}
PARENT = "/data/adb/skybind"
STAGES = ("baseline", "gateway", "after_reboot", "lifecycle")
SCOPES = ("core", "api04-query", "api04-full")


def command(argv: list[str], *, timeout: int = 6) -> dict:
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
        # Do not serialize arbitrary command output, potentially containing secrets.
        return {"ok": p.returncode == 0, "stdout": p.stdout[:512].strip() if p.returncode == 0 else "", "code": p.returncode}
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "stdout": "", "code": None}


def root_command(fixed_command: str) -> dict:
    binary = shutil.which("su")
    if not binary:
        return {"ok": False, "stdout": "", "code": None}
    return command([binary, "-c", fixed_command])


def inspect_secure_file(path: str) -> dict:
    # All paths are application constants; caller cannot inject shell syntax.
    assert path in (PARENT, *POLICIES.values())
    result = root_command("stat -c '%u %a %h %F' " + path)
    tokens = result["stdout"].split()
    if not result["ok"] or len(tokens) < 4:
        return {"observed": False, "secure": False}
    uid, mode, links = tokens[:3]
    kind = " ".join(tokens[3:])
    expected_mode = "700" if path == PARENT else "600"
    is_regular = "regular" in kind if path != PARENT else "directory" in kind
    secure = uid == "0" and mode == expected_mode and is_regular and (path == PARENT or links == "1")
    return {"observed": True, "secure": secure, "uid_root": uid == "0", "mode": mode, "kind": kind}


def probe_socket(address: str, approved_uid: int | None, *, send_denial: bool) -> dict:
    """A non-approved client sends malformed JSON; it never requests a mutation."""
    result = {"reachable": False, "root_peer": False, "denial": "not_run", "connect_status": "unknown"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(3)
            conn.connect(address)
            result["reachable"] = True
            result["connect_status"] = "connected"
            creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            pid, uid, gid = struct.unpack("3i", creds)
            result["root_peer"] = uid == 0 and pid > 0
            if not result["root_peer"]:
                result["denial"] = "nonroot_server"
                return result
            # The approved app UID is a user-provided operator pin, not a trusted source.
            if not send_denial or approved_uid is None:
                return result
            if os.getuid() == approved_uid:
                result["denial"] = "blocked_same_uid_as_approved"
                return result
            conn.sendall(b"{}")
            conn.shutdown(socket.SHUT_WR)
            data = bytearray()
            while b"\n" not in data and len(data) < 2048:
                chunk = conn.recv(2048 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            reply = json.loads(bytes(data).decode("utf-8"))
            if reply.get("ok") is False and reply.get("version") == 1:
                expected = "api04_peer_denied" if address == QUERY else "api04_mutation_peer_denied"
                result["denial"] = "pass" if reply.get("error") == expected else "unexpected_response"
            else:
                result["denial"] = "unexpected_response"
    except OSError as exc:
        if result["reachable"]:
            result["denial"] = "probe_failed"
        elif exc.errno in (errno.ENOENT, errno.ECONNREFUSED):
            result["connect_status"] = "absent"
        elif exc.errno in (errno.EACCES, errno.EPERM):
            result["connect_status"] = "permission_denied"
        else:
            result["connect_status"] = "unknown_error"
    except (ValueError, UnicodeError, json.JSONDecodeError):
        if result["reachable"]:
            result["denial"] = "probe_failed"
        else:
            result["connect_status"] = "unknown_error"
    return result


def mount_snapshot(mountpoint: str | None) -> dict:
    if not mountpoint:
        return {"observed": False}
    if not mountpoint.startswith("/") or "\n" in mountpoint or "\r" in mountpoint:
        raise ValueError("absolute mountpoint required")
    try:
        # Observational only: this is the caller's namespace, NOT proof of daemon ownership.
        rows = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {"observed": False}
    needle = mountpoint.replace(" ", "\\040")
    matches = []
    for line in rows:
        fields = line.split(" ")
        if len(fields) >= 6 and fields[4] == needle:
            matches.append({"mount_id": fields[0], "major_minor": fields[2], "line_sha256": hashlib.sha256(line.encode()).hexdigest()})
    return {"observed": True, "mounted": bool(matches), "matches": matches, "namespace": "termux_self_not_daemon"}


def android_environment() -> bool:
    return bool(shutil.which("getprop")) and Path("/system/bin").is_dir()


def observe_selinux() -> dict:
    """Read SELinux mode without interpreting Termux's permission denial as permissive.

    Only the exact Android modes are accepted. A root fallback is independently
    identified in evidence and is not treated as installed-app identity proof.
    """
    getter = shutil.which("getenforce") or "/system/bin/getenforce"
    direct = command([getter])
    if direct["ok"] and direct["stdout"] in ("Enforcing", "Permissive", "Disabled"):
        return {"mode": direct["stdout"], "source": "termux"}
    elevated = root_command("/system/bin/getenforce")
    if elevated["ok"] and elevated["stdout"] in ("Enforcing", "Permissive", "Disabled"):
        return {"mode": elevated["stdout"], "source": "root"}
    return {"mode": "unavailable", "source": "unavailable"}


def capture(stage: str, approved_uid: int | None, *, denial: bool, mountpoint: str | None) -> dict:
    try:
        boot = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        boot = ""
    enforcement = observe_selinux()
    root = root_command("id -u")
    parent = inspect_secure_file(PARENT)
    policies = {key: inspect_secure_file(path) for key, path in POLICIES.items()}
    return {
        "schema": SCHEMA, "stage": stage,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {"android": android_environment(), "root_available": root["ok"] and root["stdout"] == "0", "selinux": enforcement["mode"], "selinux_source": enforcement["source"], "boot_id": boot},
        "policy": {"parent": parent, **policies},
        "sockets": {"query": probe_socket(QUERY, approved_uid, send_denial=denial), "mutation": probe_socket(MUTATION, approved_uid, send_denial=denial)},
        "mount": mount_snapshot(mountpoint),
        "operator_pin_supplied": approved_uid is not None,
        "denial_probe_requested": denial,
        "device_qualification_complete": False,
    }


def gate_results(snapshots: list[dict], *, scope: str = "core") -> dict:
    """Assess independently selected personal-device contracts.

    Core scope never requires an unused API-04 consumer policy or a live gateway.
    All scopes still fail closed on unexpected/insecure live API-04 endpoints.
    No passive collector is permitted to issue a final device qualification.
    """
    if scope not in SCOPES:
        raise ValueError("unsupported API05 qualification scope")
    if not snapshots:
        raise ValueError("at least one snapshot required")
    for snap in snapshots:
        if not isinstance(snap, dict) or snap.get("schema") != SCHEMA or snap.get("stage") not in STAGES:
            raise ValueError("invalid API05 evidence schema or stage")
        if snap.get("device_qualification_complete") is not False:
            raise ValueError("forged final qualification flag")
    latest = snapshots[-1]
    env = latest.get("environment", {})
    policies = latest.get("policy", {})
    sock = latest.get("sockets", {})
    errors: list[str] = []
    if not env.get("android"):
        errors.append("native_android_not_observed")
    if not env.get("root_available"):
        errors.append("root_probe_unavailable")
    if env.get("selinux") != "Enforcing":
        errors.append("selinux_enforcing_not_observed")
    parent = policies.get("parent", {})
    if not parent.get("observed") or not parent.get("secure"):
        errors.append("root_owned_policy_missing_or_unverified:parent")

    require_query = scope in ("api04-query", "api04-full")
    require_mutation = scope == "api04-full"
    query_policy = policies.get("query", {})
    mutation_policy = policies.get("mutation", {})
    query_observed = bool(query_policy.get("observed"))
    mutation_observed = bool(mutation_policy.get("observed"))
    query_secure = bool(query_observed and query_policy.get("secure"))
    mutation_secure = bool(mutation_observed and mutation_policy.get("secure"))
    query_peer = sock.get("query", {})
    mutation_peer = sock.get("mutation", {})

    for name, observed, secure, required, endpoint in (
        ("query", query_observed, query_secure, require_query, query_peer),
        ("mutation", mutation_observed, mutation_secure, require_mutation, mutation_peer),
    ):
        if required and not secure:
            errors.append("root_owned_policy_missing_or_unverified:" + name)
        elif observed and not secure:
            # An insecure policy is a problem even if the corresponding gateway
            # is dormant. Missing optional policies are not a problem.
            errors.append("root_owned_policy_insecure:" + name)
        if endpoint.get("connect_status") in ("permission_denied", "unknown_error"):
            errors.append("api04_endpoint_visibility_unverified:" + name)
        if endpoint.get("reachable"):
            if not endpoint.get("root_peer"):
                errors.append("nonroot_server_socket:" + name)
            if not secure:
                errors.append(name + "_socket_without_secure_policy")
            if scope == "core":
                # Unexpected exposure of an unused privileged endpoint must
                # never be mistaken for normal core-only device readiness.
                errors.append("api04_endpoint_active_outside_core_scope:" + name)

    mutation_blockers = []
    if not mutation_observed:
        mutation_blockers.append("mutation_policy_not_provisioned")
    elif not mutation_secure:
        mutation_blockers.append("mutation_policy_insecure")
    if mutation_peer.get("reachable") and not mutation_secure:
        mutation_blockers.append("mutation_gateway_exposed_without_secure_policy")

    # Passive root mode and policy metadata support PARTIAL at most. Installed
    # package signature and daemon-side lifecycle authority remain unverified.
    g1 = "PARTIAL" if not errors else "BLOCKED"
    query_denied = bool(query_secure and query_peer.get("reachable") and
                        query_peer.get("root_peer") and query_peer.get("denial") == "pass")
    mutation_denied = bool(mutation_secure and mutation_peer.get("reachable") and
                           mutation_peer.get("root_peer") and mutation_peer.get("denial") == "pass")
    negative = bool(query_denied and mutation_denied)
    if scope == "core":
        g2 = "DEFERRED_NOT_USED" if not any(sock.get(x, {}).get("reachable") for x in ("query", "mutation")) else "BLOCKED"
    elif any(sock.get(name, {}).get("reachable") and not sock.get(name, {}).get("root_peer") for name in ("query", "mutation")):
        g2 = "BLOCKED"
    elif query_denied or (scope == "api04-full" and mutation_denied):
        g2 = "PARTIAL"
    else:
        g2 = "NOT_RUN"

    baseline = next((x for x in snapshots if x["stage"] == "baseline"), None)
    reboot = next((x for x in snapshots if x["stage"] == "after_reboot"), None)
    distinct_boot = bool(baseline and reboot and baseline["environment"].get("boot_id") and
                         reboot["environment"].get("boot_id") and
                         baseline["environment"]["boot_id"] != reboot["environment"]["boot_id"])
    observed_mount = bool(baseline and reboot and baseline.get("mount", {}).get("observed") and
                          reboot.get("mount", {}).get("observed"))
    g3 = "PARTIAL" if distinct_boot and observed_mount else "NOT_RUN"

    outstanding = [
        "independent Skybind root-daemon and native CLI/runtime provenance",
        "actual named FUSE mount start-stop/reconciliation with daemon-owned observations",
        "crash/lost-reply/reboot recovery device receipts",
        "supported-host -race receipt and source-bound core qualification review",
    ]
    if require_query:
        outstanding.extend([
            "independent installed consumer PackageManager identity/signature/SELinux attestation",
            "authorized-client positive query and unapproved-client denial receipts",
        ])
    if require_mutation:
        outstanding.append("approved mutation preview/proof/replay/recovery device receipts")

    return {
        "schema": SCHEMA,
        "scope": scope,
        "core_qualification_complete": False,
        "device_qualification_complete": False,
        "gates": {"05-1-security": g1, "05-2-gateway": g2,
                  "05-3-lifecycle": g3, "05-4-final-seal": "BLOCKED"},
        "deferred": {"api04_query": not require_query,
                     "api04_mutation": not require_mutation,
                     "reason": "no_current_consumer" if scope == "core" else "outside_selected_scope"},
        "observations": {
            "security_blockers": errors,
            "query_policy_state": "SECURE" if query_secure else "INSECURE" if query_observed else "NOT_CONFIGURED",
            "mutation_policy_state": "SECURE" if mutation_secure else "INSECURE" if mutation_observed else "NOT_CONFIGURED",
            "mutation_readiness_blockers": mutation_blockers,
            "api04_socket_observation": {
                name: sock.get(name, {}).get("connect_status", "legacy_unknown")
                for name in ("query", "mutation")
            },
            "unapproved_client_rejected_at_query_socket": query_denied,
            "unapproved_client_rejected_at_mutation_socket": mutation_denied,
            "unapproved_client_rejected_at_both_sockets": negative,
            "reboot_observed": distinct_boot,
            "mount_observation_only": observed_mount,
        },
        "still_required": outstanding,
    }


def atomic_json(path: Path, obj: dict) -> None:
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("refuse output symlink/non-file")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".api05-", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    take = commands.add_parser("capture", help="read-only local Android snapshot")
    take.add_argument("--stage", required=True, choices=STAGES)
    take.add_argument("--output", required=True, type=Path)
    take.add_argument("--approved-consumer-uid", type=int)
    take.add_argument("--probe-unapproved-client", action="store_true")
    take.add_argument("--mountpoint", help="optional observation in Termux's own mount namespace")
    check = commands.add_parser("evaluate", help="fail-closed report from collected evidence")
    check.add_argument("--output", required=True, type=Path)
    check.add_argument("--scope", choices=SCOPES, default="core", help="default core excludes dormant, unused API04 gateways; explicit API04 scopes retain their gates")
    check.add_argument("snapshots", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            if args.approved_consumer_uid is not None and not 10000 <= args.approved_consumer_uid <= 2147483647:
                raise ValueError("approved consumer uid out of Android app range")
            if args.probe_unapproved_client and args.approved_consumer_uid is None:
                raise ValueError("negative probe requires independent approved UID pin")
            result = capture(args.stage, args.approved_consumer_uid, denial=args.probe_unapproved_client, mountpoint=args.mountpoint)
        else:
            result = gate_results([json.loads(p.read_text(encoding="utf-8")) for p in args.snapshots], scope=args.scope)
        atomic_json(args.output, result)
        print("API05_EVIDENCE_WRITTEN:" + str(args.output))
        if args.command == "evaluate":
            print("API05_FINAL_SEAL_BLOCKED_REAL_DEVICE_EVIDENCE_PENDING")
        return 0
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        print("BLOCKED_API05_EVIDENCE:" + type(exc).__name__ + ":" + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
