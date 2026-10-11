#!/usr/bin/env python3
"""Compose *unqualified* full Skybind candidates from exact successful Q04 CI bytes.

This is not a release gate or a trust signer. Q04 evidence is an explicitly selected
unattested input; all external signatures and physical Android checks remain pending.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/runtime'))
sys.path.insert(0, str(ROOT / 'scripts/dev/release'))
import source_build as sb
import skybind_runtime as rt
import skybind_release as release

INPUTS = ROOT / 'scripts/dev/integration/q04.inputs.json'
LOCK = ROOT / 'scripts/dev/runtime/source.lock.json'
LANES = ('A', 'B')
SHA = re.compile(r'[a-f0-9]{64}\Z')
COMMIT = re.compile(r'[a-f0-9]{40}\Z')

class Rejected(ValueError):
    pass


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read_regular(path: Path, *, max_bytes: int = 1024 * 1024) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > max_bytes:
        raise Rejected('missing, linked or oversized input: ' + str(path))
    return path.read_bytes()


def json_input(path: Path) -> dict:
    data = json.loads(read_regular(path))
    if not isinstance(data, dict):
        raise Rejected('expected JSON object: ' + str(path))
    return data


def regular(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise Rejected('input missing or not regular: ' + str(path))
    return path


def evidence_inventory(root: Path, policy: Path = INPUTS, lock_path: Path = LOCK) -> dict:
    if root.is_symlink() or not root.is_dir():
        raise Rejected('Q04 evidence root missing or linked')
    cfg = json_input(policy)
    lock = json_input(lock_path)
    if cfg.get('schema_version') != 1 or cfg.get('kind') != 'SB_Q04_RAW_BUILD_INPUT_SELECTION_NOT_ATTESTATION':
        raise Rejected('wrong Q04 evidence selection identity')
    if cfg.get('independent_attestation') is not False or cfg.get('physical_device_tested') is not False or (cfg.get('gate_g01'), cfg.get('final_seal')) != ('BLOCKED', 'NOT_ISSUED'):
        raise Rejected('Q04 selection must not self-certify')
    if not COMMIT.fullmatch(cfg.get('run_head_sha') or '') or not COMMIT.fullmatch(cfg.get('bclone_commit') or ''):
        raise Rejected('invalid selected Git commit')
    for field in ('bclone_binary_sha256','bclone_zip_sha256','newfuture_zip_sha256','newfuture_original_sha256'):
        if not SHA.fullmatch(cfg.get(field) or ''):
            raise Rejected('invalid selected SHA: ' + field)
    if cfg.get('bclone_commit') != lock['bclone']['commit'] or cfg['newfuture_original_sha256'] != lock['newfuture']['archive_sha256']:
        raise Rejected('Q04 input selection does not match current source lock')
    if cfg.get('repository') != 'Mikeyphw/skybind' or not isinstance(cfg.get('run_id'), int) or cfg['run_id'] <= 0:
        raise Rejected('invalid repository/run selection')
    run = json_input(root / 'run.json')
    if (run.get('headSha'), run.get('headBranch'), run.get('status'), run.get('conclusion'), run.get('url'), run.get('workflowName')) != (
        cfg['run_head_sha'], 'main', 'completed', 'success',
        f"https://github.com/{cfg['repository']}/actions/runs/{cfg['run_id']}",
        'Skybind pinned Android providers (UNATTESTED)'):
        raise Rejected('Q04 run identity/status mismatch')
    jobs = run.get('jobs')
    required_jobs = {'pinned-provider-lanes (A)', 'pinned-provider-lanes (B)', 'compare-independent-builds'}
    if not isinstance(jobs, list) or len(jobs) != 3 or {j.get('name') for j in jobs if isinstance(j,dict)} != required_jobs or any(j.get('status') != 'completed' or j.get('conclusion') != 'success' for j in jobs):
        raise Rejected('Q04 jobs missing or failed')
    base = root / 'artifacts'
    if base.is_symlink() or not base.is_dir():
        raise Rejected('Q04 artifacts directory missing/linked')
    if {p.name for p in base.iterdir()} != {'skybind-provider-lane-A','skybind-provider-lane-B','skybind-provider-unattested-comparison'}:
        raise Rejected('unexpected Q04 artifact inventory')
    compare_path = base / 'skybind-provider-unattested-comparison/comparison.json'
    compare = json_input(compare_path)
    expected = {
        'schema_version':1, 'status':'BYTE_IDENTICAL_UNATTESTED',
        'source_commit':cfg['bclone_commit'], 'bclone_binary_sha256':cfg['bclone_binary_sha256'],
        'bclone.zip_sha256':cfg['bclone_zip_sha256'], 'newfuture.zip_sha256':cfg['newfuture_zip_sha256'],
        'gate_g01':'BLOCKED', 'final_seal':'NOT_ISSUED',
    }
    if compare != expected:
        raise Rejected('comparison identity/digests or trust ceiling mismatch')
    paths = {}
    hashes = {}
    for lane in LANES:
        d = base / f'skybind-provider-lane-{lane}'
        if d.is_symlink() or not d.is_dir() or {p.name for p in d.iterdir()} != {'bclone_build','packages','newfuture-inspection.json'}:
            raise Rejected('lane inventory changed: '+lane)
        packages = d / 'packages'
        if packages.is_symlink() or not packages.is_dir() or {p.name for p in packages.iterdir()} != {'newfuture.zip','bclone.zip'}:
            raise Rejected('lane packages changed: '+lane)
        build = d / 'bclone_build'
        try:
            proof = sb.verify(build)
        except (sb.Rejected, OSError, ValueError, KeyError, TypeError) as e:
            raise Rejected('source build receipt invalid: '+str(e)) from e
        if (proof.get('source_commit'),proof.get('lock_sha256'),proof.get('binary_sha256'),proof.get('go_version'),proof.get('ndk_revision')) != (
            cfg['bclone_commit'],sha(lock_path),cfg['bclone_binary_sha256'],lock['bclone']['go_version'],lock['bclone']['ndk_revision']):
            raise Rejected('source receipt mismatches Q04 selection or current lock')
        builds = {}
        for provider in ('bclone','newfuture'):
            archive = regular(packages / (provider+'.zip'))
            if sha(archive) != cfg[provider+'_zip_sha256']:
                raise Rejected('unexpected '+provider+' packaged bytes')
            try:
                pro = rt.verify_package(archive)
            except (rt.Reject, OSError, ValueError, KeyError) as e:
                raise Rejected('runtime package failed verification: '+str(e)) from e
            if pro['provider'] != provider or pro['newfuture']['archive_sha256'] != cfg['newfuture_original_sha256']:
                raise Rejected('runtime provenance input mismatch')
            builds[provider] = archive
            hashes[provider] = sha(archive)
        inspection = json_input(d/'newfuture-inspection.json')
        if (inspection.get('archive_sha256') != cfg['newfuture_original_sha256'] or
            inspection.get('status') != 'PIN_MATCH_UNATTESTED' or
            inspection.get('gate_g01') != 'BLOCKED' or
            inspection.get('final_seal') != 'NOT_ISSUED'):
            raise Rejected('newfuture inspection source/custody mismatch')
        # The helper delivered by either provider is the same originally
        # selected prebuilt; bclone's packaged runtime is the actual Q04 ELF.
        with zipfile.ZipFile(builds['newfuture']) as nf, zipfile.ZipFile(builds['bclone']) as bc:
            helper = 'system/vendor/bin/fusermount3'
            if hashlib.sha256(nf.read(helper)).digest() != hashlib.sha256(bc.read(helper)).digest():
                raise Rejected('providers supply different FUSE helper bytes')
            if hashlib.sha256(bc.read('system/bin/rclone')).hexdigest() != cfg['bclone_binary_sha256']:
                raise Rejected('bclone package substitutes built executable')
        paths[lane] = {'packages':builds,'binary':regular(build/'rclone'),'inspection':inspection}
    for name in ('binary','packages'):
        if name == 'binary':
            if sha(paths['A'][name]) != sha(paths['B'][name]):
                raise Rejected('bclone lane bytes differ')
        else:
            for provider in ('bclone','newfuture'):
                if sha(paths['A'][name][provider]) != sha(paths['B'][name][provider]):
                    raise Rejected(provider+' package lanes differ')
    return {'selection':cfg,'run':run,'comparison':compare,'paths':paths,'hashes':hashes}


def assemble(root: Path, native: Path, output: Path, policy: Path = INPUTS, lock_path: Path = LOCK) -> dict:
    inventory = evidence_inventory(root,policy,lock_path)
    native = regular(native)
    if not release.is_arm64_elf(read_regular(native, max_bytes=150*1024*1024)):
        raise Rejected('native Skybind executable not Android ARM64 ELF')
    if output.is_symlink() or (output.exists() and (not output.is_dir() or list(output.iterdir()))):
        raise Rejected('output must be an empty non-linked directory')
    if output.resolve() == root.resolve() or root.resolve() in output.resolve().parents:
        raise Rejected('output must be outside Q04 evidence')
    output.mkdir(parents=True, exist_ok=True)
    produced = {}
    try:
        for provider in ('newfuture','bclone'):
            dst = output / ('skybind-'+provider+'-CANDIDATE-UNQUALIFIED.zip')
            data, manifest = release.collect(inventory['paths']['A']['packages'][provider],native,ROOT/'module',ROOT/'module/webroot')
            release.write_zip(dst,data)
            if release.verify_release(dst)['qualification'] != 'CANDIDATE_ONLY_NOT_SEALED':
                raise Rejected('not an unsealed candidate')
            produced[provider] = {'file':dst.name, 'sha256':sha(dst), 'provider_package_sha256':inventory['hashes'][provider]}
        report = {
            'schema_version':1,'status':'COMPLETE_CANDIDATE_UNQUALIFIED',
            'provenance':'Q04_RAW_BYTE_IDENTICAL_UNATTESTED','provider_run_id':inventory['selection']['run_id'],
            'provider_run_commit':inventory['selection']['run_head_sha'],
            'skybind_native_sha256':sha(native), 'skybind_goos':'android','skybind_goarch':'arm64',
            'candidates':produced,'physical_device_tested':False,'independent_attestation':False,
            'gate_g01':'BLOCKED','other_gates':'BLOCKED','final_seal':'NOT_ISSUED',
        }
        (output/'candidate-evidence.json').write_bytes(rt.canonical(report))
        return report
    except BaseException:
        for f in output.iterdir():
            if f.is_file() and not f.is_symlink():f.unlink()
        raise


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--evidence-root',type=Path,required=True)
    parser.add_argument('--selection',type=Path,default=INPUTS)
    parser.add_argument('--lock',type=Path,default=LOCK)
    parser.add_argument('--native',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        if args.native or args.output:
            if not args.native or not args.output:
                raise Rejected('candidate needs native and output together')
            result=assemble(args.evidence_root,args.native,args.output,args.selection,args.lock)
        else:
            i=evidence_inventory(args.evidence_root,args.selection,args.lock)
            result={'status':'Q04_RAW_INPUTS_VERIFIED_UNATTESTED',
                    'run_id':i['selection']['run_id'],'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED'}
        print(json.dumps(result,sort_keys=True))
        return 0
    except (Rejected,rt.Reject,release.Reject,OSError,ValueError,KeyError,TypeError) as e:
        print('SB-Q05 candidate rejected: '+str(e),file=sys.stderr)
        return 3

if __name__=='__main__':
    sys.exit(main())
