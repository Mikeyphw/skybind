"""Source-only/cloud manifest negative tests. Does NOT build Android APKs."""
import importlib.util
import base64
import hashlib
import subprocess
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]

def load(relative, name):
    spec=importlib.util.spec_from_file_location(name,ROOT/relative)
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

policy=load('scripts/dev/android/verify_cloud_build_only.py','cloud_policy')
manifest=load('scripts/dev/android/apk_manifest.py','apk_manifest')

class AndroidCloudPolicy(unittest.TestCase):
    def test_only_gha_can_build(self):
        value=policy.check()
        self.assertEqual(value['apk_build_authority'],'github-actions-only')
        self.assertFalse(value['android_app_local_build_enabled'])
        self.assertFalse(value['remote_build_verified'])
    def test_android_target_does_not_allow_gradle_job(self):
        import tomllib
        data=tomllib.loads((ROOT/'.devtool.toml').read_text())
        for job in data['targets']['skybind_android_app']['jobs'].values():
            self.assertNotIn('gradle',' '.join(job['command']).lower())
    def test_create_refuses_non_ci(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            for name in ['app.apk','test.apk']: (folder/name).write_bytes(b'FAKE-APK')
            args=type('Args',(),{'app':folder/'app.apk','test_apk':folder/'test.apk','output':folder/'manifest.json'})()
            with mock.patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
                with self.assertRaisesRegex(ValueError,'GitHub Actions'):manifest.create(args)
            self.assertFalse(args.output.exists())
    def test_hash_and_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            app=root/'app.apk';test=root/'test.apk'
            app.write_bytes(b'fake-app-1');test.write_bytes(b'fake-test-1')
            env={'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW':'Skybind Android APKs','GITHUB_REPOSITORY':'Mikeyphw/skybind','GITHUB_REF':'refs/heads/feature'}
            args=type('Args',(),{'app':app,'test_apk':test,'output':root/'manifest.json'})()
            with mock.patch.dict(os.environ,env),mock.patch.object(manifest,'apk_cert',return_value='b'*64):
                self.assertEqual(manifest.create(args)['state'],'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED')
                verifier=type('Verify',(),{'manifest':args.output,'app':app,'test_apk':test,'expected_head_sha':'a'*40,'expected_run_id':'123'})()
                self.assertEqual(manifest.verify(verifier)['state'],'PASS_LOCAL_HASH_AND_CERT')
                verifier.expected_head_sha='c'*40
                with self.assertRaisesRegex(ValueError,'source SHA'):manifest.verify(verifier)
                verifier.expected_head_sha='a'*40
                test.write_bytes(b'changed-test')
                with self.assertRaisesRegex(ValueError,'APK bytes'):manifest.verify(verifier)
    def test_local_hash_only_never_claims_cert_or_remote_success(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);app=root/'app.apk';test=root/'test.apk'
            app.write_bytes(b'a');test.write_bytes(b'b')
            env={'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW':'Skybind Android APKs','GITHUB_REPOSITORY':'Mikeyphw/skybind','GITHUB_REF':'refs/heads/feature'}
            args=type('Args',(),{'app':app,'test_apk':test,'output':root/'manifest.json'})()
            with mock.patch.dict(os.environ,env),mock.patch.object(manifest,'apk_cert',return_value='b'*64):manifest.create(args)
            verifier=type('Verify',(),{'manifest':args.output,'app':app,'test_apk':test,'expected_head_sha':None,'expected_run_id':None})()
            with mock.patch.object(manifest,'apk_cert',return_value=None):
                v=manifest.verify(verifier)
            self.assertEqual(v['state'],'PASS_LOCAL_HASH_ONLY_CERT_UNCHECKED')
            self.assertFalse(v['github_run_authenticated'])

class HostedCertificateEvidence(unittest.TestCase):
    """Source-only unit tests. They never create or sign Android APKs."""
    # The DER bytes are synthetic: the mock attests to apksigner's verification
    # step and the parser is tested solely against its byte-encoding contract.
    CERT = b'\x30' + b'\x82' * 79
    CERT2 = b'\x30' + b'\x83' * 79

    @classmethod
    def pem(cls, cert=None):
        cert = cls.CERT if cert is None else cert
        return ('-----BEGIN CERTIFICATE-----\n' +
                base64.b64encode(cert).decode('ascii') +
                '\n-----END CERTIFICATE-----\n')

    def test_parse_version_range_signer_label(self):
        output = ('Signer (minSdkVersion=24, maxSdkVersion=35) certificate SHA-256 digest: ignored\n'
                  + self.pem())
        self.assertEqual(manifest.certificate_digest_from_pem_output(output),
                         hashlib.sha256(self.CERT).hexdigest())

    def test_parse_numbered_signer_label(self):
        output = 'Signer #1 certificate DN: Android Debug\n' + self.pem()
        self.assertEqual(manifest.certificate_digest_from_pem_output(output),
                         hashlib.sha256(self.CERT).hexdigest())

    def test_missing_pem_fails_closed_even_if_printed_digest_exists(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            manifest.certificate_digest_from_pem_output(
                'Signer #1 certificate SHA-256 digest: ' + 'a' * 64)

    def test_multiple_signer_pem_blocks_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            manifest.certificate_digest_from_pem_output(self.pem() + self.pem(self.CERT2))

    def test_corrupted_or_truncated_pem_fails_closed(self):
        with self.assertRaises(ValueError):
            manifest.certificate_digest_from_pem_output(
                '-----BEGIN CERTIFICATE-----\na!=b\n-----END CERTIFICATE-----')
        with self.assertRaisesRegex(ValueError, 'DER is malformed'):
            manifest.certificate_digest_from_pem_output(self.pem(b'\x30\x00'))

    def test_apksigner_must_actually_verify_signature(self):
        with mock.patch.object(manifest.shutil, 'which', return_value='/sdk/apksigner'):
            with mock.patch.object(manifest.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, self.pem(), 'ERROR')):
                with self.assertRaisesRegex(ValueError, 'signature verification failed'):
                    manifest.apk_cert(Path('app.apk'))

    def test_apksigner_uses_verified_certificate_pem(self):
        result = subprocess.CompletedProcess([], 0, 'Signer (minSdkVersion=28) certificate DN: debug\n' + self.pem(), '')
        with mock.patch.object(manifest.shutil, 'which', return_value='/sdk/apksigner'):
            with mock.patch.object(manifest.subprocess, 'run', return_value=result) as runner:
                digest = manifest.apk_cert(Path('app.apk'))
        self.assertEqual(digest, hashlib.sha256(self.CERT).hexdigest())
        self.assertEqual(runner.call_args.args[0],
                         ['/sdk/apksigner', 'verify', '--print-certs-pem', 'app.apk'])

    def test_distinct_app_and_instrumentation_signers_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / 'app.apk'
            test = Path(td) / 'test.apk'
            app.write_bytes(b'app');test.write_bytes(b'test')
            args = type('Args',(),{'app':app,'test_apk':test,'output':Path(td)/'out.json'})()
            env = {'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123',
                   'GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW':'Skybind Android APKs (hosted-only)',
                   'GITHUB_REPOSITORY':'Mikeyphw/skybind','GITHUB_REF':'refs/heads/main'}
            with mock.patch.dict(os.environ,env):
                with mock.patch.object(manifest,'apk_cert',side_effect=['a'*64,'b'*64]):
                    with self.assertRaisesRegex(ValueError,'signing identities differ'):
                        manifest.create(args)
            self.assertFalse(args.output.exists())

    def test_absent_apksigner_cannot_produce_hosted_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            app = Path(td) / 'app.apk'
            test = Path(td) / 'test.apk'
            app.write_bytes(b'app');test.write_bytes(b'test')
            args = type('Args',(),{'app':app,'test_apk':test,'output':Path(td)/'out.json'})()
            env = {'GITHUB_ACTIONS':'true','GITHUB_SHA':'a'*40,'GITHUB_RUN_ID':'123',
                   'GITHUB_RUN_ATTEMPT':'1','GITHUB_WORKFLOW':'Skybind Android APKs (hosted-only)',
                   'GITHUB_REPOSITORY':'Mikeyphw/skybind','GITHUB_REF':'refs/heads/main',
                   'ANDROID_HOME':'','ANDROID_SDK_ROOT':''}
            with mock.patch.dict(os.environ,env), mock.patch.object(manifest.shutil,'which',return_value=None):
                with self.assertRaisesRegex(ValueError,'certificate verification required'):
                    manifest.create(args)
            self.assertFalse(args.output.exists())

if __name__=='__main__': unittest.main()

