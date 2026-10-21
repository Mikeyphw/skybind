#!/usr/bin/env python3
"""R1 operator-policy admission source gate; never enables external access."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REQUIRED = {
    'internal/brokerruntime/policy.go': ('CanonicalPolicy', 'DisallowUnknownFields', 'rejectDuplicateJSONKeys', 'ModeSymlink', 'ExplicitlyEnabled', 'Root'),
    'internal/brokerruntime/gateway.go': ('PlatformAuthority', 'trusted_authorities_not_connected', 'IssueApproved', 'Issuer', 'Revoke', 'MaxGrantTTL'),
    'internal/brokerruntime/runtime_test.go': ('TestVerifiedScopedGrantAndImmediateRevocation', 'TestOperatorPolicyFailClosed', 'TestLoadRootOwnedOperatorPolicyAndRejectSymlinks'),
    'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/R1BKXInstalledPackageAcceptanceTest.kt': ('SKYBIND_R1_BKX_PM_NOT_REQUESTED', 'R1PackageManagerAuthority.verify', 'BLOCKED_OPERATOR_SIGNER_PIN_MISSING', 'WRONG_SIGNER_ACCEPTED'),
    'android-app/app/src/main/AndroidManifest.xml': ('<queries>', 'com.mikeyphw.bkx.android'),
    'scripts/dev/android/r1_bkx_pm_device.py': ('approved-signer', 'installed_pair', 'external_provider_qualified=False', 'Interpret_instrumentation'),
    'internal/brokeridentity/attested_package.go': ('PlatformPackageAttestor', 'PackageAuthority', 'ConstantTimeCompare'),
    'internal/brokeridentity/module_installed.go': ('InstalledModuleAttestor', 'module-package-manifest.json'),
    'internal/brokeripc/activated.go': ('ExplicitlyEnabled', 'ServeConn'),
    'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json': ('available_external_capabilities', 'external_transport_status'),
}

def evaluate(root: Path = ROOT) -> dict:
    errors: list[str] = []
    for name, tokens in REQUIRED.items():
        try:
            content = (root/name).read_text()
        except OSError:
            errors.append('MISSING:' + name)
            continue
        for token in tokens:
            if token.lower() not in content.lower():
                errors.append('MISSING_CONTRACT:' + name + ':' + token)
    try:
        manifest = json.loads((root/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
        if manifest.get('available_external_capabilities') != []:
            errors.append('PREMATURE_EXTERNAL_CAPABILITY')
        if manifest.get('external_transport_status') != 'NOT_IMPLEMENTED':
            errors.append('UNQUALIFIED_TRANSPORT_ADVERTISED')
    except (ValueError, OSError):
        errors.append('ABI_MISSING')
    main = (root/'cmd/skybind/main.go').read_text()
    if 'brokerruntime.Assemble(' in main or 'ConsumerSocket{' in main:
        errors.append('PRODUCTION_GATEWAY_ENABLED_WITHOUT_DEVICE_ATTESTATION')
    try:
        service = (root/'module/service.sh').read_text()
        if 'broker-gateway' in service or 'r1-broker' in service:
            errors.append('MODULE_AUTOSTARTS_UNQUALIFIED_BROKER')
    except OSError:
        errors.append('MODULE_SERVICE_MISSING')
    return {
        'schema': 'skybind-r1-operator-admission-source-v1',
        'status': 'PASS_R1_ADMISSION_SOURCE_DEFAULT_DENY' if not errors else 'FAIL_R1_ADMISSION_SOURCE',
        'errors': errors,
        'operator_policy_parser_implemented': True,
        'backend_connected_to_android_pm': False,
        'live_external_transport_activated': False,
        'bkx_device_qualified': False,
        'chrootctl_device_qualified': False,
        'release_qualified': False,
    }

if __name__ == '__main__':
    r = evaluate()
    print(json.dumps(r, sort_keys=True))
    raise SystemExit(0 if not r['errors'] else 1)
