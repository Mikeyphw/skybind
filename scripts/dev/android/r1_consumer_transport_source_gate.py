#!/usr/bin/env python3
"""Candidate R1 read-only consumer transport source gate; NO device activation."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[3]

def check():
    ipc=ROOT/'internal/brokeripc'
    listener=(ipc/'abstract.go').read_text()
    client=(ipc/'client.go').read_text()
    server=(ipc/'server.go').read_text()
    gateway=(ROOT/'internal/brokerruntime/gateway.go').read_text()
    tests=(ipc/'abstract_test.go').read_text()
    abi=json.loads((ROOT/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json').read_text())
    service=(ROOT/'module/service.sh').read_text()
    post=(ROOT/'module/post-fs-data.sh').read_text()
    checks={
       'AUTHENTICATED_ABSTRACT_ENDPOINT': 'ConsumerAbstractEndpoint = "\\x00skybind-r1-consumer-gateway-v1"' in listener and 'net.ListenUnix(' in listener,
       'NO_INACCESSIBLE_FILESYSTEM_PARENT': '/data/adb/skybind' not in listener.split('import (',1)[-1],
       'EXPLICIT_ROOT_ADMISSION': 'os.Geteuid() != 0' in listener and '!s.ExplicitlyEnabled' in listener,
       'BOUND_CONNECTIONS': 'maxAbstractConsumers = 8' in listener and 'sem := make(chan struct{}, maxAbstractConsumers)' in listener,
       'KERNEL_PEER_AND_GRANT_RECHECK': all(x in server for x in ['SO_PEERCRED','s.Verifier.VerifyPeer(kernel)','s.Grants.Authorize(', 'MaxRequestBytes']),
       'ONE_REQUEST_ONE_CONNECTION': 'CloseWrite()' in client and 'MaxResponseBytes+1' in client and 'DisallowUnknownFields()' in client,
       'LIVE_AUTHORITY_ACTIVATION_REQUIRED': 'pm.State() != "CONNECTED_UNQUALIFIED"' in gateway and 'module.Root != ""' in gateway,
       'TESTS_REAL_SOCKET_AND_REVOKE': all(x in tests for x in ['TestAbstractConsumerRealKernelPeerGrantAndRevocation','TestAbstractConsumerRejectsWrongKernelPeer','grants.Revoke(receipt.ID)','wrong UID accessed backend']),
       'NO_DAEMON_AUTO_ACTIVATION': 'StartAbstract(' not in service and 'StartAbstract(' not in post and 'consumer-gateway-v1' not in service and 'consumer-gateway-v1' not in post,
       'NO_SECOND_ISSUER': 'IssueApproved(' not in listener and 'IssueApproved(' not in client and 'brokerissue' not in listener,
       'NO_FALSE_PRODUCTION_CAPABILITY': abi['available_external_capabilities']==[] and abi['external_transport_status']=='NOT_IMPLEMENTED',
       'NO_CONSUMER_MUTATION': all(x not in client for x in ['exec.Command', 'os.OpenFile','rclone serve','su -c']),
    }
    for key,ok in checks.items():print(('PASS_' if ok else 'FAIL_')+key)
    return 0 if all(checks.values()) else 2
if __name__=='__main__':sys.exit(check())
