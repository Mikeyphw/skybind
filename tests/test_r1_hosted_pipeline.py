"""B1-QW3 offline contract/negative tests; never uses GitHub or Android devices."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'scripts' / 'dev' / 'android'))
import r1_hosted_apk_attest as witness
import r1_hosted_source


def digest(data):
    return hashlib.sha256(data).hexdigest()

class HostedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        store = self.root/'.devtool/artifacts/github-downloads'
        store.mkdir(parents=True)
        self.archive = store/'registered.zip'
        self.app = b'not-an-apk-test-bytes-1'
        self.test_apk = b'not-an-apk-test-bytes-2'
        self.cert = 'a'*64
        self.ctx = {'source_sha':'b'*40, 'run_id':789, 'artifact_id':42,
                    'workflow_id':123, 'pipeline_id':'f'*32, 'repository':witness.REPO}
        self.manifest = {
            'schema_version':1,'state':'CI_APK_BYTES_IDENTIFIED_NOT_DEVICE_QUALIFIED',
            'build_environment':'GitHub Actions ubuntu-24.04','release_qualified':False,
            'device_qualified':False,'repository':witness.REPO,'head_sha':self.ctx['source_sha'],
            'run_id':'789','run_attempt':'2','workflow':'Skybind Android APKs (hosted-only)',
            'app':{'name':witness.APP,'size_bytes':len(self.app),'sha256':digest(self.app),
                   'certificate_sha256':self.cert},
            'test_apk':{'name':witness.TEST,'size_bytes':len(self.test_apk),'sha256':digest(self.test_apk),
                        'certificate_sha256':self.cert}
        }
        self.repack()
        self.p = mock.patch.object(witness,'ROOT',self.root)
        self.p.start()
        self.addCleanup(self.p.stop)

    def repack(self):
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr(witness.APP,self.app)
            z.writestr(witness.TEST,self.test_apk)
            z.writestr(witness.MANIFEST,json.dumps(self.manifest))
        self.receipt = {'phase':'ACTIONS-04','archive_verified':True,'repository':witness.REPO,
                        'run_id':789,'artifact_id':42,'file':str(self.archive),'sha256':witness.sha(self.archive)}

    def inspect(self,archive,*,fmt,variant,member,expected_package,expected_cert):
        payload=self.app if member==witness.APP else self.test_apk
        self.assertEqual(fmt,'apk');self.assertEqual(variant,'debug')
        return {'signature_verified':True,'package':expected_package,
                'signer_sha256':expected_cert,'sha256':digest(payload),'member':member}

    def test_sdk_packages_use_single_space_delimited_input(self):
        workflow=(ROOT/'.github/workflows/skybind-android-apks.yml').read_text()
        self.assertEqual(r1_hosted_source.verify_sdk_packages(workflow),
                         r1_hosted_source.SDK_PACKAGES)
        self.assertIn("log-accepted-android-sdk-licenses: 'false'",workflow)

    def test_sdk_packages_reject_original_multiline_regression(self):
        workflow=(ROOT/'.github/workflows/skybind-android-apks.yml').read_text()
        bad=workflow.replace(
            "packages: 'platforms;android-35 build-tools;35.0.0 platform-tools'",
            "packages: |\n            platforms;android-35\n            build-tools;35.0.0\n            platform-tools")
        self.assertNotEqual(bad, workflow)
        with self.assertRaisesRegex(ValueError,'inline quoted scalar'):
            r1_hosted_source.verify_sdk_packages(bad)

    def test_sdk_packages_rejects_missing_package(self):
        workflow=(ROOT/'.github/workflows/skybind-android-apks.yml').read_text()
        bad=workflow.replace('build-tools;35.0.0 ', '')
        with self.assertRaisesRegex(ValueError,'space-delimited'):
            r1_hosted_source.verify_sdk_packages(bad)

    def test_static_source_gate(self):
        with mock.patch.object(r1_hosted_source,'ROOT',ROOT):
            self.assertEqual(r1_hosted_source.check()['status'],'PASS_B1_QW3_SOURCE_ONLY')

    def test_native_pipeline_schema(self):
        try:
            from devtool.actions_pipeline import _manifest
        except ImportError:
            self.skipTest('Devtool source module not present in test runtime')
        doc,sha = _manifest(ROOT,witness.PIPELINE.as_posix())
        self.assertEqual(doc['name'], witness.NAME)
        self.assertEqual(len(doc['nodes']),5)
        self.assertEqual(len(sha),64)

    def test_native_pipeline_rejects_remote_commit_drift(self):
        try:
            from devtool import actions_pipeline as engine
        except ImportError:
            self.skipTest('Devtool source module not present in test runtime')
        from devtool.github_actions import GitHubActionsError
        with mock.patch.object(engine,'_source',return_value='b'*40), \
             mock.patch.object(engine,'dispatch_workflow',return_value={
                 'pre_dispatch_sha':'c'*40,'workflow_id':123,'workflow_path':
                 '.github/workflows/skybind-android-apks.yml'}):
            with self.assertRaises(GitHubActionsError):
                engine.pipeline_plan(None,witness.REPO,ROOT,witness.PIPELINE.as_posix())

    def test_accepts_complete_bound_pair(self):
        got = witness.check_pair(self.ctx,self.receipt,inspection=self.inspect,attempt=2)
        self.assertTrue(got['github_run_authenticated'])
        self.assertFalse(got['release_qualified'])
        self.assertFalse(got['device_qualified'])

    def test_rejects_unverified_archive(self):
        bad=dict(self.receipt,archive_verified=False)
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,bad,inspection=self.inspect,attempt=2)

    def test_rejects_wrong_run_id(self):
        bad=dict(self.receipt,run_id=790)
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,bad,inspection=self.inspect,attempt=2)

    def test_rejects_wrong_source_or_attempt(self):
        for field,val in [('head_sha','c'*40),('run_attempt','3'),('workflow','Unrelated')]:
            original = self.manifest[field]
            self.manifest[field] = val
            self.repack()
            with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,self.receipt,inspection=self.inspect,attempt=2)
            self.manifest[field] = original

    def test_rejects_tampered_apk(self):
        self.app = b'tampered-apk'
        self.repack()
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,self.receipt,inspection=self.inspect,attempt=2)

    def test_rejects_disagreeing_signing_identity(self):
        self.manifest['test_apk']['certificate_sha256']='c'*64
        self.repack()
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,self.receipt,inspection=self.inspect,attempt=2)

    def test_rejects_failed_native_signature_inspection(self):
        def fail(*a,**kw): return {'signature_verified':False}
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,self.receipt,inspection=fail,attempt=2)

    def test_rejects_outside_devtool_store(self):
        path=self.root/'elsewhere.zip'
        path.write_bytes(self.archive.read_bytes())
        bad=dict(self.receipt,file=str(path))
        with self.assertRaises(witness.GateError):witness.check_pair(self.ctx,bad,inspection=self.inspect,attempt=2)

    def test_rejects_incomplete_pipeline_journal(self):
        state = self.root/'state'
        jdir = state/'devtool/actions/pipelines'
        jdir.mkdir(parents=True)
        obj={'schema':1,'id':'f'*32,'name':witness.NAME,
             'repo_root':str(self.root.resolve()),'repository':witness.REPO,
             'head_sha':'b'*40,'manifest_file':witness.PIPELINE.as_posix(),
             'manifest_sha256':'c'*64,'nodes':{k:{'state':'success'} for k in
               ('source','policy','build','result','archive')}}
        obj['nodes']['result']['state']='waiting'
        (jdir/('f'*32+'.json')).write_text(json.dumps(obj))
        with mock.patch.dict(os.environ,{'XDG_STATE_HOME':str(state)}), \
             mock.patch.object(witness,'source_identity',return_value='b'*40), \
             mock.patch.object(witness,'sha',return_value='c'*64):
            with self.assertRaises(witness.GateError):witness.context('f'*32)

if __name__=='__main__':unittest.main()
