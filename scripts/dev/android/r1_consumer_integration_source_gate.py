#!/usr/bin/env python3
"""Fail-closed R1 consumer integration source contract; never starts a socket."""
from pathlib import Path
import sys
import tomllib
ROOT=Path(__file__).resolve().parents[3]



def release_target_cwd_checks(document: dict, repo_root: Path = ROOT) -> dict[str, bool]:
    """Validate R1 commands from Devtool's declared target root, not shell cwd.

    In particular, target skybind_release has root=release, so path-bearing
    command arguments must be relative to release/. This is a source-level
    configuration assertion, not a command execution or device qualification.
    """
    try:
        target = document["targets"]["skybind_release"]
        target_root = (repo_root / target["root"]).resolve()
        repo_root = repo_root.resolve()
        jobs = target["jobs"]
        contract = jobs["r1-consumer-integration-contract"]["command"]
        contract_ok = (
            contract[:2] == ["python3", "-B"] and len(contract) == 3 and
            (target_root / contract[2]).resolve() ==
                (repo_root / "scripts/dev/android/r1_consumer_integration_source_gate.py").resolve()
        )
        results = {"RELEASE_INTEGRATION_PYTHON_CWD": contract_ok}
        for job, label in (
            ("r1-consumer-integration-go", "RELEASE_INTEGRATION_GO_CWD"),
            ("r1-consumer-transport-go", "RELEASE_TRANSPORT_GO_CWD"),
        ):
            command = jobs[job]["command"]
            results[label] = (
                len(command) >= 5 and command[0:2] == ["go", "-C"] and
                command[3:5] == ["test", "-count=1"] and
                (target_root / command[2]).resolve() == repo_root and
                all(arg.startswith("./") for arg in command[5:])
            )
        return results
    except (KeyError, TypeError, ValueError, IndexError):
        return {key: False for key in (
            "RELEASE_INTEGRATION_PYTHON_CWD", "RELEASE_INTEGRATION_GO_CWD",
            "RELEASE_TRANSPORT_GO_CWD")}

def gate():
    paths={name:ROOT/name for name in (
        "internal/brokerruntime/metadata.go", "internal/brokerruntime/handoff.go",
        "internal/brokeridentity/authority_apk.go", "cmd/skybind-r1-gateway/main.go",
        "cmd/skybind-r1-module-check/main.go", "integrations/bkx/SkybindR1ReadClient.kt",
        "internal/brokeripc/grant_client.go", "internal/brokeripc/server.go",
        ".github/workflows/skybind-r1-consumer-diagnostics.yml")}
    src={key:p.read_text() for key,p in paths.items()}
    checks={
        "EXPLICIT_OPERATOR_ACTIVATION": all(s in src["cmd/skybind-r1-gateway/main.go"] for s in ("operator-approve","brokerruntime.LoadAt","bridge.Accept","StartAbstract","handoff.Start")),
        "REAL_TYPED_READ_ONLY_BACKEND": all(s in src["internal/brokerruntime/metadata.go"] for s in ("provider.Canonical()", "rclone.lsjson", "rclone.size", "rclone.listremotes", "rclone.version", "system.capabilities", "paths.RcloneConfig")),
        "NO_GENERIC_SHELL_BACKEND": not any(s in src["internal/brokerruntime/metadata.go"] for s in ("os/exec","exec.Command(","/system/bin/sh","rm -rf")),
        "OPERATOR_APPROVED_EXACT_PID_HANDOFF": all(s in src["internal/brokerruntime/handoff.go"] for s in ("PeerCredentials(c)","peer != offer.Peer","verified != offer.Identity","IssueApproved","RevokeIssued","handoffTimeout")),
        "SEPARATE_GRANT_SOCKET": "skybind-r1-grant-handoff-v1" in src["internal/brokerruntime/handoff.go"] and "skybind-r1-consumer-gateway-v1" in (ROOT/"internal/brokeripc/abstract.go").read_text(),
        "INDEPENDENT_APPROVED_APK_BYTES": all(s in src["internal/brokeridentity/authority_apk.go"] for s in ("ApprovedAPK_SHA256","/data/app/","ConstantTimeCompare","os.SameFile")),
        "NO_AUTO_MODULE_SERVICE": all("skybind-r1-gateway" not in (ROOT/p).read_text() for p in ("module/service.sh","module/post-fs-data.sh")),
        "NO_BKX_APK_CHANGES": "android-app" not in src["integrations/bkx/SkybindR1ReadClient.kt"] and "com.mikeyphw.bkx.r1" in src["integrations/bkx/SkybindR1ReadClient.kt"],
        "HOSTED_ANDROID_ARM64_DIAGNOSTICS": all(s in src[".github/workflows/skybind-r1-consumer-diagnostics.yml"] for s in ("GOOS: android", "GOARCH: arm64", '"release_qualified":false', "sha256sum")),
    }
    checks.update(release_target_cwd_checks(tomllib.loads((ROOT/".devtool.toml").read_text())))
    for k,ok in checks.items():print(("PASS_" if ok else "FAIL_")+k)
    return 0 if all(checks.values()) else 2
if __name__=="__main__":sys.exit(gate())
