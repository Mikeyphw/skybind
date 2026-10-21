#!/usr/bin/env python3
"""Fail-closed R1 consumer integration source contract; never starts a socket."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]

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
    for k,ok in checks.items():print(("PASS_" if ok else "FAIL_")+k)
    return 0 if all(checks.values()) else 2
if __name__=="__main__":sys.exit(gate())
