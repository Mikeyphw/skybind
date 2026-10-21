#!/usr/bin/env python3
"""R1 channel source gate. Never starts a listener or issues consumer grants."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]

def check():
    agent=(ROOT/'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/R1PMBridgeAgent.kt').read_text()
    bridge=(ROOT/'internal/brokeridentity/pm_bridge.go').read_text()
    cli=(ROOT/'cmd/skybind-r1-pm/main.go').read_text()
    workflow=(ROOT/'.github/workflows/skybind-r1-pm-bridge.yml').read_text()
    device_runner=(ROOT/'scripts/dev/android/r1_pm_bridge_device.py').read_text()
    android_tests=(ROOT/'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/R1PMBridgeAgentTest.kt').read_text()
    manifest=(ROOT/'android-app/app/src/main/AndroidManifest.xml').read_text()
    peers=[(ROOT/'internal/brokeridentity'/name).read_text() for name in ('android.go','root.go','pm_bridge.go')]
    normalizer=(ROOT/'internal/brokeridentity/proc_selinux.go').read_text()
    checks={
      'PROC_SELINUX_NUL_NORMALIZATION': 'procSELinuxLabel' in normalizer and all('procSELinuxLabel(label)' in code and 'TrimSpace(string(label))' not in code for code in peers),
      'PROC_SELINUX_REJECTS_EMBEDDED_NUL': 'bytes.IndexAny(raw' in normalizer and 'ErrUnverified' in normalizer,
      'ANDROID_AGENT_ABSTRACT_PEER': 'Namespace.ABSTRACT' in agent and 'skybind-r1-pm-authority-v1' in agent,
      'ROOT_PEERCRED_AND_STARTTIME': 'SO_PEERCRED' in bridge and 'parseStartTicks' in bridge and 'parseStatusUID' in bridge,
      'ROOT_PEER_LABEL_AND_UID': 'attr/current' in bridge and 'cred.Uid != b.Pin.UID' in bridge,
      'ROOT_CHALLENGE_AND_REPLAY': 'crypto/rand' in bridge and 'ConstantTimeCompare' in bridge,
      'ROOT_OPERATOR_PIN': 'skybind-context' in cli and 'skybind-uid' in cli and 'bkx-signer' in cli,
      'ROOT_CLI_EXPLICIT': 'func main()' in cli and 'r1PMBridgeCheck(os.Args[1:])' in cli,
      'NO_AUTO_BROKER_GRANTS': 'IssueApproved(' not in cli and 'IssueApproved(' not in bridge and 'BROKER_UNQUALIFIED' not in cli,
      'NO_AUTO_MODULE_SERVICE': 'r1-pm-bridge' not in (ROOT/'module/service.sh').read_text(),
      'NO_EXPORT_API': 'QUERY_ALL_PACKAGES' not in manifest.replace('<!-- BKX visibility is limited to its exact package; no QUERY_ALL_PACKAGES. -->',''),
      'HOSTED_GO_DIAGNOSTIC': 'GOOS: android' in workflow and 'GOARCH: arm64' in workflow and 'release_qualified":false' in workflow,
      'NO_BKX_MUTATIONS': all(x not in agent for x in ['Runtime.getRuntime()', 'ProcessBuilder(', 'Shell.cmd(', 'rcat', 'deletefile']),
      'DEVICE_FOUR_ANDROID_NEGATIVES': all(x in android_tests and x in device_runner for x in ['deniesUnknownConsumer', 'deniesUninstalledOrWrongUid', 'deniesInvalidNonce', 'deniesUnknownFields']) and 'run_agent_negative_instrumentation(serial)' in device_runner,
      'DEVICE_RESTART_REQUIRED': "SKYBIND_RESTART_REQUIRED_FOR_THREE_INDEPENDENT_CASES" in device_runner and "args.restart_skybind" in device_runner,
      'DEVICE_RECEIPT_CONSISTENCY': 'DIAGNOSTIC_RECEIPT_INCONSISTENT_FLAGS_' in device_runner and 'DIAGNOSTIC_RECEIPT_OVERCLAIMS_QUALIFICATION' in device_runner,
    }
    for k,ok in checks.items():print(('PASS' if ok else 'FAIL')+'_'+k)
    return 0 if all(checks.values()) else 2

if __name__=='__main__':sys.exit(check())
