#!/usr/bin/env python3
"""Deterministic Skybind *candidate* ZIP from verified build-time runtime inputs.

Producing a candidate never issues a release seal. Installed runtime is immutable;
there are no on-device provider selectors, mutable runtime downloads or migrations.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import os
import re
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
RUNTIME_TOOL = ROOT / 'scripts/dev/runtime/skybind_runtime.py'
sys.path.insert(0, str(RUNTIME_TOOL.parent))
from skybind_runtime import verify_package, is_arm64_elf, Reject, digest, canonical

MAX_TOTAL = 512 * 1024 * 1024
MAX_FILE = 256 * 1024 * 1024
ALLOWED_MODULE = {'module.prop','customize.sh','service.sh','post-fs-data.sh','action.sh','uninstall.sh'}
MANDATORY_WEB = {'index.html', 'style.css','app.js','model.js','bridge.js','icon.png','platform.json','config.json'}


def safe_path(name: str) -> bool:
    return bool(name) and not name.startswith('/') and not name.endswith('/') and '\\' not in name and all(p not in ('','.', '..') for p in name.split('/'))


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def checked_source(path: Path, limit: int = MAX_FILE) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise Reject('missing/linked/oversize source: ' + str(path))
    return path.read_bytes()


def zip_members(path: Path) -> dict[str, bytes]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_TOTAL:
        raise Reject('unsafe input archive')
    result = {}
    total = 0
    with zipfile.ZipFile(path) as z:
        for e in z.infolist():
            name = e.filename
            mode = (e.external_attr >> 16) & 0xffff
            if not safe_path(name) or e.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise Reject('invalid archive entry')
            if name in result or e.file_size > MAX_FILE or e.file_size < 1:
                raise Reject('duplicate/oversized/empty member')
            total += e.file_size
            if total > MAX_TOTAL:
                raise Reject('aggregate size limit')
            result[name] = z.read(e)
    return result


def verify_installed_runtime(files: dict[str, bytes]) -> dict:
    """Cross-check the assembled module against the on-device Go authority.

    This verifies the *exact* root-level provenance and every referenced member,
    not just the input runtime archive. It never substitutes an unpinned provider.
    """
    try:
        provenance = json.loads(files['runtime.provenance.json'])
        if not isinstance(provenance, dict) or provenance.get('schema_version') != 1 or provenance.get('product') != 'Skybind' or provenance.get('arch') != 'arm64':
            raise Reject('invalid installed runtime provenance schema')
        if provenance.get('provider') not in ('newfuture', 'bclone') or provenance.get('engine_path') != 'system/bin/rclone' or provenance.get('helper_path') != 'system/vendor/bin/fusermount3':
            raise Reject('invalid runtime authority identity')
        required = provenance.get('files')
        if not isinstance(required, dict) or not 3 <= len(required) <= 66:
            raise Reject('invalid runtime provenance inventory')
        for name, record in required.items():
            if not isinstance(name, str) or not safe_path(name) or not name.startswith('system/') or not isinstance(record, dict):
                raise Reject('invalid runtime member name')
            blob = files.get(name)
            if blob is None or record.get('sha256') != sha(blob) or record.get('size') != len(blob) or not blob:
                raise Reject('installed runtime member digest/size mismatch: ' + name)
        for name in ('system/bin/rclone', 'system/vendor/bin/fusermount3'):
            if name not in required or not is_arm64_elf(files[name]):
                raise Reject('required runtime ELF missing from provenance')
        return provenance
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        if isinstance(exc, Reject):
            raise
        raise Reject('invalid installed runtime provenance') from exc


def collect(runtime: Path, binary: Path, module: Path, webroot: Path) -> tuple[dict[str, bytes], dict]:
    proven = verify_package(runtime)
    engine = zip_members(runtime)
    if not {'system/bin/rclone','system/vendor/bin/fusermount3','runtime.provenance.json','SHA256SUMS','module.prop'} <= engine.keys():
        raise Reject('invalid build-time runtime inventory')
    # Input archive must be the known, complete, hash-verified runtime package.
    payload = {n: b for n, b in engine.items() if n.startswith('system/')}
    # The installed runtime authority reads this root-level file directly.
    # Never discard or regenerate upstream build provenance during composition.
    payload['runtime.provenance.json'] = engine['runtime.provenance.json']
    verify_installed_runtime(payload)
    if not {'system/bin/rclone','system/vendor/bin/fusermount3'} <= payload.keys():
        raise Reject('runtime binary/helper missing')
    app = checked_source(binary)
    if not is_arm64_elf(app):
        raise Reject('Skybind native binary must be Android ARM64 ELF')
    payload['system/bin/skybind'] = app
    for name in sorted(ALLOWED_MODULE):
        payload[name] = checked_source(module/name, 128*1024)
    if not payload['module.prop'].startswith(b'id=skybind\n'):
        raise Reject('module identity mismatch')
    for p in webroot.iterdir():
        if p.is_dir() or p.name == '.gitkeep':
            continue
        name = p.name
        if not safe_path(name) or name.startswith('.'):
            raise Reject('unsafe WebUI asset name')
        payload['webroot/'+name] = checked_source(p, 10*1024*1024)
    if not {'webroot/'+x for x in MANDATORY_WEB} <= payload.keys():
        raise Reject('incomplete original WebUI')
    sbom = {
      'spdxVersion':'SPDX-2.3','dataLicense':'CC0-1.0',
      'SPDXID':'SPDXRef-DOCUMENT','name':'Skybind-Android-module-candidate',
      'documentNamespace':'https://skybind.invalid/spdx/'+sha(canonical({n:sha(b) for n,b in sorted(payload.items())})),
      'creationInfo':{'creators':['Tool: skybind_release.py'],'created':'1980-01-01T00:00:00Z'},
      'files':[{'fileName':'./'+n,'SPDXID':'SPDXRef-File-'+sha(n.encode())[:16],
                'checksums':[{'algorithm':'SHA256','checksumValue':sha(b)}],
                'licenseConcluded':'NOASSERTION','copyrightText':'NOASSERTION'}
               for n,b in sorted(payload.items())],
    }
    payload['sbom.spdx.json'] = canonical(sbom)
    info = {
      'schema_version':1,'product':'skybind', 'qualification':'CANDIDATE_ONLY_NOT_SEALED',
      'runtime_provider':proven['provider'],
      'runtime_package_sha256':sha(runtime.read_bytes()),
      'runtime_provenance_sha256':sha(engine['runtime.provenance.json']),
      'files':{n:{'sha256':sha(b),'size':len(b)} for n,b in sorted(payload.items())},
    }
    payload['skybind.manifest.json'] = canonical(info)
    payload['SHA256SUMS'] = ''.join(f'{sha(payload[n])}  {n}\n' for n in sorted(payload)).encode()
    return payload, info


def write_zip(path:Path, payload:dict[str,bytes]) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    temp = path.with_name(path.name+'.incomplete')
    if temp.exists(): raise Reject('incomplete output exists; inspect it first')
    try:
        with zipfile.ZipFile(temp,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for name,data in sorted(payload.items()):
                if not safe_path(name) or not data: raise Reject('invalid output inventory')
                info=zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_STORED
                executable = name.startswith('system/bin/') or name=='system/vendor/bin/fusermount3' or name in (ALLOWED_MODULE - {'module.prop'})
                info.external_attr=(0o100755 if executable else 0o100644)<<16
                z.writestr(info,data)
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()


def verify_release(path:Path) ->dict:
    entries=zip_members(path)
    if not {'system/bin/skybind','system/bin/rclone','system/vendor/bin/fusermount3','skybind.manifest.json','SHA256SUMS'} <= entries.keys():
        raise Reject('incomplete module package')
    manifest=json.loads(entries['skybind.manifest.json'])
    verify_installed_runtime(entries)
    if manifest.get('runtime_provenance_sha256') != sha(entries['runtime.provenance.json']):
        raise Reject('release provenance identity mismatch')
    if manifest.get('qualification')!='CANDIDATE_ONLY_NOT_SEALED' or manifest.get('product')!='skybind' or manifest.get('schema_version')!=1:
        raise Reject('forged/missing candidate status')
    if set(manifest['files'])!=set(entries)-{'skybind.manifest.json','SHA256SUMS'}:
        raise Reject('manifest inventory mismatch')
    if not {'webroot/'+x for x in MANDATORY_WEB} <= set(entries):
        raise Reject('original WebUI incomplete')
    try:
        sbom=json.loads(entries['sbom.spdx.json'])
        if sbom['spdxVersion']!='SPDX-2.3' or sbom['SPDXID']!='SPDXRef-DOCUMENT':
            raise Reject('invalid SPDX bill of materials')
        sbom_items={it['fileName'][2:]:it['checksums'][0]['checksumValue'] for it in sbom['files']}
        if sbom_items != {n:sha(b) for n,b in entries.items() if n not in ('sbom.spdx.json','skybind.manifest.json','SHA256SUMS')}:
            raise Reject('SPDX file inventory/checksum mismatch')
    except (IndexError,TypeError,KeyError):
        raise Reject('malformed SPDX bill of materials')
    for name, evidence in manifest['files'].items():
        b=entries[name]
        if sha(b)!=evidence['sha256'] or len(b)!=evidence['size']:
            raise Reject('tampered member: '+name)
    for executable in ('system/bin/skybind','system/bin/rclone','system/vendor/bin/fusermount3'):
        if not is_arm64_elf(entries[executable]):raise Reject('invalid installed ARM64 binary')
    expected={f'{sha(b)}  {n}' for n,b in entries.items() if n!='SHA256SUMS'}
    if set(entries['SHA256SUMS'].decode().splitlines())!=expected:raise Reject('incorrect SHA256SUMS')
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if names!=sorted(names):raise Reject('noncanonical ZIP ordering')
        for zi in z.infolist():
            name=zi.filename
            if zi.date_time!=(1980,1,1,0,0,0):raise Reject('nondeterministic ZIP timestamps')
            exe=(name.startswith('system/bin/') or name=='system/vendor/bin/fusermount3' or name in (ALLOWED_MODULE-{'module.prop'}))
            expected_mode = 0o100755 if exe else 0o100644
            if ((zi.external_attr>>16)&0xffff)!=expected_mode:raise Reject('invalid mode')
    return manifest


def main()->int:
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest='command',required=True)
    b=s.add_parser('candidate')
    b.add_argument('--runtime',type=Path,required=True);b.add_argument('--skybind-arm64',type=Path,required=True)
    b.add_argument('--module',type=Path,default=ROOT/'module');b.add_argument('--webroot',type=Path,default=ROOT/'module/webroot');b.add_argument('--output',type=Path,required=True)
    v=s.add_parser('verify');v.add_argument('archive',type=Path)
    args=p.parse_args()
    try:
        if args.command=='candidate':
            payload,info=collect(args.runtime,args.skybind_arm64,args.module,args.webroot)
            write_zip(args.output,payload)
            verify_release(args.output)
            print(json.dumps({'status':'CANDIDATE_ONLY_NOT_SEALED','sha256':sha(args.output.read_bytes()),'provider':info['runtime_provider']}))
        else:
            info=verify_release(args.archive)
            print(json.dumps({'status':info['qualification'],'sha256':sha(args.archive.read_bytes())}))
        return 0
    except (Reject, OSError, KeyError, ValueError, TypeError, zipfile.BadZipFile) as e:
        print('Skybind release rejected: '+str(e),file=sys.stderr);return 1
if __name__=='__main__':sys.exit(main())
