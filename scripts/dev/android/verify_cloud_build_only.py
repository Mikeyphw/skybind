#!/usr/bin/env python3
"""Source-only guard: no local Android application builds via Devtool."""
from pathlib import Path
import tomllib
import json

ROOT = Path(__file__).resolve().parents[3]

def check():
    config=tomllib.loads((ROOT/'.devtool.toml').read_text())
    target=config['targets']['skybind_android_app']
    if target['runner']!='command' or target['root']!='android-app':
        raise ValueError('Android app target must remain nonbuilding command runner')
    for job_name, job in target.get('jobs',{}).items():
        text=' '.join(str(v) for v in job.get('command',[])).lower()
        if any(bad in text for bad in ('gradle','assemble','bundle','build-apk','build-app')):
            raise ValueError('local APK builder in Devtool Android app job: '+job_name)
    for name, candidate in config['targets'].items():
        if candidate.get('runner') == 'android' and candidate.get('root') in {'android-app','tests/device/probe-app'}:
            raise ValueError('direct local APK builder still registered: '+name)
        for workflow_name, entries in candidate.get('workflows',{}).items():
            if 'runner:android#build' in str(entries) or 'runner:android#package' in str(entries):
                raise ValueError('local Android build workflow still reachable: '+name+'#'+workflow_name)
    legacy=config['targets']['skybind_app_probe']
    if legacy['runner']!='command' or 'legacy-cloud-only-block' not in str(legacy['workflows'].get('app-probe-build')):
        raise ValueError('legacy Q10 local builder is not fail-closed')
    build_settings=(ROOT/'android-app/build.gradle.kts').read_text()
    if '2.2.21' not in build_settings or '8.9.2' not in build_settings:
        raise ValueError('unreviewed Kotlin/AGP build toolchain drift')
    workflow=(ROOT/'.github/workflows/skybind-android-apks.yml').read_text()
    for required in ['workflow_dispatch:','runs-on: ubuntu-24.04',':app:assembleDebug',':app:assembleDebugAndroidTest','android-build-manifest.json','upload-artifact@']:
        if required not in workflow: raise ValueError('missing GitHub-only build requirement: '+required)
    if not (ROOT/'android-app/app/src/main/AndroidManifest.xml').is_file(): raise ValueError('missing app manifest')
    return {'status':'PASS_SOURCE_POLICY_ONLY','android_app_local_build_enabled':False,'apk_build_authority':'github-actions-only','remote_build_verified':False}

if __name__=='__main__':
    try: print(json.dumps(check(),sort_keys=True))
    except (ValueError,KeyError,OSError) as e:
        print(json.dumps({'status':'FAILED_POLICY','reason':str(e)}));raise SystemExit(2)
