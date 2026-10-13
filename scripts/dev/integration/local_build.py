#!/usr/bin/env python3
"""Build local, unqualified Skybind modules using validated Q04 CI provider bytes.

Never compiles or downloads a mutable provider. Only the Skybind daemon is
compiled locally; the release / device gates are not authorized by this tool.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import contextlib
import threading
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
# The only reviewed local compatibility exception. Never changes source.lock.json,
# Q04 provider provenance, GitHub CI compiler selection or release qualification.
LOCAL_COMPATIBILITY = {('1.27.2', '1.27.1')}

class LocalBuildError(RuntimeError):
    pass


LOG_INTERVAL_SECONDS = 15.0


def progress(message: str) -> None:
    # Flush so Devtool can show progress while the child remains active.
    print('[SKYBIND LOCAL] ' + message, flush=True)


@contextlib.contextmanager
def waiting_for(label: str):
    """Progress for CPU-heavy Python verifiers and candidate assembly."""
    done = threading.Event()

    def reporter() -> None:
        elapsed = 0.0
        while not done.wait(LOG_INTERVAL_SECONDS):
            elapsed += LOG_INTERVAL_SECONDS
            progress(f'{label}: still running ({elapsed:.0f}s)')

    worker = threading.Thread(target=reporter, daemon=True)
    worker.start()
    try:
        yield
    finally:
        done.set()
        worker.join(timeout=1)


def checked_command(argv: list[str], *, env: dict[str, str] | None = None,
                    stdin: bytes | None = None, capture: bool = False,
                    cwd: Path = ROOT, label: str | None = None,
                    show_output: bool = False) -> subprocess.CompletedProcess:
    """Run a bounded-output child with regular progress, never echo secrets.

    The installed provider and remote config may be sensitive. Captured output
    is returned to callers but not printed; other output is discarded.
    """
    if capture and show_output:
        raise LocalBuildError('capture and live output cannot be enabled together')
    desc = label or Path(argv[0]).name
    start = time.monotonic()
    try:
        with subprocess.Popen(
            argv, cwd=cwd, env=env,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture else (None if show_output else subprocess.DEVNULL),
            stderr=subprocess.PIPE if capture else (None if show_output else subprocess.DEVNULL),
        ) as process:
            first = True
            while True:
                try:
                    stdout, stderr = process.communicate(
                        input=stdin if first else None,
                        timeout=LOG_INTERVAL_SECONDS,
                    )
                    break
                except subprocess.TimeoutExpired:
                    progress(f'{desc}: still running ({time.monotonic() - start:.0f}s)')
                    first = False
            if process.returncode != 0:
                raise LocalBuildError(f'{desc} failed (exit {process.returncode}); '
                                      'raw command output withheld to protect remote secrets')
            return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)
    except FileNotFoundError as exc:
        raise LocalBuildError(f'{desc}: required executable not found: {argv[0]}') from exc


def evidence_root(path: Path | None = None) -> Path:
    if path is not None:
        # No silent fallback if the user supplied an explicit evidence path.
        progress('Q04 evidence: verifying explicitly selected source')
        with waiting_for('Q04 evidence verification'):
            q05.evidence_inventory(path)
        progress('Q04 evidence: selected source verified')
        return path
    if CACHE.exists() or CACHE.is_symlink():
        progress('Q04 evidence: validating existing local cache')
        with waiting_for('Q04 evidence verification'):
            q05.evidence_inventory(CACHE)
        progress('Q04 evidence: local cache verified')
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
        progress('Q04 evidence: fetching immutable GitHub run metadata')
        view = checked_command(['gh', 'run', 'view', str(RUN_ID), '--repo', REPOSITORY,
                                '--json', 'headSha,headBranch,status,conclusion,workflowName,url,jobs'],
                               capture=True, label='GitHub run metadata')
        (stage / 'run.json').write_bytes(view.stdout)
        progress('Q04 evidence: downloading pinned provider artifacts (first run may take time)')
        checked_command(['gh', 'run', 'download', str(RUN_ID), '--repo', REPOSITORY,
                         '-D', str(stage / 'artifacts')], label='Q04 artifact download')
        progress('Q04 evidence: verifying downloaded bytes and build receipts')
        with waiting_for('Q04 evidence verification'):
            q05.evidence_inventory(stage)
        stage.rename(CACHE)
        progress('Q04 evidence: verified cache ready')
    return CACHE


def selected_go(go_bin: str) -> tuple[str, dict[str, str]]:
    lock = q05.json_input(q05.LOCK)
    selected = lock['bclone']['go_version']
    env = os.environ.copy()
    env.update({'GOTOOLCHAIN': 'local', 'GOWORK': 'off', 'CGO_ENABLED': '0'})
    progress(f'Toolchain preflight: checking local Go against CI pin {selected} before any evidence download')
    p = checked_command([go_bin, 'version'], env=env, capture=True, label='Go version probe')
    detected = p.stdout.decode('utf-8', errors='replace').strip()
    match = GO_VERSION.fullmatch(detected)
    detected_version = match.group(1) if match else None
    if detected_version != selected and (selected, detected_version) not in LOCAL_COMPATIBILITY:
        found = ('go' + detected_version) if detected_version else 'unrecognized version output'
        raise LocalBuildError(
            f'Go {selected} (selected CI pin) or explicitly reviewed local Go 1.27.1 '
            f'(only when CI pin is 1.27.2) required, found {found} ({go_bin}); '
            'set SKYBIND_LOCAL_GO_BIN=/absolute/path/to/go for a supported compiler. '
            'No provider download or compilation was attempted')
    if detected_version != selected:
        progress(f'Toolchain preflight: Go {detected_version} accepted for LOCAL, UNQUALIFIED '
                 f'build only ({go_bin}); CI source pin remains Go {selected}')
    else:
        progress(f'Toolchain preflight: Go {selected} matches CI pin ({go_bin})')
    return detected_version, env


def verify_webui() -> None:
    assets = sorted((ROOT / 'module/webroot').glob('*.js'))
    if len(assets) < 5:
        raise LocalBuildError('missing WebUI JS modules')
    for asset in assets:
        if asset.is_symlink() or not asset.is_file():
            raise LocalBuildError('unsafe WebUI input: ' + asset.name)
        checked_command(['node', '--input-type=module', '--check'], stdin=asset.read_bytes(), label='WebUI syntax: ' + asset.name)
    # The Q05P7 native-log contract is important for observable mount failures.
    # M8: personal builds must test cross-milestone UI regression, not only legacy screens.
    for test in ('test_q05p7_logs_truth.mjs', 'test_q05p6_ui_truth.mjs', 'test_q08_mount_quick_actions.mjs'):
        checked_command(['node', 'tests/integration/' + test], label='WebUI regression: ' + test)
    checked_command(['node', '--test', *[str(p) for p in sorted((ROOT / 'tests/webui').glob('*.mjs'))]],
                    label='WebUI cross-milestone regression M0-M8')


def verify_native(binary: Path, expected_go: str, go_bin: str, env: dict[str, str]) -> None:
    if binary.is_symlink() or not binary.is_file() or not q05.release.is_arm64_elf(binary.read_bytes()):
        raise LocalBuildError('Android/arm64 Skybind ELF missing or invalid')
    info = checked_command([go_bin, 'version', '-m', str(binary)], env=env, capture=True, label='Native ELF Go metadata')
    decoded = info.stdout.decode('utf-8', errors='replace')
    required = ('go' + expected_go, 'GOOS=android', 'GOARCH=arm64', 'CGO_ENABLED=0')
    if not all(item in decoded for item in required):
        raise LocalBuildError('native Go build metadata mismatches selected Android toolchain')


def record_local_toolchain(output: Path, report: dict, actual_go: str, ci_pin: str) -> None:
    """Persist actual compiler identity beside the candidate, never a qualification claim.

    This is deliberately not a modification to Q04 receipts or the provider lock.
    The native ELF is independently checked against *actual_go* before entry.
    """
    if (report.get('final_seal'), report.get('gate_g01'),
            report.get('independent_attestation'), report.get('physical_device_tested')) != (
                'NOT_ISSUED', 'BLOCKED', False, False):
        raise LocalBuildError('local evidence cannot claim independent qualification')
    if actual_go != ci_pin and (ci_pin, actual_go) not in LOCAL_COMPATIBILITY:
        raise LocalBuildError('unreviewed local compiler cannot be recorded')
    report['build_kind'] = 'LOCAL_DEVELOPMENT_UNQUALIFIED'
    report['toolchain'] = 'go' + actual_go
    report['selected_ci_toolchain'] = 'go' + ci_pin
    report['local_go_matches_ci_pin'] = actual_go == ci_pin
    report['local_toolchain_qualification'] = 'NOT_ATTESTED_NOT_CI_EQUIVALENT'
    # SB-Q12: capture source identity at the *time of build*, not after installation.
    # This receipt is local/self-reported and is NEVER a signed release assertion.
    def git(*args: str) -> str | None:
        p = subprocess.run(['git', '-c', 'safe.directory=' + str(ROOT), '-C', str(ROOT), *args],
                           capture_output=True, text=True, timeout=10, check=False)
        return p.stdout.strip() if p.returncode == 0 else None
    commit = git('rev-parse', 'HEAD')
    tree = git('rev-parse', 'HEAD^{tree}')
    clean = git('status', '--porcelain') == ''
    if not commit or not tree:
        clean = False
    report['q12_source_build'] = {
        'schema_version': 1, 'commit': commit, 'tree': tree, 'git_clean': clean,
        'candidate_sha256': {provider: item['sha256'] for provider, item in report['candidates'].items()},
        'assurance': 'LOCAL_SELF_REPORTED_BUILD_TIME_NOT_ATTESTED',
    }
    (output / 'candidate-evidence.json').write_bytes(q05.rt.canonical(report))


def build(*, provider: str, existing_evidence: Path | None = None, go_bin: str = 'go',
          verify_only: bool = False, output_parent: Path = OUTPUT_BASE) -> dict:
    if provider not in ('newfuture', 'bclone', 'both'):
        raise LocalBuildError('invalid provider')
    providers = ('newfuture', 'bclone') if provider == 'both' else (provider,)
    progress('Starting ' + ('Q04 evidence-only verification' if verify_only else 'local candidate build')
             + ' for ' + ', '.join(providers))
    # When an explicit evidence directory is supplied, reject invalid local
    # inputs first. Never do a remote download before the Go preflight.
    q04 = evidence_root(existing_evidence) if existing_evidence is not None else None
    if verify_only:
        q04 = q04 or evidence_root()
        progress('Q04 evidence: checking canonical provider inventory')
        with waiting_for('Q04 inventory'):
            inputs = q05.evidence_inventory(q04)
        progress('Q04 evidence verified; candidate build and seal NOT attempted')
        return {'status': 'Q04_INPUTS_VERIFIED_UNATTESTED', 'providers': list(providers),
                'run_id': inputs['selection']['run_id'], 'gate_g01': 'BLOCKED', 'final_seal': 'NOT_ISSUED'}

    # Fail immediately on missing/wrong Go before the potentially long gh fetch.
    version, env = selected_go(go_bin)
    ci_pin = q05.json_input(q05.LOCK)['bclone']['go_version']
    if q04 is None:
        q04 = evidence_root()
    progress('Q04 evidence: checking canonical provider inventory')
    with waiting_for('Q04 inventory'):
        q05.evidence_inventory(q04)
    progress('WebUI: validating ES modules and browser-facing regressions')
    verify_webui()
    progress('WebUI: validation passed')
    tests_env = {k: v for k, v in env.items() if k not in ('GOOS', 'GOARCH')}
    progress('Go: running native host tests')
    checked_command([go_bin, 'test', '-count=1', './...'], env=tests_env, label='Go unit tests', show_output=True)
    progress('Go: tests passed')
    if output_parent.is_symlink():
        raise LocalBuildError('output parent is a symlink')
    output_parent.mkdir(parents=True, exist_ok=True)
    native_parent = ROOT / 'build'
    native_parent.mkdir(parents=True, exist_ok=True)
    if native_parent.is_symlink():
        raise LocalBuildError('native build parent is symlinked')
    with tempfile.TemporaryDirectory(prefix='.skybind-native-', dir=native_parent) as tmp:
        native = Path(tmp) / 'skybind'
        build_env = dict(env, GOOS='android', GOARCH='arm64')
        progress('Go: cross-compiling Skybind for Android/arm64')
        checked_command([go_bin, 'build', '-trimpath', '-buildvcs=false',
                         '-ldflags=-buildid= -s -w', '-o', str(native), './cmd/skybind'],
                        env=build_env, label='Android/arm64 compilation', show_output=True)
        progress('Go: verifying Android ELF and selected compiler metadata')
        verify_native(native, version, go_bin, build_env)
        progress('Go: native binary verified')
        out = Path(tempfile.mkdtemp(prefix='candidate-', dir=output_parent))
        try:
            progress('Packaging: assembling ' + ', '.join(providers) + ' module ZIP(s)')
            with waiting_for('Module assembly'):
                report = q05.assemble(q04, native, out, providers=providers)
            progress('Packaging: checking candidate integrity and unqualified status')
            for item in report['candidates'].values():
                with waiting_for('Candidate ZIP verification'):
                    if q05.release.verify_release(out / item['file'])['qualification'] != 'CANDIDATE_ONLY_NOT_SEALED':
                        raise LocalBuildError('local candidate qualification mismatch')
            report['local_output'] = str(out)
            record_local_toolchain(out, report, version, ci_pin)
            progress('SUCCESS: local, unqualified module(s) built with Go ' + version +
                     ' (CI pin remains Go ' + ci_pin + ') at ' + str(out))
            print(json.dumps(report, sort_keys=True), flush=True)
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
        print('SKYBIND_LOCAL_BUILD_BLOCKED: ' + str(exc), file=sys.stderr, flush=True)
        return 3


if __name__ == '__main__':
    sys.exit(main())
