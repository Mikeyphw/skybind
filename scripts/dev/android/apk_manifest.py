#!/usr/bin/env python3
"""Hosted APK manifest producer + local byte verifier. NEVER builds/signs APKs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

CERT_RE = re.compile(r'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F]{64})')

def apk_cert(path: Path):
    apksigner=shutil.which('apksigner')
    if not apksigner:
        home=os.getenv('ANDROID_HOME') or os.getenv('ANDROID_SDK_ROOT')
        if home:
            candidates=sorted(Path(home,'build-tools').glob('*/apksigner'),reverse=True)
            apksigner=str(candidates[0]) if candidates else None
    if not apksigner: return None
    result=subprocess.run([apksigner,'verify','--print-certs',str(path)],capture_output=True,text=True,timeout=60)
    if result.returncode: raise ValueError('APK signature verification failed')
    match=CERT_RE.search(result.stdout)
    if not match: raise ValueError('APK certificate fingerprint unavailable')
    return match.group(1).lower()

def record(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size<=0: raise ValueError('missing or invalid APK')
    if path.suffix!='.apk': raise ValueError('not an APK')
    return {'name':path.name,'size_bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'certificate_sha256':apk_cert(path)}

def create(args):
    if os.environ.get('GITHUB_ACTIONS')!='true' or not all(os.getenv(k) for k in ('GITHUB_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT','GITHUB_WORKFLOW','GITHUB_REPOSITORY','GITHUB_REF')):
        raise ValueError('creation requires authenticated GitHub Actions environment identity')
    app=record(args.app);test=record(args.test_apk)
    if not app['certificate_sha256'] or not test['certificate_sha256']:
        raise ValueError('hosted APK certificate verification required')
    if app['certificate_sha256'] != test['certificate_sha256']:
        raise ValueError('app and instrumentation signing identities differ')
    doc={'schema_version':1,'state':'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED','repository':os.environ['GITHUB_REPOSITORY'],'ref':os.environ['GITHUB_REF'],'head_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],'run_attempt':os.environ['GITHUB_RUN_ATTEMPT'],'workflow':os.environ['GITHUB_WORKFLOW'],'build_environment':'GitHub Actions ubuntu-24.04','gradle':'8.11.1','agp':'8.9.2','kotlin':'2.2.21','jdk':'17','compile_sdk':35,'app_id':'io.github.mikeyphw.skybind','test_app_id':'io.github.mikeyphw.skybind.test','signing':'ephemeral-github-debug','app':app,'test_apk':test,'release_qualified':False,'device_qualified':False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(doc,sort_keys=True,indent=2)+'\n')
    return {'state':doc['state'],'app_sha256':app['sha256'],'test_sha256':test['sha256']}

def verify(args):
    doc=json.loads(args.manifest.read_text())
    if doc['schema_version']!=1 or doc['state']!='CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED' or doc['release_qualified'] is not False or doc['device_qualified'] is not False:raise ValueError('incorrect/overclaimed manifest')
    if not re.fullmatch('[0-9a-f]{40}',doc['head_sha']) or not str(doc['run_id']).isdigit() or not str(doc['run_attempt']).isdigit(): raise ValueError('invalid source/run identity')
    if args.expected_head_sha and doc['head_sha']!=args.expected_head_sha: raise ValueError('wrong source SHA')
    if args.expected_run_id and doc['run_id']!=args.expected_run_id:raise ValueError('wrong GitHub run ID')
    signatures_valid=True
    for key,path in [('app',args.app),('test_apk',args.test_apk)]:
        current=record(path);expected=doc[key]
        if expected['name']!=current['name'] or expected['size_bytes']!=current['size_bytes'] or expected['sha256']!=current['sha256']:
            raise ValueError('APK bytes do not match manifest: '+key)
        if current['certificate_sha256'] is None:
            signatures_valid=False
        elif current['certificate_sha256']!=expected['certificate_sha256']: raise ValueError('APK certificate does not match manifest')
    return {'state':'PASS_LOCAL_HASH_AND_CERT' if signatures_valid else 'PASS_LOCAL_HASH_ONLY_CERT_UNCHECKED','github_run_authenticated':False,'release_qualified':False,'device_qualified':False}

def main():
    ap=argparse.ArgumentParser(description=__doc__);sub=ap.add_subparsers(dest='action',required=True)
    for name in ('create','verify'):
        subp=sub.add_parser(name)
        subp.add_argument('--app',type=Path,required=True)
        subp.add_argument('--test-apk',type=Path,required=True)
        subp.add_argument('--output',type=Path) if name=='create' else subp.add_argument('--manifest',type=Path,required=True)
        if name=='verify':
            subp.add_argument('--expected-head-sha');subp.add_argument('--expected-run-id')
    args=ap.parse_args()
    try: print(json.dumps(create(args) if args.action=='create' else verify(args),sort_keys=True))
    except (ValueError,OSError,KeyError,json.JSONDecodeError) as e:
        print(json.dumps({'state':'FAIL_CLOSED','reason':str(e)}));raise SystemExit(2)
if __name__=='__main__': main()
