#!/usr/bin/env python3
"""Source-only R1 native/Android trust-layer gate (no listener/device mutation)."""
from __future__ import annotations
import json
import pathlib
import sys

ROOT=pathlib.Path(__file__).resolve().parents[3]
CHECKS={
 'internal/brokeridentity/attested_package.go':('PlatformPackageAttestor','PackagesForUID','ConstantTimeCompare'),
 'internal/brokeridentity/module_installed.go':('InstalledModuleAttestor','module-package-manifest.json','Readlink','SameFile'),
 'internal/brokeridentity/multiplex.go':('ConsumerVerifier','Chrootctl','BKXUID'),
 'internal/brokeripc/activated.go':('ConsumerSocket','ExplicitlyEnabled','ServeConn','0660'),
 'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/R1PackageManagerAuthority.kt':('GET_SIGNING_CERTIFICATES','getPackagesForUid','getUserHandleForUid'),
 'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/R1PackageManagerAuthorityTest.kt':('R1PackageManagerAuthority','unapproved'),
 'internal/brokeridentity/attested_package_test.go':('TestTrustedPlatformSigningAndExactUID','shared-uid'),
 'internal/brokeridentity/module_installed_test.go':('TestInstalledModuleSealAndActualProcess','other-executable'),
 'internal/brokeripc/activated_test.go':('TestConsumerSocketDefaultDeniedAndScopedRequest','Revoke'),
}

def check(root: pathlib.Path=ROOT)->dict:
    errors=[]
    for file, tokens in CHECKS.items():
        path=root/file
        try: data=path.read_text()
        except OSError: errors.append('MISSING:'+file);continue
        for token in tokens:
            if token not in data: errors.append('CONTRACT_MISSING:'+file+':'+token)
    main=(root/'cmd/skybind/main.go').read_text()
    if 'ConsumerSocket' in main or 'consumer-gateway' in main:
        errors.append('R1_PRODUCTION_ACTIVATION_NOT_QUALIFIED')
    try:
        abi=json.loads((root/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
        if abi.get('available_external_capabilities') != []:
            errors.append('PREMATURE_EXTERNAL_CAPABILITY_ADVERTISEMENT')
    except (ValueError,OSError) as e: errors.append('ABI_MISSING:'+str(type(e).__name__))
    return {'schema':'skybind-r1-device-trust-source-v1',
      'status':'PASS_R1_DEVICE_TRUST_SOURCE_NO_EXTERNAL_ACTIVATION' if not errors else 'FAIL_R1_DEVICE_TRUST_SOURCE',
      'errors':errors,'production_listener_enabled':False,'android_bridge_connected_to_go':False,
      'device_process_attested':False,'grants_issued':False,'external_provider_qualified':False,
      'release_qualified':False}

if __name__=='__main__':
    result=check();print(json.dumps(result,sort_keys=True))
    sys.exit(0 if not result['errors'] else 1)
