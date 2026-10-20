#!/usr/bin/env python3
"""R1 source-only grant engine and consumer ABI safety policy; never binds a socket."""
import json
import tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
req=lambda ok,reason: ok or (_ for _ in ()).throw(AssertionError(reason))
p=(ROOT/'internal/brokeridentity/root.go').read_text()
abi=json.loads((ROOT/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
conf=tomllib.loads((ROOT/'.devtool.toml').read_text())
req(abi['abi_major']==1 and abi['available_external_capabilities']==[],'NO_EXTERNAL_CAPABILITIES_YET')
req(abi['external_transport_status']=='NOT_IMPLEMENTED','NO_RUNTIME_BROKER_YET')
req(abi['status']=='R0_CONTRACT_ONLY_NO_RUNTIME_PROVIDER','NO_FALSE_R1_QUALIFICATION')
req('RootVerifier' in p and 'VerifyPeer' in p and 'ModuleAttestor' in p,'R1_ROOT_IDENTITY_PRIMITIVES_MISSING')
req('crypto/sha256' in p and 'parseStartTicks' in p,'R1_PROCESS_INSTANCE_IDENTITY_MISSING')
req('ModuleSealSHA256' in p and 'SELinuxContext' in p and 'ModuleAttestor' in p,
    'R1_ATTESTED_MODULE_IDENTITY_MISSING')
identity=(ROOT/'internal/brokeridentity/android.go').read_text()
req('PackageAttestor' in identity and 'PackagePin' in identity and 'parseStatusUID' in identity and 'SELinuxContext' in identity,
    'R1_EXISTING_BKX_IDENTITY_MISSING')
grant=(ROOT/'internal/brokergrant/grant.go').read_text()
req('func (s *Store) Revoke(' in grant and 'Authorize(' in grant and 'cleanPrefix' in grant,
    'R1_EXISTING_GRANT_ENFORCEMENT_MISSING')
req('strings.HasPrefix(path, prefix+"/")' in grant, 'R1_PREFIX_COMPONENT_BOUNDARY_MISSING')
for forbidden in ('net.Listen(', 'exec.Command(', 'http.ListenAndServe(', 'su -c', 'rclone serve', 'os.OpenFile('):
    req(forbidden not in p,'FORBIDDEN_PRIVILEGED_TRANSPORT:'+forbidden)
wf=conf['targets']['skybind_release']['workflows']['r1-consumer-foundation-source']
ids=[n['id'] for n in wf]
req(ids==['policy-contract','policy-go-tests','consumer-r0','m3-evidence-tests','m3-regression','hosted-only'],
    'R1_DAG_TOPOLOGY_INCOMPLETE')
for i,n in enumerate(wf):req(n['depends_on']==ids[:i],'R1_DAG_DEPENDENCIES_INCOMPLETE')
for token in ('m3_evidence_reconcile.py','test_r1_consumer_access_contract.py'):
    req((ROOT/'scripts/dev/android'/token).exists() if 'reconcile' in token else (ROOT/'tests'/token).exists(),
        'R1_RECEIPTS_UNIT_MISSING')
print('PASS_R1_CONSUMER_POLICY_FOUNDATION_SOURCE_ONLY_NO_EXTERNAL_ACCESS')
