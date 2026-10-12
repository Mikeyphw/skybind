#!/usr/bin/env python3
"""SB-Q10: Build/install a *debug* Android UID probe; never an evidence attestor.

The probe is the existing Q09/SB-C06 org.skybind.probe Activity. It is only
installed here. Execution, write consent and evidence are owned by skybind-q09.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
import zipfile

REPO = Path(__file__).resolve().parents[2]
PROBE = REPO / 'tests/device/probe-app'
OUT = REPO / 'build/app-probe'
PACKAGE = 'org.skybind.probe'
APK_NAME = 'skybind-app-probe-debug.apk'
SOURCE_DIGESTS = {
    'tests/device/probe-app/settings.gradle': 'e3a0e3e63003b302d8b7c94663321e69247fc72ee9dfa40350c0a72a0dfa950d',
    'tests/device/probe-app/build.gradle': '8c9f2652d054b80fbc19998e3b1c7b89ad04d98213ee23776129bae2b0508b74',
    'tests/device/probe-app/app/build.gradle': 'dbaba0a84e8aeccdfc70159d192fa2c320dfba3b00c549031ba4be807c950509',
    'tests/device/probe-app/app/src/main/AndroidManifest.xml': '556a01a3765b7d0786fd137ec2c215e5f8f3dda61580e3bbd0fee548ed1020b0',
    'tests/device/probe-app/app/src/main/java/org/skybind/probe/ProbeActivity.java': '836e515c5fcc55798c3f84a6fc242e114b42ef0f749871c151bfe2ccfbf2750b',
}

class ProbeError(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def msg(message: str) -> None:
    print('[SB-Q10] ' + message, flush=True)


def source_check() -> None:
    for relative, expected in SOURCE_DIGESTS.items():
        path = REPO / relative
        if path.is_symlink() or not path.is_file() or sha(path.read_bytes()) != expected:
            raise ProbeError('probe source missing or changed: ' + relative)
    policy = REPO / 'scripts/dev/runtime/source.selection.json'
    if policy.is_symlink() or not policy.is_file():
        raise ProbeError('Skybind release policy is missing')
    obj = json.loads(policy.read_text())
    if obj.get('gate_g01') != 'BLOCKED' or obj.get('final_seal') != 'NOT_ISSUED' or obj.get('independent_attestation') is not False:
        raise ProbeError('unexpected release state; refuse implicit gate promotion')


def checked_apk(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_size < 1000 or path.stat().st_size > 50 * 1024 * 1024:
        raise ProbeError('invalid, missing, oversized, or symlinked debug APK')
    try:
        with zipfile.ZipFile(path) as archive:
            files = archive.namelist()
            if len(files) > 5000 or len(files) != len(set(files)):
                raise ProbeError('duplicate or excessive APK members')
            if 'AndroidManifest.xml' not in files or 'classes.dex' not in files:
                raise ProbeError('APK missing manifest or classes.dex')
            if archive.testzip() is not None:
                raise ProbeError('APK ZIP integrity failure')
    except zipfile.BadZipFile as exc:
        raise ProbeError('malformed APK') from exc
    return sha(path.read_bytes())


def helper_command(helper: Path) -> list[str]:
    # Provision only missing SDK/build tools through Devtool's supported bootstrap.
    # Bootstrap network scope is local to this debug probe; no release signer.
    return [sys.executable, str(helper), str(PROBE), '--no-chroot',
            '--task', ':app:assembleDebug', '--aapt2-provider', 'auto',
            '--android-platform', '35', '--build-tools', 'auto',
            '--arm-build-tools-provider', 'auto', '--ndk-version', 'auto',
            '--cmake-version', 'auto', '--space-min-free-mb', '2048',
            '--space-target-free-mb', '3072', '--managed-gradle-retention', '2',
            '--toolchain-downloads', 'missing', '--bootstrap-network', 'allow',
            '--max-workers', '2', '--system-deps', 'auto',
            '--daemon-idle-timeout-ms', '900000', '--gradle-jvm-heap-mb', '768',
            '--build-cache', '--output-dir', str(OUT / 'devtool-build'),
            '--artifact-collision', 'unique']


def build() -> Path:
    source_check()
    if not os.environ.get('PREFIX', '').startswith('/data/data/com.termux/files/usr'):
        raise ProbeError('build must run in Termux (not root/chroot); Gradle ARM tools are device-specific')
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    apk = OUT / APK_NAME
    receipt = OUT / 'build-receipt.json'
    # A failed build must never leave an installable "last successful" receipt.
    for path in (apk, receipt):
        if path.is_symlink():
            raise ProbeError('refusing symlinked output')
        if path.exists():
            path.unlink()
    helper = Path.home() / '.local/share/devtool/runtime/android/build-apk'
    if helper.is_file() and not helper.is_symlink():
        cmd = helper_command(helper)
        msg('Building debug app using Devtool managed Android SDK 35 (missing toolchains may be downloaded).')
        result = subprocess.run(cmd, cwd=REPO, check=False)
    else:
        raise ProbeError('Devtool managed Android build helper is missing: '+str(helper))
    if result.returncode:
        raise ProbeError(f'Android debug build failed (exit {result.returncode}); inspect Devtool Android bootstrap diagnostics for SDK 35/Gradle dependencies')
    # AGP emits the canonical APK here. The Devtool build helper may alternatively
    # export exactly one APK to the explicitly dedicated output directory.
    native = PROBE / 'app/build/outputs/apk/debug/app-debug.apk'
    if native.is_file() and not native.is_symlink():
        selected = native
    else:
        options = [p for p in (OUT / 'devtool-build').rglob('*.apk') if p.is_file() and not p.is_symlink()]
        if len(options) != 1:
            raise ProbeError('cannot identify a unique newly-built debug APK')
        selected = options[0]
    checked_apk(selected)
    shutil.copyfile(selected, apk)
    digest = checked_apk(apk)
    # No signing material or private source data in the receipt.
    record = {'schema_version': 1, 'type': 'SKYBIND_Q10_DEBUG_APP_BUILD',
              'package': PACKAGE, 'variant': 'debug', 'apk_name': APK_NAME,
              'apk_sha256': digest, 'app_source_sha256': dict(SOURCE_DIGESTS),
              'created_at_unix': int(time.time()),
              'qualification': 'BUILD_ONLY_UNATTESTED', 'release_seal': 'NOT_ISSUED'}
    with receipt.open('x') as handle:
        json.dump(record, handle, sort_keys=True, indent=2)
        handle.write('\n')
    os.chmod(receipt, 0o600)
    msg('Debug APK: ' + str(apk))
    msg('SHA-256: ' + digest)
    return apk


def install_receipt() -> tuple[Path, str]:
    source_check()
    apk = OUT / APK_NAME
    receipt_path = OUT / 'build-receipt.json'
    if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 20000:
        raise ProbeError('missing or unsafe build receipt; build first')
    record = json.loads(receipt_path.read_text())
    digest = checked_apk(apk)
    if (record.get('schema_version') != 1 or record.get('type') != 'SKYBIND_Q10_DEBUG_APP_BUILD'
        or record.get('package') != PACKAGE or record.get('variant') != 'debug'
        or record.get('apk_name') != APK_NAME or record.get('apk_sha256') != digest
        or record.get('app_source_sha256') != SOURCE_DIGESTS
        or record.get('release_seal') != 'NOT_ISSUED'):
        raise ProbeError('APK hash/source mismatch; rebuild before installing')
    return apk, digest


def installation_script(apk: Path, digest: str, token: str) -> str:
    if not re.fullmatch('[0-9a-f]{24}', token) or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ProbeError('invalid installation identity')
    dest = f'/data/local/tmp/skybind-q10-probe-{token}.apk'
    q = shlex.quote
    # Only staged probe APK is touched; no remounts, broad permissions or app-data wiping.
    return ("set -eu\n"
            "umask 077\n"
            f"dest={q(dest)}\n"
            "[ ! -e \"$dest\" ] || exit 31\n"
            "trap 'rm -f \"$dest\"' EXIT HUP INT TERM\n"
            f"/system/bin/cp {q(str(apk))} \"$dest\"\n"
            "[ -f \"$dest\" ] && [ ! -L \"$dest\" ]\n"
            "[ ! -x /system/bin/restorecon ] || /system/bin/restorecon \"$dest\"\n"
            "/system/bin/chmod 0644 \"$dest\"\n"
            "staged=$(/system/bin/toybox sha256sum \"$dest\")\n"
            f"[ \"${{staged%% *}}\" = {q(digest)} ] || exit 32\n"
            "/system/bin/pm install -r \"$dest\"\n"
            f"/system/bin/pm list packages -U {PACKAGE}\n")


def install() -> None:
    if not os.path.isdir('/system') or not os.path.isdir('/data'):
        raise ProbeError('install must run on an Android device')
    apk, digest = install_receipt()
    root = subprocess.run(['su', '-c', '/system/bin/id -u'], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=15, check=False)
    if root.returncode or root.stdout.strip() != '0':
        raise ProbeError('root permission unavailable; allow Termux su request')
    cmd = installation_script(apk, digest, secrets.token_hex(12))
    msg('Installing verified DEBUG probe APK; Skybind module and mount remain untouched.')
    proc = subprocess.run(['su', '-c', cmd], text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=180, check=False)
    if proc.returncode or not re.search(r'(?m)^Success\s*$', proc.stdout):
        raise ProbeError('pm install failed (exit '+str(proc.returncode)+'): '+(proc.stderr or proc.stdout)[-500:])
    match = re.search(r'^package:'+re.escape(PACKAGE)+r'\s+uid:(\d+)\s*$', proc.stdout, flags=re.M)
    if not match or int(match.group(1)) < 10000:
        raise ProbeError('package installation did not establish an unprivileged app UID')
    msg(f'Installed {PACKAGE} as ordinary app UID {match.group(1)}.')
    msg('Installation only: run ~/.local/bin/skybind-q09 app-probe --yes for actual consent-based read/write evidence.')
    msg('Release seal remains NOT_ISSUED.')


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ('build', 'install', 'build-install'):
        print('Usage: skybind_app_probe.py build|install|build-install', file=sys.stderr)
        return 2
    try:
        if argv[0] in ('build', 'build-install'):
            build()
        if argv[0] in ('install', 'build-install'):
            install()
        return 0
    except (ProbeError, OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print('[SB-Q10] BLOCKED: ' + str(exc), file=sys.stderr)
        return 3


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
