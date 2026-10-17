#!/usr/bin/env python3
"""Source-only B1-QW3 Devtool Actions pipeline gate (no network, APK, device)."""
import json
from pathlib import Path
import tomllib
import re

ROOT=Path(__file__).resolve().parents[3]


# Keep the action's exact input shape pinned. A YAML literal block is treated
# as a single newline-containing package by setup-android@v4.
SDK_PACKAGES = ('platforms;android-35', 'build-tools;35.0.0', 'platform-tools')

def verify_sdk_packages(workflow_text):
    found = re.findall(r"(?m)^[ \t]+packages:[ \t]*([^\r\n]*)$", workflow_text)
    if len(found) != 1:
        raise ValueError('expected exactly one Android SDK packages input')
    raw = found[0].strip()
    if len(raw) < 2 or raw[0] not in ("'", '\"') or raw[-1] != raw[0]:
        raise ValueError('Android SDK packages must be an inline quoted scalar')
    packages = tuple(raw[1:-1].split())
    if packages != SDK_PACKAGES:
        raise ValueError('Android SDK packages must be three space-delimited SDK paths')
    return packages

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
    verify_sdk_packages(wf)
    config=tomllib.loads((ROOT/'.devtool.toml').read_text())
    job=config['targets']['skybind_release']['jobs']['r1-hosted-source']
    assert job['metadata']['read_only'] is True
    assert 'r1-hosted-source' in config['targets']['skybind_release']['workflows']
    assert config['wrapper']['commands']['r1-hosted-source']['target']=='skybind_release'
    return {'status':'PASS_B1_QW3_SOURCE_ONLY','pipeline':str(PIPELINE),
            'repository':REPO, 'remote_authenticated':False,'qualified_release':False}

if __name__=='__main__':
    print(json.dumps(check(),sort_keys=True))
