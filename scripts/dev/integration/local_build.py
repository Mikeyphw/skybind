#!/usr/bin/env python3
"""Build local, unqualified Skybind modules using validated Q04 CI provider bytes.

Never compiles or downloads a mutable provider. Only the Skybind daemon is
compiled locally; the release / device gates are not authorized by this tool.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/dev/integration'))
import q05_candidate as q05

RUN_ID = 38110749243  # selected immutable Q04 evidence, verified again by q05
REPOSITORY = 'Mikeyphw/skybind'
CACHE = ROOT / 'build/local-q04-evidence'
OUTPUT_BASE = ROOT / 'dist/local-candidates'
GO_VERSION = re.compile(r'^go version go(\d+\.\d+\.\d+)\s+(\S+)/(\S+)(?:\s|$)')

class LocalBuildError(RuntimeError):
    pass


def checked_command(argv: list[str], *, env: dict[str, str] | None = None, stdin: bytes | None = None,
                    capture: bool = False, cwd: Path = ROOT) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, cwd=cwd, env=env, input=stdin, check=True,
                              stdout=subprocess.PIPE if capture else None,
                              stderr=subprocess.PIPE if capture else None)
    except FileNotFoundError as exc:
        raise LocalBuildError('required tool is missing: ' + argv[0]) from exc
    except subprocess.CalledProcessError as exc:
        # Never echo captured provider stdout/stderr (remote config/secrets).
        raise LocalBuildError(f'local step failed (exit {exc.returncode}): {argv[0]}') from exc


def evidence_root(path: Path | None = None) -> Path:
    if path is not None:
        # No silent fallback if the user supplied an explicit evidence path.
        q05.evidence_inventory(path)
        return path
    if CACHE.exists() or CACHE.is_symlink():
        q05.evidence_inventory(CACHE)
        return CACHE
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    if CACHE.parent.is_symlink():
        raise LocalBuildError('evidence cache parent may not be symlinked')
    if shutil.which('gh') is None:
        raise LocalBuildError('gh CLI required for first pinned Q04 evidence download; or set SKYBIND_Q04_EVIDENCE_ROOT')
    # A failed network operation leaves no trusted cache behind.
    with tempfile.TemporaryDirectory(prefix='.skybind-evidence-', dir=CACHE.parent) as tmp:
        stage = Path(tmp)
        (stage / 'artifacts').mkdir()
        view = checked_command(['gh', 'run', 'view', str(RUN_ID), '--repo', REPOSITORY,
                                '--json', 'headSha,headBranch,status,conclusion,workflowName,url,jobs'],
                               capture=True)
        (stage / 'run.json').write_bytes(view.stdout)
        checked_command(['gh', 'run', 'download', str(RUN_ID), '--repo', REPOSITORY,
                         '-D', str(stage / 'artifacts')])
        q05.evidence_inventory(stage)
        stage.rename(CACHE)
    return CACHE


def selected_go(go_bin: str) -> tuple[str, dict[str, str]]:
    lock = q05.json_input(q05.LOCK)
    selected = lock['bclone']['go_version']
    env = os.environ.copy()
    env.update({'GOTOOLCHAIN': 'local', 'GOWORK': 'off', 'CGO_ENABLED': '0'})
    p = checked_command([go_bin, 'version'], env=env, capture=True)
    match = GO_VERSION.fullmatch(p.stdout.decode('utf-8', errors='replace').strip())
    if not match or match.group(1) != selected:
        raise LocalBuildError(f'pinned Go {selected} is required; select its executable with SKYBIND_LOCAL_GO_BIN')
    return selected, env


def verify_webui() -> None:
    assets = sorted((ROOT / 'module/webroot').glob('*.js'))
    if len(assets) < 5:
        raise LocalBuildError('missing WebUI JS modules')
    for asset in assets:
        if asset.is_symlink() or not asset.is_file():
            raise LocalBuildError('unsafe WebUI input: ' + asset.name)
        checked_command(['node', '--input-type=module', '--check'], stdin=asset.read_bytes())
    # The Q05P7 native-log contract is important for observable mount failures.
    for test in ('test_q05p7_logs_truth.mjs', 'test_q05p6_ui_truth.mjs'):
        checked_command(['node', 'tests/integration/' + test])


def verify_native(binary: Path, expected_go: str, go_bin: str, env: dict[str, str]) -> None:
    if binary.is_symlink() or not binary.is_file() or not q05.release.is_arm64_elf(binary.read_bytes()):
        raise LocalBuildError('Android/arm64 Skybind ELF missing or invalid')
    info = checked_command([go_bin, 'version', '-m', str(binary)], env=env, capture=True)
    decoded = info.stdout.decode('utf-8', errors='replace')
    required = ('go' + expected_go, 'GOOS=android', 'GOARCH=arm64', 'CGO_ENABLED=0')
    if not all(item in decoded for item in required):
        raise LocalBuildError('native Go build metadata mismatches selected Android toolchain')


def build(*, provider: str, existing_evidence: Path | None = None, go_bin: str = 'go',
          verify_only: bool = False, output_parent: Path = OUTPUT_BASE) -> dict:
    if provider not in ('newfuture', 'bclone', 'both'):
        raise LocalBuildError('invalid provider')
    q04 = evidence_root(existing_evidence)
    inputs = q05.evidence_inventory(q04)
    providers = ('newfuture', 'bclone') if provider == 'both' else (provider,)
    if verify_only:
        return {'status': 'Q04_INPUTS_VERIFIED_UNATTESTED', 'providers': list(providers),
                'run_id': inputs['selection']['run_id'], 'gate_g01': 'BLOCKED', 'final_seal': 'NOT_ISSUED'}
    version, env = selected_go(go_bin)
    verify_webui()
    # Run tests natively on the host, not under an incompatible cross-compile target.
    tests_env = {k: v for k, v in env.items() if k not in ('GOOS', 'GOARCH')}
    checked_command([go_bin, 'test', '-count=1', './...'], env=tests_env)
    if output_parent.is_symlink():
        raise LocalBuildError('output parent is a symlink')
    output_parent.mkdir(parents=True, exist_ok=True)
    # Every invocation gets a new directory; existing modules are never overwritten.
    native_parent = ROOT / 'build'
    native_parent.mkdir(parents=True, exist_ok=True)
    if native_parent.is_symlink():
        raise LocalBuildError('native build parent is symlinked')
    with tempfile.TemporaryDirectory(prefix='.skybind-native-', dir=native_parent) as tmp:
        native = Path(tmp) / 'skybind'
        build_env = dict(env, GOOS='android', GOARCH='arm64')
        checked_command([go_bin, 'build', '-trimpath', '-buildvcs=false',
                         '-ldflags=-buildid= -s -w', '-o', str(native), './cmd/skybind'], env=build_env)
        verify_native(native, version, go_bin, build_env)
        out = Path(tempfile.mkdtemp(prefix='candidate-', dir=output_parent))
        try:
            report = q05.assemble(q04, native, out, providers=providers)
            # Mandatory post-assembly verifier, not just a successful write.
            for item in report['candidates'].values():
                if q05.release.verify_release(out / item['file'])['qualification'] != 'CANDIDATE_ONLY_NOT_SEALED':
                    raise LocalBuildError('local candidate qualification mismatch')
            report['local_output'] = str(out)
            report['toolchain'] = 'go' + version
            print(json.dumps(report, sort_keys=True))
            return report
        except BaseException:
            shutil.rmtree(out)
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=['newfuture', 'bclone', 'both'], default='newfuture')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--evidence-root', type=Path, default=Path(os.environ['SKYBIND_Q04_EVIDENCE_ROOT']) if os.environ.get('SKYBIND_Q04_EVIDENCE_ROOT') else None)
    parser.add_argument('--go-bin', default=os.environ.get('SKYBIND_LOCAL_GO_BIN', 'go'))
    parser.add_argument('--output-parent', type=Path, default=OUTPUT_BASE)
    args = parser.parse_args()
    try:
        result = build(provider=args.provider, existing_evidence=args.evidence_root, go_bin=args.go_bin,
                       verify_only=args.verify_only, output_parent=args.output_parent)
        if args.verify_only:
            print(json.dumps(result, sort_keys=True))
        return 0
    except (LocalBuildError, q05.Rejected, q05.rt.Reject, q05.release.Reject, ValueError, OSError,
            json.JSONDecodeError, KeyError, TypeError) as exc:
        print('SKYBIND_LOCAL_BUILD_BLOCKED: ' + str(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main())
