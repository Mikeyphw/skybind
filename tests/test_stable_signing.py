"""Source-only stable signing negative gates; NEVER builds or signs an APK."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'scripts/dev/android/stable_signing.py'
spec = importlib.util.spec_from_file_location('skybind_stable_signing', MODULE)
if not MODULE.exists():
    raise RuntimeError('stable signing implementation missing')
signing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(signing)


class StableSigningPolicy(unittest.TestCase):
    def test_source_wires_only_hosted_build_and_secret_signer(self):
        workflow = (ROOT / '.github/workflows/skybind-android-apks.yml').read_text()
        gradle = (ROOT / 'android-app/app/build.gradle.kts').read_text()
        self.assertIn('scripts/dev/android/stable_signing.py ci-prepare', workflow)
        self.assertIn('scripts/dev/android/stable_signing.py ci-finalize', workflow)
        self.assertLess(workflow.index('ci-prepare'), workflow.index('gradle --no-daemon'))
        self.assertLess(workflow.index('ci-finalize'), workflow.index('upload-artifact@'))
        self.assertIn('secrets.SKYBIND_ANDROID_KEYSTORE_B64', workflow)
        self.assertIn('secrets.SKYBIND_ANDROID_SIGNER_SHA256', workflow)
        self.assertIn('secrets.SKYBIND_ANDROID_KEYSTORE_PASSWORD', workflow)
        self.assertIn('if: always()', workflow)
        self.assertIn("github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'", workflow)
        self.assertIn('create("skybindPersistentDebug")', gradle)
        self.assertIn('signingConfig = signingConfigs.getByName("skybindPersistentDebug")', gradle)
        self.assertIn('keyAlias = "skybind_dev"', gradle)
        self.assertIn('Skybind hosted persistent signing credentials are required', gradle)
        self.assertNotIn('local.properties', gradle)
        self.assertNotIn('gradle assemble', str(ROOT / 'scripts/dev/android/stable_signing.py'))

    def test_fingerprint_is_certificate_der_sha256(self):
        cert = b'\x30' + b'\x82' * 79
        pem = '-----BEGIN CERTIFICATE-----\n' + base64.b64encode(cert).decode() + '\n-----END CERTIFICATE-----'
        self.assertEqual(signing.pin_from_pem(pem), hashlib.sha256(cert).hexdigest())
        with self.assertRaises(signing.SigningError):
            signing.pin_from_pem(pem + '\n' + pem)
        with self.assertRaises(signing.SigningError):
            signing.pin_from_pem('-----BEGIN CERTIFICATE-----\nInvalid!\n-----END CERTIFICATE-----')

    def test_ci_requires_github_and_pin(self):
        with self.assertRaisesRegex(signing.SigningError, 'HOSTED_GITHUB_IDENTITY_REQUIRED'):
            signing.ci_prepare({})
        with tempfile.TemporaryDirectory() as d:
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': signing.REPO,
                   'RUNNER_TEMP': d}
            with self.assertRaisesRegex(signing.SigningError, 'PIN_NOT_CONFIGURED'):
                signing.ci_prepare(env)

    def test_ci_rejects_invalid_secret_bytes_without_writing_key(self):
        with tempfile.TemporaryDirectory() as d:
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': signing.REPO,
                   'RUNNER_TEMP': d, signing.ENV_PIN: 'a' * 64,
                   signing.ENV_PASS: 'very-long-development-password',
                   signing.ENV_KEYSTORE: '@@invalid@@'}
            with self.assertRaisesRegex(signing.SigningError, 'INVALID_BASE64'):
                signing.ci_prepare(env)
            self.assertFalse((Path(d) / 'skybind-signing').exists())

    def test_ci_fails_on_wrong_signer_and_does_not_claim_build(self):
        with tempfile.TemporaryDirectory() as d:
            raw = b'nonsecret-ephemeral-fixture'
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': signing.REPO,
                   'RUNNER_TEMP': d, signing.ENV_PIN: 'a' * 64,
                   signing.ENV_PASS: 'very-long-development-password',
                   signing.ENV_KEYSTORE: base64.b64encode(raw).decode()}
            with mock.patch.object(signing, 'keytool_pin', return_value='b' * 64):
                with self.assertRaisesRegex(signing.SigningError, 'FINGERPRINT_MISMATCH'):
                    signing.ci_prepare(env)
            self.assertEqual((Path(d) / 'skybind-signing/skybind-dev.p12').read_bytes(), raw)

    def test_ci_prepare_rejects_reuse_of_old_key_location(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'skybind-signing').mkdir()
            env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': signing.REPO,
                   'RUNNER_TEMP': d, signing.ENV_PIN: 'a' * 64,
                   signing.ENV_PASS: 'very-long-development-password',
                   signing.ENV_KEYSTORE: base64.b64encode(b'fake').decode()}
            with self.assertRaisesRegex(signing.SigningError, 'SIGNING_TEMP_ALREADY_EXISTS'):
                signing.ci_prepare(env)

    def fixture_manifest(self, path, app='a'*64, test='a'*64):
        payload = {'state': 'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED',
                   'signing': 'ephemeral-github-debug',
                   'app': {'certificate_sha256': app},
                   'test_apk': {'certificate_sha256': test}}
        path.write_text(json.dumps(payload))

    def test_ci_finalizes_exact_pinned_pair_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'manifest.json'
            self.fixture_manifest(p)
            got = signing.ci_finalize(p, 'a'*64)
            self.assertEqual(got['state'], 'PASS_HOSTED_STABLE_SIGNED_PAIR_NOT_DEVICE_QUALIFIED')
            out = json.loads(p.read_text())
            self.assertEqual(out['signing'], 'persistent-github-debug')
            self.assertEqual(out['signing_certificate_pin_sha256'], 'a'*64)
            self.assertNotIn('password', out)
            self.assertNotIn('keystore', out)

    def test_ci_refuses_rotated_certificate(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'manifest.json'
            self.fixture_manifest(p, test='b'*64)
            original = p.read_bytes()
            with self.assertRaisesRegex(signing.SigningError, 'CERTIFICATE_PIN_MISMATCH'):
                signing.ci_finalize(p, 'a'*64)
            self.assertEqual(original, p.read_bytes())

    def test_provision_never_uses_missing_or_changed_key_silently(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            key=root / signing.KEY_FILE
            key.write_bytes(b'fixture-keystore')
            key.chmod(0o600)
            (root / 'signer-sha256.txt').write_text('a'*64+'\n')
            with mock.patch.object(signing, 'keytool_pin', return_value='b'*64):
                with self.assertRaisesRegex(signing.SigningError, 'SIGNING_KEY_ROTATION_REFUSED'):
                    signing.provision(root=root, password='fixture-password-long')

    def test_provision_uploads_only_private_stdin_secrets(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            key=root/signing.KEY_FILE
            key.write_bytes(b'fixture-keystore')
            key.chmod(0o600)
            calls=[]
            def gh(command, **kwargs):
                calls.append((command, kwargs))
                return mock.Mock(returncode=0)
            with mock.patch.object(signing, 'keytool_pin', return_value='c'*64):
                result=signing.provision(root=root, password='fixture-password-long', gh_runner=gh)
            self.assertEqual(result['public_signer_sha256'], 'c'*64)
            self.assertEqual(len(calls), 3)
            for command, kwargs in calls:
                self.assertEqual(command[:3], ['gh','secret','set'])
                self.assertEqual(command[-2:], ['--repo', signing.REPO])
                self.assertIsInstance(kwargs['input'], bytes)
                self.assertNotIn('fixture-password-long', ' '.join(command))

if __name__ == '__main__':
    unittest.main()
