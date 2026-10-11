#!/usr/bin/env python3
"""SB-Q02: immutable, offline-source, Android/arm64 bclone build and comparison.

No ref resolver, scheduled upgrades, runtime installation, trust-signing, or gate promotion.
A source lock is an INPUT constraint, not a third-party authenticity attestation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOCK = ROOT / 'scripts/dev/runtime/source.lock.json'
PIN_GO = '1.27.2'
PIN_NDK = '28.2.13676358'
API_LEVEL = 21
BCLONE_REPO = 'BenjiThatFoxGuy/bclone'
NEWFUTURE_REPO = 'NewFuture/rclone-fuse3-magisk'
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
NDK_HOST = 'linux-x86_64'   # CI builds on a fresh Ubuntu runner; Termux-native unsupported.
ALLOWED_ANDROID_LIBS = frozenset({'libc.so', 'libm.so', 'libdl.so', 'liblog.so', 'libz.so',
                                   'libandroid.so', 'libstdc++.so'})

class Rejected(ValueError):
    pass


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def filehash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True) + '\n').encode()


def command(args: list[str], *, cwd: Path | None = None, env: dict | None = None,
            timeout: int = 1800, allow_fail: bool = False) -> str:
    cp = subprocess.run(args, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, timeout=timeout, check=False)
    if cp.returncode and not allow_fail:
        raise Rejected(f'command failed ({cp.returncode}): {args[0]} {args[1:3]}: {cp.stderr[-1000:]}')
    return cp.stdout.strip()


def load_lock(path: Path) -> dict:
    try:
        obj = json.loads(path.read_text(encoding='utf-8'))
        nf, bc = obj['newfuture'], obj['bclone']
    except (KeyError, ValueError, OSError, TypeError) as e:
        raise Rejected('missing or malformed source.lock.json') from e
    if obj.get('schema') != 1 or nf.get('repository') != NEWFUTURE_REPO or bc.get('repository') != BCLONE_REPO:
        raise Rejected('provider identity/schema changed')
    if nf.get('tag') != 'v1.75.0' or nf.get('asset') != 'magisk-rclone_arm64-v8a.zip':
        raise Rejected('NewFuture release identity changed; new independent review required')
    if not SHA256.fullmatch(nf.get('archive_sha256') or ''):
        raise Rejected('BLOCKED: independently reviewed NewFuture SHA256 pin is missing/invalid')
    if not COMMIT.fullmatch(bc.get('commit') or ''):
        raise Rejected('BLOCKED: independently reviewed bclone full commit pin is missing/invalid')
    if bc.get('ndk_revision') != PIN_NDK or bc.get('go_version') not in (PIN_GO, 'go'+PIN_GO):
        raise Rejected('BLOCKED: reviewed Go 1.27.2 and NDK 28.2.13676358 pins required')
    return obj


def verify_checkout(source: Path, commit: str) -> tuple[str, str]:
    if source.is_symlink() or not source.is_dir():
        raise Rejected('source checkout must be a real directory')
    for name in ('go.mod', 'go.sum'):
        p = source / name
        if not p.is_file() or p.is_symlink():
            raise Rejected('source missing regular '+name)
    head = command(['git', 'rev-parse', 'HEAD'], cwd=source).lower()
    if head != commit:
        raise Rejected('source HEAD is not pinned commit')
    if command(['git', 'symbolic-ref', '-q', 'HEAD'], cwd=source, allow_fail=True):
        raise Rejected('checkout must be detached at the reviewed commit')
    if command(['git', 'status', '--porcelain=v1', '--untracked-files=all'], cwd=source):
        raise Rejected('source checkout is dirty (including untracked files)')
    origin = command(['git', 'remote', 'get-url', 'origin'], cwd=source)
    if origin.rstrip('/').removesuffix('.git') != 'https://github.com/' + BCLONE_REPO:
        raise Rejected('upstream Git origin differs from reviewed repository')
    return filehash(source/'go.mod'), filehash(source/'go.sum')


def verify_toolchain(ndk: Path) -> tuple[Path, Path, str]:
    if ndk.is_symlink() or not ndk.is_dir():
        raise Rejected('NDK must be a real directory')
    props = ndk/'source.properties'
    if not props.is_file() or not re.search(r'^Pkg\.Revision\s*=\s*'+re.escape(PIN_NDK)+r'\s*$',
                                            props.read_text(), flags=re.M):
        raise Rejected('NDK source.properties revision mismatch')
    # GOHOSTOS must be linux and amd64: pinned NDK host prebuilt exists for this build lane.
    got = command(['go', 'version'], timeout=20)
    if not re.fullmatch(r'go version go'+re.escape(PIN_GO)+r' linux/amd64', got):
        raise Rejected('host Go toolchain differs from pinned Go '+PIN_GO+' linux/amd64: '+got)
    bin_dir = ndk/'toolchains/llvm/prebuilt'/NDK_HOST/'bin'
    cc = bin_dir/f'aarch64-linux-android{API_LEVEL}-clang'
    readelf = bin_dir/'llvm-readelf'
    if not cc.is_file() or not readelf.is_file() or not os.access(cc, os.X_OK) or not os.access(readelf, os.X_OK):
        raise Rejected('pinned NDK Android API21 compiler/readelf missing')
    version = command([str(cc), '--version'], timeout=20).splitlines()[0]
    if 'clang' not in version.lower():
        raise Rejected('NDK compiler is not clang')
    return cc, readelf, version


def inspect_elf(binary: Path, readelf: Path) -> dict:
    if not binary.is_file() or binary.is_symlink():
        raise Rejected('Android ELF is not a regular file')
    with binary.open('rb') as fh:
        head = fh.read(64)
    if len(head) < 64 or head[:7] != b'\x7fELF\x02\x01\x01' or int.from_bytes(head[18:20], 'little') != 183:
        raise Rejected('not a little-endian ELF64 AArch64 executable')
    if int.from_bytes(head[16:18], 'little') not in (2, 3):
        raise Rejected('ELF type must be EXEC or DYN')
    header = command([str(readelf), '-h', str(binary)], timeout=30)
    segments = command([str(readelf), '-l', str(binary)], timeout=30)
    dynamic = command([str(readelf), '-d', str(binary)], timeout=30)
    if 'AArch64' not in header or 'ELF64' not in header:
        raise Rejected('NDK llvm-readelf contradicts ELF64 ARM64 header')
    interpreters = re.findall(r'Requesting program interpreter:\s*([^\]]+)', segments)
    if any(value.strip() != '/system/bin/linker64' for value in interpreters):
        raise Rejected('ELF requests non-Android dynamic linker')
    needed = sorted(re.findall(r'Shared library:\s*\[([^\]]+)\]', dynamic))
    if any(lib not in ALLOWED_ANDROID_LIBS for lib in needed):
        raise Rejected('unexpected/non-platform Android shared library: '+str(needed))
    return {'format': 'ELF64', 'machine': 'AArch64', 'abi': 'arm64-v8a',
            'interpreter': interpreters[0].strip() if interpreters else None, 'needed': needed}


def build(source: Path, ndk: Path, output: Path, lock_path: Path = DEFAULT_LOCK) -> dict:
    lock = load_lock(lock_path)    # Reject *before* executing toolchain/download/build.
    if source.is_symlink() or ndk.is_symlink():
        raise Rejected('symlinked source/NDK is not permitted')
    source = source.resolve(strict=True)
    ndk = ndk.resolve(strict=True)
    output = output.resolve()
    # Prevent output inside immutable checkout (would dirty checkout after preflight).
    if output == source or source in output.parents:
        raise Rejected('output cannot be inside source checkout')
    mod, sums = verify_checkout(source, lock['bclone']['commit'])
    cc, readelf, cc_version = verify_toolchain(ndk)
    if output.exists() and any(output.iterdir()):
        raise Rejected('output directory must be empty: refuse stale build/provenance')
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='skybind-q02-') as temp:
            cache = Path(temp)
            # Deliberately do not inherit ambient Go/CGO configuration, GOPATH, GOPRIVATE,
            # GOFLAGS or compiler flags. Go modules are verified via pinned go.sum and sumdb.
            env = {k: os.environ[k] for k in ('PATH','SSL_CERT_FILE','SSL_CERT_DIR','HTTPS_PROXY','HTTP_PROXY','NO_PROXY')
                   if k in os.environ}
            env.update({'HOME': str(cache/'home'), 'GOPATH': str(cache/'gopath'),
                        'GOMODCACHE': str(cache/'gomod'), 'GOCACHE': str(cache/'gocache'),
                        'GOTMPDIR': str(cache/'tmp'), 'TMPDIR': str(cache/'tmp'),
                        'GOOS':'android', 'GOARCH':'arm64', 'CGO_ENABLED':'1', 'CC':str(cc),
                        'CC_FOR_TARGET':str(cc), 'GOWORK':'off', 'GOTOOLCHAIN':'local',
                        'GOENV':'off', 'GOFLAGS':'', 'GOPROXY':'https://proxy.golang.org',
                        'GOSUMDB':'sum.golang.org', 'GONOSUMDB':'', 'GONOPROXY':'',
                        'GOPRIVATE':'', 'CGO_LDFLAGS':'-llog', 'SOURCE_DATE_EPOCH':'0',
                        'TZ':'UTC', 'LC_ALL':'C'})
            for name in ('home','gopath','gomod','gocache','tmp'):
                (cache/name).mkdir()
            graph = command(['go','list','-mod=readonly','-m','all'], cwd=source, env=env)
            if not graph.strip():
                raise Rejected('Go module dependency graph empty')
            graph_hash = digest((graph+'\n').encode())
            binary = output/'rclone'
            command(['go','build','-mod=readonly','-trimpath','-buildvcs=false',
                     '-tags=android','-ldflags=-buildid= -s -w','-o',str(binary),'.'],
                    cwd=source, env=env)
        if (filehash(source/'go.mod'), filehash(source/'go.sum')) != (mod, sums):
            raise Rejected('Go module metadata was mutated')
        if command(['git','status','--porcelain=v1','--untracked-files=all'], cwd=source):
            raise Rejected('checkout mutated during build')
        elf = inspect_elf(binary, readelf)
        binary.chmod(0o755)
        record = {'schema_version':1, 'qualification':'UNATTESTED_SOURCE_BUILD',
                  'gate_g01':'BLOCKED', 'final_seal':'NOT_ISSUED',
                  'provider':'bclone', 'repository':BCLONE_REPO,
                  'source_commit':lock['bclone']['commit'], 'lock_sha256':filehash(lock_path),
                  'go_version':PIN_GO, 'ndk_revision':PIN_NDK, 'android_api':API_LEVEL,
                  'goos':'android', 'goarch':'arm64', 'cgo_enabled':True,
                  'go_mod_sha256':mod, 'go_sum_sha256':sums, 'module_graph_sha256':graph_hash,
                  'module_graph_members':len(graph.splitlines()),
                  'module_resolution':'readonly/isolate/sumdb',
                  'compiler_version':cc_version, 'compiler_sha256':filehash(cc),
                  'binary_name':'rclone', 'binary_sha256':filehash(binary),
                  'binary_size':binary.stat().st_size, 'elf':elf}
        (output/'provenance.json').write_bytes(canonical(record))
        (output/'SHA256SUMS').write_text(
            f"{record['binary_sha256']}  rclone\n{filehash(output/'provenance.json')}  provenance.json\n",
            encoding='ascii')
        return verify(output)
    except BaseException:
        for name in ('rclone','provenance.json','SHA256SUMS'):
            (output/name).unlink(missing_ok=True)
        raise


def verify(directory: Path) -> dict:
    if not directory.is_dir() or directory.is_symlink():
        raise Rejected('build output missing/unsafe')
    if {p.name for p in directory.iterdir()} != {'rclone','provenance.json','SHA256SUMS'}:
        raise Rejected('unexpected build inventory')
    binary, record_file, sums = (directory/x for x in ('rclone','provenance.json','SHA256SUMS'))
    if any(p.is_symlink() or not p.is_file() for p in (binary, record_file, sums)):
        raise Rejected('symlink/nonregular output')
    data = json.loads(record_file.read_text(encoding='utf-8'))
    if (data.get('schema_version'),data.get('qualification'),data.get('provider'),data.get('gate_g01'),
        data.get('final_seal'),data.get('binary_name')) != (1,'UNATTESTED_SOURCE_BUILD','bclone',
                                                          'BLOCKED','NOT_ISSUED','rclone'):
        raise Rejected('invalid provenance qualification/identity')
    if not COMMIT.fullmatch(data.get('source_commit') or '') or not SHA256.fullmatch(data.get('lock_sha256') or ''):
        raise Rejected('source/provenance pin invalid')
    if (data.get('goos'),data.get('goarch'),data.get('go_version'),data.get('ndk_revision'),data.get('android_api')) != (
        'android','arm64',PIN_GO,PIN_NDK,API_LEVEL):
        raise Rejected('provenance toolchain mismatch')
    with binary.open('rb') as fh:
        head = fh.read(64)
    if (head[:7] != b'\x7fELF\x02\x01\x01' or
        int.from_bytes(head[18:20], 'little') != 183):
        raise Rejected('output not ELF64 AArch64')
    if data.get('binary_sha256') != filehash(binary) or data.get('binary_size') != binary.stat().st_size:
        raise Rejected('binary digest or size mismatch')
    if sums.read_text(encoding='ascii') != (
        f"{filehash(binary)}  rclone\n{filehash(record_file)}  provenance.json\n"):
        raise Rejected('SHA256SUMS mismatch')
    if record_file.read_bytes() != canonical(data):
        raise Rejected('noncanonical provenance serialization')
    return data


def compare(left: Path, right: Path, left_packages: Path | None = None,
            right_packages: Path | None = None) -> dict:
    a, b = verify(left), verify(right)
    if left.resolve() == right.resolve():
        raise Rejected('two comparison builds must be separate directories')
    if a != b or (left/'rclone').read_bytes() != (right/'rclone').read_bytes():
        raise Rejected('independent bclone builds not byte-identical')
    result = {'schema_version':1, 'status':'BYTE_IDENTICAL_UNATTESTED',
              'gate_g01':'BLOCKED', 'final_seal':'NOT_ISSUED',
              'bclone_binary_sha256':a['binary_sha256'], 'source_commit':a['source_commit']}
    if (left_packages is None) != (right_packages is None):
        raise Rejected('both lanes must provide provider packages')
    if left_packages is not None:
        # Packages are fully verified by Skybind packager, not just diffed.
        for lane, packages in ((left,left_packages),(right,right_packages)):
            proof = {}
            for provider in ('newfuture','bclone'):
                archive = packages/(provider+'.zip')
                if not archive.is_file():
                    raise Rejected('missing independently built '+provider+' provider package')
                command([sys.executable,str(ROOT/'scripts/dev/runtime/skybind_runtime.py'),
                         'verify',str(archive)],timeout=60)
                with zipfile.ZipFile(archive) as z:
                    proof[provider] = {
                        'runtime':digest(z.read('system/bin/rclone')),
                        'helper':digest(z.read('system/vendor/bin/fusermount3')),
                        'meta':json.loads(z.read('runtime.provenance.json'))}
            if proof['newfuture']['helper'] != proof['bclone']['helper']:
                raise Rejected('provider FUSE helper bytes differ inside one build lane')
            if proof['bclone']['runtime'] != filehash(lane/'rclone'):
                raise Rejected('packaged bclone differs from separately verified pinned build')
            if proof['newfuture']['meta']['provider']!='newfuture' or proof['bclone']['meta']['provider']!='bclone':
                raise Rejected('provider provenance identity wrong')
            if proof['bclone']['meta']['bclone']['commit'] != a['source_commit']:
                raise Rejected('packaged bclone source commit mismatch')
        for name in ('newfuture.zip','bclone.zip'):
            x,y=left_packages/name,right_packages/name
            if filehash(x)!=filehash(y):
                raise Rejected(name+' is not byte-identical across independent clean lanes')
            result[name+'_sha256']=filehash(x)
    return result


def verify_newfuture(archive: Path, ndk: Path, lock_path: Path = DEFAULT_LOCK) -> dict:
    """Check pinned official archive BYTES + NDK ELF linkage, not upstream authenticity."""
    lock = load_lock(lock_path)
    if archive.name != lock['newfuture']['asset']:
        raise Rejected('NewFuture asset filename mismatch')
    if filehash(archive) != lock['newfuture']['archive_sha256']:
        raise Rejected('NewFuture official asset SHA256 does not match reviewed lock')
    _,readelf,_ = verify_toolchain(ndk)
    spec = importlib.util.spec_from_file_location('skybind_runtime',ROOT/'scripts/dev/runtime/skybind_runtime.py')
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    blobs = mod.extract_newfuture(archive,lock['newfuture']['archive_sha256'],lock['newfuture']['tag'])
    proof = {}
    with tempfile.TemporaryDirectory(prefix='skybind-q02-elf-') as tmp:
        for name,data in sorted(blobs.items()):
            path = Path(tmp)/name.replace('/','_')
            path.write_bytes(data)
            proof[name] = {'sha256':digest(data), 'elf':inspect_elf(path,readelf)}
    if 'system/vendor/bin/fusermount3' not in proof or 'system/bin/rclone' not in proof:
        raise Rejected('NewFuture lacks canonical runtime/FUSE helper')
    return {'schema_version':1, 'status':'PIN_MATCH_UNATTESTED',
            'archive_sha256':filehash(archive), 'files':proof,
            'static_fuse_runtime_qualified':False, 'gate_g01':'BLOCKED',
            'final_seal':'NOT_ISSUED'}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd',required=True)
    b = sub.add_parser('build')
    for key in ('source-dir','ndk','output-dir'):
        b.add_argument('--'+key,required=True,type=Path)
    b.add_argument('--lock',type=Path,default=DEFAULT_LOCK)
    v = sub.add_parser('verify');v.add_argument('directory',type=Path)
    pins = sub.add_parser('pins');pins.add_argument('--lock',type=Path,default=DEFAULT_LOCK)
    nf = sub.add_parser('verify-newfuture')
    nf.add_argument('--archive',type=Path,required=True)
    nf.add_argument('--ndk',type=Path,required=True)
    nf.add_argument('--lock',type=Path,default=DEFAULT_LOCK)
    c = sub.add_parser('compare');c.add_argument('--left',type=Path,required=True)
    c.add_argument('--right',type=Path,required=True)
    c.add_argument('--left-packages',type=Path)
    c.add_argument('--right-packages',type=Path)
    args=p.parse_args()
    try:
        if args.cmd=='build':result=build(args.source_dir,args.ndk,args.output_dir,args.lock)
        elif args.cmd=='verify':result=verify(args.directory)
        elif args.cmd=='pins':
            lock=load_lock(args.lock)
            result={'status':'PINS_PRESENT_NOT_INDEPENDENTLY_ATTESTED',
                    'bclone_commit':lock['bclone']['commit'],
                    'newfuture_sha256':lock['newfuture']['archive_sha256'],
                    'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED'}
        elif args.cmd=='verify-newfuture':result=verify_newfuture(args.archive,args.ndk,args.lock)
        else:result=compare(args.left,args.right,args.left_packages,args.right_packages)
    except (Rejected, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print('SB-Q02 BLOCKED: '+str(exc),file=sys.stderr)
        return 3
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':
    sys.exit(main())
