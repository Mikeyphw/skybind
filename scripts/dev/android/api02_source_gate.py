#!/usr/bin/env python3
"""Static API-02 source contract gate. Does not grant access or qualify devices."""
from pathlib import Path
import re
import tomllib

ROOT=Path(__file__).resolve().parents[3]
def src(path):return (ROOT/path).read_text()

def check():
    cli=src('cmd/skybind/feature.go')
    main=src('cmd/skybind/main.go')
    api=src('internal/featureapi/feature.go')
    daemon=src('internal/daemon/feature_capabilities.go')
    broker=src('internal/brokerruntime/gateway.go')
    extension=src('internal/control/offline_extension_m05ui.go')
    d=tomllib.loads(src('.devtool.toml'))
    assert 'case "feature":' in main and 'RegisterFeatureCapabilities(engine, j)' in main
    assert 'uid != 0' in cli and 'feature.execute' in cli and '--stdin' in cli
    assert 'daemon.Call(ctx, paths.DaemonSocket, req)' in cli
    assert 'checkTopLevel(buf)' in api and 'rejectDuplicateJSON(req.Arguments)' in api
    assert 'request_id' in api and 'feature_version_unsupported' in api
    assert 'feature.execute' in extension and 'feature.capabilities' in extension
    assert 'j.ByRequest(call.RequestID)' in daemon and 'mu.Lock()' in daemon
    assert 'duplicate_request_use_operation_status' in daemon
    assert 'engine.Dispatch(ctx, request)' in daemon
    assert 'g.socket.Start()' in broker # existing R1 opt-in entrypoint unchanged
    allowed=re.findall(r'^\s*"([\w.]+)":\s*protocol\.(?:Query|Preview|Run|Reconcile|Cancel),',api,re.M)
    assert len(allowed)==16 and len(set(allowed))==16
    assert {'mount.start.preview','mount.start','namespace.preview','namespace.apply','operation.events'}.issubset(allowed)
    assert not any(x.startswith(('rclone.','remote.','provider.','config.')) for x in allowed)
    assert not any(x in allowed for x in ('shell.exec','feature.execute'))
    assert 'api02-managed-features' in d['targets']['skybind_release']['workflows']
    for job in ('api02-managed-feature-go','api02-managed-feature-source'):
        assert job in d['targets']['skybind_release']['jobs']
    assert 'api02-managed-features' in d['wrapper']['commands']
    contract=src('docs/contracts/rclone-compat/API02_MANAGED_FEATURES_V1_20261026.md')
    assert 'root-only' in contract and 'API-03' in contract and 'independently attested' in contract
    print('PASS_API02_ROOT_LOCAL_MANAGED_FEATURE_CONTRACT_SOURCE_ONLY')

if __name__=='__main__':check()
