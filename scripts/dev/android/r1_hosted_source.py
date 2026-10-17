#!/usr/bin/env python3
"""Source-only B1-QW3 Devtool Actions pipeline gate (no network, APK, device)."""
import json
from pathlib import Path
import tomllib

ROOT=Path(__file__).resolve().parents[3]

def check():
    from r1_hosted_apk_attest import PIPELINE, ARTIFACT, NAME, WORKFLOW, REPO
    doc=json.loads((ROOT/PIPELINE).read_text())
    assert doc['schema']==1 and doc['name']==NAME
    nodes=doc['nodes']
    assert [(n['id'],n['kind']) for n in nodes] == [
        ('source','local-git'),('policy','local-invoke'),('build','github-dispatch'),
        ('result','github-result'),('archive','github-archive')]
    assert nodes[1]['action']=='build-policy' and nodes[1]['target']=='skybind_android_app'
    assert nodes[2]['workflow']==WORKFLOW and nodes[2]['ref']=='main' and nodes[2]['inputs']=={}
    assert nodes[2]['needs']==['source','policy']
    assert nodes[3]['from']=='build' and nodes[3]['needs']==['build']
    assert nodes[4]['from']=='build' and nodes[4]['needs']==['build','result']
    assert nodes[4]['artifact_name']==ARTIFACT
    wf=(ROOT/'.github/workflows'/WORKFLOW).read_text()
    for flag in ('workflow_dispatch:', 'name: Skybind Android APKs (hosted-only)',
                 'name: skybind-android-debug-apks-unqualified', 'assembleDebugAndroidTest',
                 'apk_manifest.py create', 'apk_manifest.py verify'):
        assert flag in wf,flag
    config=tomllib.loads((ROOT/'.devtool.toml').read_text())
    job=config['targets']['skybind_release']['jobs']['r1-hosted-source']
    assert job['metadata']['read_only'] is True
    assert 'r1-hosted-source' in config['targets']['skybind_release']['workflows']
    assert config['wrapper']['commands']['r1-hosted-source']['target']=='skybind_release'
    return {'status':'PASS_B1_QW3_SOURCE_ONLY','pipeline':str(PIPELINE),
            'repository':REPO, 'remote_authenticated':False,'qualified_release':False}

if __name__=='__main__':
    print(json.dumps(check(),sort_keys=True))
