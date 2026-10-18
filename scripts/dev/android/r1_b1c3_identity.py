#!/usr/bin/env python3
"""B1-C3: read-only Android UID/package and SELinux survey bound to H4 APKs.

This is NOT an OS-trusted privileged package attestor and must never be used
as a Go brokeridentity.PackageAttestor implementation or to issue grants.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid

import r1_b1c_device as b1c

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT / "build/evidence/android/b1c3"
PACKAGE_LINE = re.compile(r"^package:([A-Za-z][A-Za-z0-9_.]*)\s+uid:(\d+)\s*$")

class Blocked(b1c.Blocked):
    pass


def package_uid_map(output: str) -> dict[str, int]:
    """Parse full Android package/UID enumeration; reject even unrelated ambiguity.

    This is device-state observation only, not proof of an authenticated caller.
    """
    packages: dict[str, int] = {}
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        raise Blocked("PACKAGE_UID_ENUMERATION_EMPTY")
    for line in lines:
        match = PACKAGE_LINE.fullmatch(line)
        if match is None:
            raise Blocked("PACKAGE_UID_ENUMERATION_AMBIGUOUS")
        name, raw_uid = match.groups()
        uid = int(raw_uid)
        if name in packages or uid > 2**31 - 1:
            raise Blocked("PACKAGE_UID_ENUMERATION_AMBIGUOUS")
        packages[name] = uid
    return packages


def validate_uid_mapping(a: dict[str, int], b: dict[str, int]) -> tuple[int, int]:
    if a != b:
        raise Blocked("PACKAGE_UID_FRONTENDS_DISAGREE")
    if b1c.APP not in a or b1c.TEST not in a:
        raise Blocked("ATTESTED_PACKAGE_MISSING_FROM_UID_ENUMERATION")
    app_uid, test_uid = a[b1c.APP], a[b1c.TEST]
    if app_uid < 10000 or test_uid < 10000 or app_uid == test_uid:
        raise Blocked("PACKAGE_UID_OWNERSHIP_INVALID")
    owners = {name for name, uid in a.items() if uid == app_uid}
    test_owners = {name for name, uid in a.items() if uid == test_uid}
    if owners != {b1c.APP} or test_owners != {b1c.TEST}:
        raise Blocked("SHARED_OR_AMBIGUOUS_UID")
    return app_uid, test_uid


def adb_check(adb: str, serial: str, *command: str) -> str:
    code, out, err = b1c.adb_call(adb, serial, "shell", *command)
    if code != 0 or err.strip() or not out.strip():
        raise Blocked("ANDROID_PLATFORM_IDENTITY_QUERY_FAILED")
    return out


def write_receipt(obj: dict) -> str:
    if EVIDENCE_DIR.is_symlink():
        raise Blocked("RECEIPT_DIRECTORY_SYMLINK")
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / ("b1c3-" + uuid.uuid4().hex + ".json")
    with target.open("x", encoding="utf-8") as stream:
        json.dump(obj, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return str(target)


def run(serial: str | None = None) -> int:
    report: dict = {
        "schema": "skybind-b1c3-identity-survey-v1",
        "state": "BLOCKED",
        "reason": None,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "hosted_pipeline_id": b1c.PIPELINE,
        "hosted_run_id": b1c.RUN,
        "hosted_source_sha": b1c.SOURCE,
        "survey_harness_sha256": b1c.digest(Path(__file__)),
        "device_qualified": False,
        "release_qualified": False,
        "privileged_package_attestor_implemented": False,
        "cross_uid_broker_authorized": False,
        "automatic_install": False,
        "automatic_uninstall": False,
        "automatic_data_clear": False,
        "automatic_reboot": False,
    }
    try:
        attested = b1c.hosted_attestation()
        archive = b1c.verified_archive(attested)
        with tempfile.TemporaryDirectory(prefix="skybind-b1c3-") as folder:
            temp = Path(folder)
            b1c.copy_verified_pair(archive, attested, temp)
            adb = shutil.which("adb")
            if adb is None:
                raise Blocked("ADB_NOT_FOUND")
            selected = b1c.chosen_device(adb, serial)
            report["device_serial_sha256"] = hashlib.sha256(selected.encode()).hexdigest()
            report["device_api"] = int(b1c.getprop(adb, selected, "ro.build.version.sdk"))
            if report["device_api"] < 26:
                raise Blocked("DEVICE_API_BELOW_MINIMUM")
            if b1c.check_installed(adb, selected, temp, attested) != "MATCHED":
                raise Blocked("ATTESTED_APKS_NOT_INSTALLED")
            report["installed_pair"] = "MATCHED"
            first = package_uid_map(adb_check(adb, selected, "pm", "list", "packages", "-U", "--user", "0"))
            second = package_uid_map(adb_check(adb, selected, "cmd", "package", "list", "packages", "-U", "--user", "0"))
            app_uid, test_uid = validate_uid_mapping(first, second)
            report["app_uid"] = app_uid
            report["instrumentation_package_uid"] = test_uid
            report["package_uid_crosscheck"] = "PASS"
            selinux = adb_check(adb, selected, "getenforce").strip()
            report["selinux"] = selinux
            if selinux != "Enforcing":
                raise Blocked("SELINUX_NOT_ENFORCING")
            report["hosted_attestation"] = "PASS"
            report["hosted_apk_bytes"] = "PASS"
            report["state"] = "PASS_B1C3_UID_OBSERVATION_NOT_BROKER_AUTH"
    except (b1c.Blocked, ValueError, KeyError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        report["reason"] = exc.reason if isinstance(exc, b1c.Blocked) else type(exc).__name__.upper()
    path = write_receipt(report)
    print(json.dumps({"state": report["state"], "reason": report["reason"], "receipt": path,
                      "package_uid_crosscheck": report.get("package_uid_crosscheck"),
                      "installed_pair": report.get("installed_pair")}, sort_keys=True))
    return 0 if report["state"].startswith("PASS_") else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="Select one authorized ADB device when multiple are present")
    args = parser.parse_args()
    return run(args.serial)


if __name__ == "__main__":
    raise SystemExit(main())
