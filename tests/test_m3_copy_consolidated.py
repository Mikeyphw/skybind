"""Negative source-only M3-copy, integrity, qualification and consumer boundary tests."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts/dev/android"))
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

fixture=load('scripts/dev/android/m3_copy_fixture.py','m3_copy_fixture_test')
runner=load('scripts/dev/android/m2_live_device.py','m3_copy_runner_test')
launcher=load('scripts/devtool/ci_artifacts_device.py','m3_copy_launcher_test')
consumer=load('scripts/dev/android/m3_consumer_contract_gate.py','m3_consumer_test')

RAW='''INSTRUMENTATION_STATUS: numtests=1
INSTRUMENTATION_STATUS: test=liveDisposableCopyReconnectReconcile
INSTRUMENTATION_STATUS_CODE: 1
INSTRUMENTATION_STATUS: test=liveDisposableCopyReconnectReconcile
INSTRUMENTATION_STATUS_CODE: 0
INSTRUMENTATION_RESULT: stream=OK (1 test)
INSTRUMENTATION_CODE: -1
'''

class M3Copy(unittest.TestCase):
    def test_strict_instrumentation_parser(self):
        self.assertEqual(runner.parse_m3_copy(RAW),('PASS_M3_DISPOSABLE_COPY_RECONCILED',None))
        for malformed in (RAW.replace('numtests=1','numtests=2'),
                          RAW.replace('CODE: -1','CODE: 0'),
                          RAW.replace('liveDisposableCopyReconnectReconcile','unrelated'),
                          RAW+'INSTRUMENTATION_STATUS_CODE: 0\n',RAW+'FAILURES!!!\n'):
            self.assertEqual(runner.parse_m3_copy(malformed)[0],'FAILED')
        for marker in runner.M3_COPY_BLOCKED:
            self.assertEqual(runner.parse_m3_copy(RAW+marker),('BLOCKED',marker))
        for marker in runner.M3_COPY_FAILED:
            self.assertEqual(runner.parse_m3_copy(RAW+marker),('FAILED',marker))

    def test_legacy_empty_jobs_null_is_not_missing_or_malformed(self):
        # Live installed Go daemon may legitimately serialize an empty jobs slice
        # as explicit null; a missing/malformed registry must remain BLOCKED.
        base={'schema_version':1,'revision':0}
        responses=[
            ({**base,'jobs':None}, [], False),
            ({**base,'jobs':[]}, [], False),
            ({**base,'jobs':[fixture.definition()]}, [fixture.definition()], True),
        ]
        for data, expected_jobs, expected_owned in responses:
            with self.subTest(data=data):
                with patch.object(fixture,'rpc',return_value={'registry':data,'runs':[]}):
                    reg,owned=fixture.registry()
                    self.assertEqual(reg,{'schema_version':1,'revision':0,'jobs':expected_jobs})
                    self.assertEqual(owned,expected_owned)
        for bad in (
            {**base},  # missing key must not be silently converted into []
            {**base,'jobs':{}},
            {**base,'jobs':'null'},
            {**base,'jobs':[None]},
            {'schema_version':1,'revision':-1,'jobs':[]},
            {'schema_version':1,'revision':True,'jobs':[]},
        ):
            with self.subTest(bad=bad):
                with patch.object(fixture,'rpc',return_value={'registry':bad,'runs':[]}):
                    with self.assertRaises(fixture.Blocked): fixture.registry()
        # Historical copy entries are never synthesized from a null registry.
        with patch.object(fixture,'rpc',return_value={'registry':{**base,'jobs':None},'runs':None}):
            with self.assertRaises(fixture.Blocked): fixture.registry()

    def test_disposable_pre_and_post_integrity(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'copy-fixture'
            reg={'schema_version':1,'revision':0,'jobs':[]}
            with patch.object(fixture,'ROOT',root), patch.object(fixture,'SRC',root/'source'),\
                 patch.object(fixture,'DST',root/'destination'), \
                 patch.object(fixture,'registry',return_value=(reg,False)),\
                 patch.object(fixture,'apply_registry'):
                pre=fixture.prepare(64)
                self.assertFalse(pre['destination_verified'])
                with self.assertRaises(fixture.Blocked): fixture.fixture_state('complete')
                for i in range(64):
                    name=f'copy-{i:05d}.bin'
                    shutil.copyfile(root/'source'/name,root/'destination'/name)
                post=fixture.fixture_state('complete')
                self.assertTrue(post['destination_verified'])
                self.assertEqual(pre['expected_content_sha256'],post['expected_content_sha256'])
                (root/'destination'/'copy-00023.bin').write_bytes(b'CORRUPT')
                with self.assertRaises(fixture.Blocked): fixture.fixture_state('complete')
                (root/'destination'/'copy-00023.bin').write_bytes(fixture.payload(23))
                (root/'destination'/'foreign').write_bytes(b'foreign')
                with self.assertRaises(fixture.Blocked): fixture.fixture_state('complete')
                self.assertTrue((root/'destination'/'foreign').exists())
                (root/'destination'/'foreign').unlink()
                (root/'destination'/fixture.SENTINEL).write_bytes(b'changed')
                with self.assertRaises(fixture.Blocked): fixture.fixture_state('complete')

    def test_copy_only_manual_and_path_boundary(self):
        self.assertEqual(fixture.definition()['interval_seconds'],0)
        self.assertEqual(fixture.definition()['kind'],'copy')
        self.assertNotEqual(fixture.definition()['source'],fixture.definition()['destination'])
        with self.assertRaises(fixture.Blocked): fixture.prepare(1)
        self.assertEqual(launcher.select_lanes(['m3-copy-live']),['m3-copy-live'])
        for bad in ('--test arbitrary','m3-copy-live;sync','m3-copy-live m3-cancel-live'):
            with self.assertRaises(launcher.QualificationError):launcher.select_lanes([bad])

    def test_receipt_must_have_real_hash_evidence(self):
        data={'schema':'skybind-m2-live-v1','source_sha':'a'*40,'github_run_id':7,
              'artifact_id':8,'installed_pair_verified':True,'signing_verified':True,
              'release_qualified':False,'device_qualified':False,
              'm2_l1_device_qualified':False,
              'state':'PASS_M3_DISPOSABLE_COPY_RECONCILED',
              'qualified_scope':'M3_LOCAL_DISPOSABLE_COPY_SHA256_RECONNECT_TERMINAL_ONLY',
              'm3_copy_device_qualified':True,
              'copy_preflight':dict(phase='prepared',source_verified=True,destination_verified=False,
                                    expected_content_sha256='f'*64,count=64),
              'copy_integrity':dict(phase='complete',source_verified=True,destination_verified=True,
                                    sentinel_preserved=True,expected_content_sha256='f'*64,count=64)}
        self.assertEqual(launcher.validated_lane_receipt(data,lane='m3-copy-live',run_id=7,
                                    sha='a'*40,artifact_id=8)['state'],data['state'])
        for changes in ({'m3_copy_device_qualified':False}, {'copy_integrity':None},
                        {'copy_integrity':{**data['copy_integrity'],'sentinel_preserved':False}},
                        {'copy_integrity':{**data['copy_integrity'],'expected_content_sha256':'e'*64}},
                        {'release_qualified':True}):
            with self.assertRaises(launcher.QualificationError):
                launcher.validated_lane_receipt({**data,**changes},lane='m3-copy-live',
                                               run_id=7,sha='a'*40,artifact_id=8)

    def test_evolving_chrootctl_source_does_not_repin_skybind(self):
        from json import loads, dumps
        doc=loads(consumer.MANIFEST.read_text())
        self.assertFalse(consumer.verify()['external_rclone_compatible'])
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)
            for rel,item in doc['chrootctl']['verified_sources'].items():
                f=source/rel;f.parent.mkdir(parents=True,exist_ok=True)
                f.write_text('\n'.join(item['tokens']))
            report=consumer.verify(source)
            self.assertFalse(report['source_build_required_for_consumer_update'])
            self.assertTrue(all(not x['matches_reference']
                            for x in report['source_audit'].values()))
            # A source refactor preserving the surveyed command footprint remains
            # acceptable; an optional historical audit can still demand old bytes.
            with self.assertRaises(consumer.ContractError):
                consumer.verify(source,strict_reference_sha=True)
            f=source/'internal/rcloneops/list.go'
            f.write_text('remove required command semantics')
            with self.assertRaises(consumer.ContractError): consumer.verify(source)

    def test_consumer_capability_negotiation_is_fail_closed(self):
        import json
        contract=json.loads(consumer.MANIFEST.read_text())
        abi=json.loads(consumer.ABI.read_text())
        self.assertEqual(abi['available_external_capabilities'],[])
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'consumer.json'
            good=dict(schema='skybind-rclone-consumer-request-v1',consumer='chrootctl',
                      abi_major=1,required_operations=['version','lsjson'],
                      required_capabilities=[],native_rclone_fallback=True,
                      implicit_credential_export=False)
            f.write_text(json.dumps(good))
            state=consumer.verify_declaration(f,abi,contract)
            self.assertEqual(state['status'],'PASS_DECLARATION_ONLY')
            self.assertFalse(state['runtime_qualified'])
            self.assertFalse(state['source_build_required'])
            good['required_capabilities']=['rclone.read-stream.v1']
            f.write_text(json.dumps(good))
            self.assertEqual(consumer.verify_declaration(f,abi,contract)['status'],
                             'BLOCKED_CAPABILITY_NOT_IMPLEMENTED')
            for change in ({'abi_major':2},{'implicit_credential_export':True},
                           {'required_operations':['serve restic --stdio']},
                           {'native_rclone_fallback':False}):
                candidate={**good,**change}
                f.write_text(json.dumps(candidate))
                with self.assertRaises(consumer.ContractError):
                    consumer.verify_declaration(f,abi,contract)

if __name__=='__main__':unittest.main()
