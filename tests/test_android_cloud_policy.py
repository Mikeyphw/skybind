"""Source-only/cloud manifest negative tests. Does NOT build Android APKs."""
import importlib.util
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

if __name__=='__main__': unittest.main()
