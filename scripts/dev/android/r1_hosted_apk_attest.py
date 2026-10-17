#!/usr/bin/env python3
"""B1-QW3: fail-closed witness for Devtool-authenticated hosted Skybind APK pair.

Requires successful native Actions-06 pipeline and a fresh native Actions-04
remote artifact verification. Uses Devtool's package inspector, NOT the ACTIONS-05
collector hard-wired to devtool-android-build.yml. No installs, builds, or releases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = Path('docs/devtool/r1_android_hosted_pipeline.json')
NAME = 'skybind-r1-android-hosted'
WORKFLOW = 'skybind-android-apks.yml'
ARTIFACT = 'skybind-android-debug-apks-unqualified'
REPO = 'Mikeyphw/skybind'
APP = 'app-debug.apk'
TEST = 'app-debug-androidTest.apk'
MANIFEST = 'android-build-manifest.json'
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_MANIFEST = 32768
HEX32 = re.compile(r'[0-9a-f]{32}\Z')
HEX40 = re.compile(r'[0-9a-f]{40}\Z')
HEX64 = re.compile(r'[0-9a-f]{64}\Z')

class GateError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise GateError(message)

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as inp:
        for b in iter(lambda: inp.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()

def load(path, max_bytes=256*1024):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= max_bytes,
            f'missing, linked or oversized file: {path.name}')
    return json.loads(path.read_text(encoding='utf-8'))

def git(*args):
    p = subprocess.run(['git', '-C', str(ROOT), *args], capture_output=True, text=True, timeout=15)
    require(p.returncode == 0, 'Git identity unavailable')
    return p.stdout.strip()

def source_identity():
    require(not git('status', '--porcelain', '--untracked-files=normal'), 'Git worktree not clean')
    head = git('rev-parse', 'HEAD').lower()
    require(bool(HEX40.fullmatch(head)), 'Invalid Git HEAD')
    remote = git('remote', 'get-url', 'origin')
    require(remote in (f'git@github.com:{REPO}.git', f'https://github.com/{REPO}.git',
                       f'https://github.com/{REPO}'), 'Git origin does not match pinned repository')
    return head

def journal_path(ident):
    require(bool(HEX32.fullmatch(ident)), 'Pipeline ID must be exactly 32 lowercase hex digits')
    home = Path(os.getenv('XDG_STATE_HOME') or (Path.home() / '.local/state'))
    return home / 'devtool' / 'actions' / 'pipelines' / (ident + '.json')

def context(ident):
    head = source_identity()
    obj = load(journal_path(ident))
    require(obj.get('schema') == 1 and obj.get('id') == ident and obj.get('name') == NAME,
            'Pipeline journal identity mismatch')
    require(obj.get('repo_root') == str(ROOT.resolve()) and obj.get('repository', '').lower() == REPO.lower(),
            'Pipeline journal points to wrong repository or working copy')
    require(obj.get('head_sha') == head and obj.get('manifest_file') == PIPELINE.as_posix() and
            obj.get('manifest_sha256') == sha(ROOT / PIPELINE), 'Pipeline source binding mismatch')
    require(obj.get('cancel_requested') is not True, 'Pipeline was cancelled')
    nodes = obj.get('nodes')
    require(isinstance(nodes, dict) and set(nodes) == {'source','policy','build','result','archive'},
            'Unexpected pipeline graph')
    require(all(isinstance(v, dict) and v.get('state') == 'success' for v in nodes.values()),
            'Pipeline must finish all nodes successfully')
    run = nodes['build'].get('run_id')
    artifact = nodes['archive'].get('artifact_id')
    require(type(run) is int and run > 0 and type(artifact) is int and artifact > 0,
            'Missing positive GitHub run/artifact ID')
    require(nodes['result'].get('state') == 'success' and nodes['archive'].get('state') == 'success',
            'GitHub success/verified archive absent')
    require(type(nodes['build'].get('workflow_id')) is int and nodes['build']['workflow_id'] > 0,
            'GitHub workflow identity absent')
    return {'source_sha':head, 'run_id':run, 'artifact_id':artifact,
            'workflow_id':nodes['build']['workflow_id'], 'repository':REPO,
            'pipeline_id':ident}

def native_verify(ctx, auth='gh'):
    require(auth in ('gh', 'env', 'auto'), 'Unauthorized credential source')
    args = ['devtool','-r',str(ROOT),'--no-hud','--no-clipboard','actions','verify',
            '--github-repo',REPO,'--auth',auth,'--run-id',str(ctx['run_id']),
            '--artifact-id',str(ctx['artifact_id']),'--json']
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=180)
    require(p.returncode == 0, 'Devtool Actions-04 remote verification failed: ' + p.stderr[:300])
    outer = json.loads(p.stdout)
    require(outer.get('ok') is True and outer.get('exit_code') == 0, 'Devtool verification returned failure')
    doc = outer.get('data')
    require(isinstance(doc, dict), 'Devtool verification has no machine data')
    return doc

def validate_receipt(ctx, receipt):
    require(receipt.get('phase') == 'ACTIONS-04' and receipt.get('archive_verified') is True,
            'Native Devtool did not authenticate and verify artifact ZIP')
    require(receipt.get('repository', '').lower() == REPO.lower() and
            receipt.get('run_id') == ctx['run_id'] and receipt.get('artifact_id') == ctx['artifact_id'],
            'Native artifact verification identity mismatch')
    digest = receipt.get('sha256')
    require(isinstance(digest, str) and bool(HEX64.fullmatch(digest)), 'Artifact digest invalid')
    path = Path(str(receipt.get('file','')))
    storage = ROOT / '.devtool' / 'artifacts' / 'github-downloads'
    require(not path.is_symlink() and path.is_file() and path.parent.resolve() == storage.resolve(),
            'Archive outside Devtool verified storage')
    require(path.stat().st_size <= MAX_ARCHIVE and sha(path) == digest, 'Archive differs from authenticated digest')
    return path

def registry_attempt(ctx, archive):
    reg = load(ROOT / '.devtool' / 'artifacts' / 'registry.json', 8*1024*1024)
    matches = [r for r in reg.get('items', []) if isinstance(r, dict) and
               isinstance(r.get('metadata'),dict) and
               r['metadata'].get('remote_repository','').lower() == REPO.lower() and
               r['metadata'].get('remote_run_id') == ctx['run_id'] and
               r['metadata'].get('remote_artifact_id') == ctx['artifact_id'] and
               r.get('sha256') == sha(archive)]
    require(len(matches) == 1, 'Expected one canonical Devtool archive registry entry')
    meta = matches[0]['metadata']
    require(meta.get('remote_head_sha') == ctx['source_sha'] and
            meta.get('remote_workflow_id') == ctx['workflow_id'] and
            meta.get('archive_digest_verified') is True, 'Registry source/workflow/digest binding mismatch')
    attempt = meta.get('remote_run_attempt')
    require(type(attempt) is int and attempt > 0, 'Authenticated workflow attempt missing')
    return attempt

def check_pair(ctx, receipt, *, inspection=None, attempt=None):
    """Source/attempt + byte + package/certificate acceptance; inspection injectable for tests."""
    archive = validate_receipt(ctx, receipt)
    if attempt is None:
        attempt = registry_attempt(ctx, archive)
    require(type(attempt) is int and attempt > 0, 'Invalid run attempt')
    with zipfile.ZipFile(archive) as z:
        members = {i.filename:i for i in z.infolist() if not i.is_dir()}
        require(set(members) in ({APP, TEST, MANIFEST},
                {f'android-build-evidence/{x}' for x in (APP, TEST, MANIFEST)}),
                'Unexpected or missing APK/manifest members')
        prefix = 'android-build-evidence/' if MANIFEST not in members else ''
        info = members[prefix + MANIFEST]
        require(0 < info.file_size <= MAX_MANIFEST, 'Hosted manifest absent or oversized')
        doc = json.loads(z.read(prefix+MANIFEST).decode('utf-8'))
        require(doc.get('schema_version') == 1 and
                doc.get('state') == 'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED' and
                doc.get('build_environment') == 'GitHub Actions ubuntu-24.04' and
                doc.get('release_qualified') is False and doc.get('device_qualified') is False,
                'Hosted manifest state is invalid/overclaimed')
        require(doc.get('repository','').lower() == REPO.lower() and
                doc.get('head_sha') == ctx['source_sha'] and
                doc.get('run_id') == str(ctx['run_id']) and
                doc.get('run_attempt') == str(attempt) and
                doc.get('workflow') == 'Skybind Android APKs (hosted-only)',
                'Hosted manifest source/run/attempt/workflow mismatch')
        digest_map = {}
        certs = []
        for key, member, package in (('app', APP,'io.github.mikeyphw.skybind'),
                                     ('test_apk', TEST,'io.github.mikeyphw.skybind.test')):
            item = members[prefix+member]
            declared = doc.get(key)
            require(isinstance(declared, dict) and declared.get('name') == member and
                    type(declared.get('size_bytes')) is int and
                    declared.get('size_bytes') == item.file_size and item.file_size > 0 and
                    item.file_size <= MAX_ARCHIVE and
                    bool(HEX64.fullmatch(str(declared.get('sha256','')))) and
                    bool(HEX64.fullmatch(str(declared.get('certificate_sha256','')))),
                    f'{key}: invalid hosted APK manifest entry')
            h = hashlib.sha256()
            with z.open(item) as s:
                for chunk in iter(lambda:s.read(1024*1024),b''):
                    h.update(chunk)
            require(h.hexdigest() == declared['sha256'], f'{key}: hosted APK digest differs')
            if inspection is None:
                from devtool.actions_android import inspect_android_zip
                check = inspect_android_zip
            else:
                check = inspection
            detail = check(archive, fmt='apk', variant='debug', member=prefix+member,
                           expected_package=package, expected_cert=declared['certificate_sha256'])
            require(detail.get('signature_verified') is True and
                    detail.get('package') == package and
                    detail.get('signer_sha256') == declared['certificate_sha256'] and
                    detail.get('sha256') == declared['sha256'] and
                    detail.get('member') == prefix+member,
                    f'{key}: Devtool package/signature inspection rejected')
            digest_map[key] = declared['sha256']
            certs.append(detail['signer_sha256'])
        require(len(set(certs)) == 1, 'App and instrumentation signed by different certificates')
    return {'schema':'skybind-b1-qw3-v1','status':'PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED',
            'repository':REPO,'head_sha':ctx['source_sha'],'run_id':ctx['run_id'],
            'run_attempt':attempt,'workflow_id':ctx['workflow_id'],
            'artifact_id':ctx['artifact_id'],'artifact_zip_sha256':receipt['sha256'],
            'app_sha256':digest_map['app'],'test_sha256':digest_map['test_apk'],
            'debug_signer_sha256':certs[0], 'github_run_authenticated':True,
            'signatures_inspected':True,'device_qualified':False,'release_qualified':False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-id', required=True)
    parser.add_argument('--auth', choices=['gh','env','auto'], default='gh')
    args = parser.parse_args()
    try:
        ctx = context(args.pipeline_id)
        remote = native_verify(ctx, auth=args.auth)
        output = check_pair(ctx, remote)
        destination = ROOT / 'build' / 'evidence' / 'r1-android-hosted' / args.pipeline_id
        require(not destination.is_symlink(), 'Output evidence location is symlink')
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / 'attestation.json'
        require(not target.exists() and not target.is_symlink(), 'Attestation exists; refusing overwrite')
        with target.open('x',encoding='utf-8') as f:
            json.dump(output,f,indent=2,sort_keys=True)
            f.write('\n')
        print(json.dumps({'status':output['status'],'receipt':str(target),
                          'run_id':ctx['run_id'],'source_sha':ctx['source_sha']},sort_keys=True))
    except Exception as exc:  # Explicitly fail closed on native Devtool/Android tool exceptions.
        print(json.dumps({'status':'FAILED_OR_BLOCKED','reason':str(exc)[:600]},sort_keys=True))
        return 2
    return 0

if __name__ == '__main__':
    sys.exit(main())
