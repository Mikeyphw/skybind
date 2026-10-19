#!/usr/bin/env python3
"""Skybind hosted debug signing: persistent local key, GitHub-only APK builds.

PROVISION does not build/install APKs. It creates a keystore under the user's
private home (never the repository) and provisions three GitHub Actions secrets.
CI-PREPARE fails closed on absent/rotated keys before any Gradle invocation.
CI-FINALIZE checks the hosted manifest and records the public signer pin.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys

REPO = 'Mikeyphw/skybind'
ALIAS = 'skybind_dev'
ENV_KEYSTORE = 'SKYBIND_ANDROID_KEYSTORE_B64'
ENV_PASS = 'SKYBIND_ANDROID_KEYSTORE_PASSWORD'
ENV_PIN = 'SKYBIND_ANDROID_SIGNER_SHA256'
ENV_PATH = 'SKYBIND_ANDROID_KEYSTORE_PATH'
KEY_FILE = 'skybind-dev.p12'
HEX64 = re.compile(r'[a-f0-9]{64}\Z')
PEM = re.compile(r'-----BEGIN CERTIFICATE-----\s*([A-Za-z0-9+/=\s]+?)\s*-----END CERTIFICATE-----')
MAX_KEYSTORE = 256 * 1024


class SigningError(Exception):
    pass


def require(condition: bool, error: str):
    if not condition:
        raise SigningError(error)


def pin_from_pem(pem: str) -> str:
    matches = PEM.findall(pem)
    require(len(matches) == 1, 'EXPECTED_EXACTLY_ONE_SIGNER_CERTIFICATE')
    try:
        cert = base64.b64decode(''.join(matches[0].split()), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SigningError('BAD_SIGNER_CERTIFICATE') from exc
    require(64 <= len(cert) <= 65536 and cert.startswith(b'\x30'), 'BAD_SIGNER_DER')
    return hashlib.sha256(cert).hexdigest()


def keytool_pin(path: Path, password: str, *, runner=None) -> str:
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_KEYSTORE, 'INVALID_KEYSTORE_FILE')
    env = dict(os.environ, SKYBIND_KEYSTORE_PASSWORD=password)
    command = ['keytool', '-exportcert', '-rfc', '-alias', ALIAS, '-storetype', 'PKCS12',
               '-keystore', str(path), '-storepass:env', 'SKYBIND_KEYSTORE_PASSWORD']
    try:
        p = (runner or subprocess.run)(command, env=env, capture_output=True,
                                       text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SigningError('KEYTOOL_UNAVAILABLE_OR_TIMEOUT') from exc
    require(p.returncode == 0, 'KEYSTORE_OR_PASSWORD_REJECTED')
    return pin_from_pem(p.stdout)


def key_location() -> Path:
    return Path.home() / '.local' / 'share' / 'skybind' / 'signing'


def provision(*, root: Path | None = None, password: str | None = None,
              gh_runner=None, keytool_runner=None) -> dict:
    """Never rotate an existing key. No secret is printed, logged or committed."""
    root = root or key_location()
    require(not root.is_symlink(), 'SIGNING_DIRECTORY_SYMLINK')
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    key = root / KEY_FILE
    pinfile = root / 'signer-sha256.txt'
    if password is None:
        password = getpass.getpass('Skybind signing password (not stored): ')
        confirmation = getpass.getpass('Repeat signing password: ')
        require(password == confirmation, 'PASSWORD_CONFIRMATION_MISMATCH')
    require(len(password) >= 16 and not any(c in password for c in '\r\n\x00'),
            'SIGNING_PASSWORD_TOO_SHORT_OR_INVALID')
    require(not key.is_symlink() and not pinfile.is_symlink(), 'SIGNING_PATH_SYMLINK')
    if not key.exists():
        require(shutil.which('keytool') is not None, 'KEYTOOL_NOT_INSTALLED')
        temp = root / '.skybind-dev.new.p12'
        require(not temp.exists() and not temp.is_symlink(), 'TEMP_KEY_ALREADY_EXISTS')
        env = dict(os.environ, SKYBIND_KEYSTORE_PASSWORD=password)
        cmd = ['keytool', '-genkeypair', '-noprompt', '-alias', ALIAS,
               '-keyalg', 'RSA', '-keysize', '3072', '-validity', '3650',
               '-dname', 'CN=Skybind Development,O=Local Development',
               '-storetype', 'PKCS12', '-keystore', str(temp),
               '-storepass:env', 'SKYBIND_KEYSTORE_PASSWORD',
               '-keypass:env', 'SKYBIND_KEYSTORE_PASSWORD']
        try:
            result = (keytool_runner or subprocess.run)(cmd, env=env, capture_output=True,
                                                        text=True, timeout=90)
            require(result.returncode == 0, 'KEY_CREATION_FAILED')
            require(temp.is_file() and temp.stat().st_size > 0, 'KEYSTORE_NOT_CREATED')
            temp.chmod(0o600)
            os.replace(temp, key)
        except Exception:
            if temp.exists() and not temp.is_symlink():
                temp.unlink()
            raise
    require(not key.is_symlink() and key.stat().st_mode & 0o077 == 0,
            'KEYSTORE_ACCESS_TOO_PERMISSIVE')
    certificate = keytool_pin(key, password, runner=keytool_runner)
    if pinfile.exists():
        require(pinfile.read_text('ascii').strip() == certificate, 'SIGNING_KEY_ROTATION_REFUSED')
    else:
        with pinfile.open('x', encoding='ascii') as out:
            out.write(certificate + '\n')
        pinfile.chmod(0o600)
    upload = gh_runner or subprocess.run
    secret_values = {
        ENV_KEYSTORE: base64.b64encode(key.read_bytes()),
        ENV_PASS: password.encode(),
        ENV_PIN: certificate.encode(),
    }
    for name, value in secret_values.items():
        try:
            result = upload(['gh', 'secret', 'set', name, '--repo', REPO],
                            input=value, capture_output=True, timeout=45)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SigningError('GITHUB_SECRET_UPLOAD_FAILED_' + name) from exc
        require(result.returncode == 0, 'GITHUB_SECRET_UPLOAD_FAILED_' + name)
    return {'state': 'GITHUB_SIGNING_SECRETS_PROVISIONED_NOT_BUILT',
            'key_file': str(key), 'public_signer_sha256': certificate,
            'github_repository': REPO, 'secrets_configured': list(secret_values)}


def ci_prepare(environ: dict | None = None) -> dict:
    env = environ if environ is not None else os.environ
    require(env.get('GITHUB_ACTIONS') == 'true' and env.get('GITHUB_REPOSITORY') == REPO,
            'HOSTED_GITHUB_IDENTITY_REQUIRED')
    expected = env.get(ENV_PIN, '')
    password = env.get(ENV_PASS, '')
    encoded = env.get(ENV_KEYSTORE, '')
    require(bool(HEX64.fullmatch(expected)), 'SIGNING_CERTIFICATE_PIN_NOT_CONFIGURED')
    require(len(password) >= 16 and len(encoded) < MAX_KEYSTORE * 2,
            'SIGNING_SECRETS_MISSING_OR_OVERSIZED')
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SigningError('KEYSTORE_SECRET_INVALID_BASE64') from exc
    require(0 < len(raw) <= MAX_KEYSTORE, 'KEYSTORE_SECRET_INVALID_SIZE')
    temp = Path(env.get('RUNNER_TEMP', ''))
    require(temp.is_absolute() and temp.is_dir() and not temp.is_symlink(),
            'RUNNER_TEMP_INVALID')
    parent = temp / 'skybind-signing'
    require(not parent.exists() and not parent.is_symlink(), 'SIGNING_TEMP_ALREADY_EXISTS')
    parent.mkdir(mode=0o700)
    key = parent / 'skybind-dev.p12'
    with key.open('xb') as out:
        out.write(raw)
    key.chmod(0o600)
    actual = keytool_pin(key, password)
    require(actual == expected, 'STABLE_SIGNER_FINGERPRINT_MISMATCH')
    return {'state': 'PASS_HOSTED_STABLE_SIGNER_READY', 'public_signer_sha256': actual,
            'apk_build_executed': False}


def ci_finalize(manifest: Path, expected: str) -> dict:
    require(bool(HEX64.fullmatch(expected)), 'SIGNER_PIN_MISSING')
    require(manifest.is_file() and not manifest.is_symlink() and manifest.stat().st_size < 32768,
            'HOSTED_MANIFEST_MISSING')
    obj = json.loads(manifest.read_text())
    require(obj.get('state') == 'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED',
            'MANIFEST_NOT_BUILD_CANDIDATE')
    require(obj.get('app', {}).get('certificate_sha256') == expected and
            obj.get('test_apk', {}).get('certificate_sha256') == expected,
            'SIGNATURE_CERTIFICATE_PIN_MISMATCH')
    require(obj.get('signing') == 'ephemeral-github-debug', 'UNEXPECTED_SIGNING_FORMAT')
    obj['signing'] = 'persistent-github-debug'
    obj['signing_certificate_pin_sha256'] = expected
    obj['signing_provisioning'] = 'github-actions-secrets'
    manifest.write_text(json.dumps(obj, indent=2, sort_keys=True) + '\n')
    return {'state': 'PASS_HOSTED_STABLE_SIGNED_PAIR_NOT_DEVICE_QUALIFIED',
            'public_signer_sha256': expected}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('provision', help='Create/reuse local key and configure repo secrets; no APK build')
    sub.add_parser('ci-prepare', help='On GitHub: decode secrets and enforce exact signer pin')
    a = sub.add_parser('ci-finalize', help='On GitHub: verify and mark produced APK pair signer')
    a.add_argument('--manifest', type=Path, required=True)
    try:
        args = ap.parse_args()
        if args.command == 'provision':
            result = provision()
        elif args.command == 'ci-prepare':
            result = ci_prepare()
        else:
            require(os.environ.get('GITHUB_ACTIONS') == 'true',
                    'HOSTED_GITHUB_IDENTITY_REQUIRED')
            result = ci_finalize(args.manifest, os.environ.get(ENV_PIN, ''))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (SigningError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Never display underlying commands, environment or secret material.
        code = str(exc) if isinstance(exc, SigningError) else type(exc).__name__.upper()
        print(json.dumps({'state': 'FAILED_OR_BLOCKED', 'reason': code}, sort_keys=True))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
