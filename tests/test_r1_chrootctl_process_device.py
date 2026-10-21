import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
import json
import hashlib
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'scripts/dev/android/r1_chrootctl_process_device.py'
spec=importlib.util.spec_from_file_location('r1_chroot_live',P)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def machine(state='BLOCKED',reason='CHROOTCTL_LIVE_SEAL_OR_SELINUX_NOT_ATTESTED',attested=False):
    return json.dumps({'schema':'skybind-r1-live-chrootctl-process-v1','state':state,'reason':reason,
      'chrootctl_process_attested':attested,'grants_issued':False,'external_provider_qualified':False,'release_qualified':False})

class LiveSourceTests(unittest.TestCase):
    def test_complete_three_case_acceptance(self):
        self.assertEqual(m.check_receipt(machine('PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY',None,True),0,'positive')['process_attested'],True)
        self.assertEqual(m.check_receipt(machine(),2,'wrong_seal')['state'],'BLOCKED')
        self.assertEqual(m.check_receipt(machine(),2,'wrong_context')['state'],'BLOCKED')
    def test_denies_forged_receipt_and_wrong_status(self):
        for code,s in [(0,machine()),(2,machine('PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY',None,True)),
                       (0,machine().replace('"grants_issued": false','"grants_issued": true')),
                       (0,machine()+'\n'+machine()),(0,'broken'),
                       (0,machine().replace('"schema": "skybind-r1-live-chrootctl-process-v1"','"schema": "bad"'))]:
            with self.assertRaises(m.Blocked):m.check_receipt(s,code,'positive')
        for code,s in [(0,machine()),(2,machine('PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY',None,True)),
                       (2,machine(reason='OTHER')), (2,machine().replace('"release_qualified": false','"release_qualified": true'))]:
            with self.assertRaises(m.Blocked):m.check_receipt(s,code,'wrong_seal')
    def test_artifact_source_pin_and_sha(self):
        sha='a'*40
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            (base/'source.json').write_text(json.dumps({'schema':'skybind-r1-consumer-diagnostic-artifact-v1','source_sha':sha,'external_provider_qualified':False,'release_qualified':False}))
            sums=[]
            for filename in m.BINARIES:
                data=b'A'*5000+filename.encode()
                (base/filename).write_bytes(data)
                sums.append(hashlib.sha256(data).hexdigest()+'  '+filename)
            (base/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n')
            def fake(args,**kwargs):
                if args[:2]==['gh','api']:
                    return SimpleNamespace(returncode=0,stdout=json.dumps({'head_sha':sha,'conclusion':'success','name':m.WORKFLOW,'event':'workflow_dispatch'}))
                return SimpleNamespace(returncode=0,stdout='')
            with patch.object(m,'command',side_effect=fake):
                self.assertEqual(m.load_artifact(123,sha,base).name,m.BINARIES[1])
                (base/m.BINARIES[1]).write_bytes(b'changed')
                with self.assertRaises(m.Blocked):m.load_artifact(123,sha,base)
            with patch.object(m,'command',return_value=SimpleNamespace(returncode=0,stdout='{}')):
                with self.assertRaises(m.Blocked):m.load_artifact(123,sha,base)
    def test_full_live_three_case_receipt_requires_all_denials(self):
        with tempfile.TemporaryDirectory() as td:
            args=SimpleNamespace(run_id=123,expected_sha='a'*40,live=True,operator_approve=True,pid=900,
                                 approved_manifest_sha256='b'*64,approved_selinux='u:r:su:s0',output_root=Path(td))
            receipts={
              'positive':{'state':'PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY','reason':None,'process_attested':True},
              'wrong_seal':{'state':'BLOCKED','reason':'CHROOTCTL_LIVE_SEAL_OR_SELINUX_NOT_ATTESTED','process_attested':False},
              'wrong_context':{'state':'BLOCKED','reason':'CHROOTCTL_LIVE_SEAL_OR_SELINUX_NOT_ATTESTED','process_attested':False},
            }
            with patch.object(m,'expected_source',return_value='a'*40),patch.object(m,'load_artifact',return_value=Path(td)/'unused'),patch.object(m,'module_case',side_effect=lambda binary,pid,seal,label,name:receipts[name]):
                self.assertEqual(m.run(args),0)
                report=json.loads(next(Path(td).glob('*.json')).read_text())
                self.assertTrue(report['chrootctl_process_attested'])
                self.assertFalse(report['android_selinux_consumer_socket_qualified'])
                self.assertEqual(len(report['cases']),3)
        with tempfile.TemporaryDirectory() as td:
            args.output_root=Path(td)
            receipts['wrong_seal']={'state':'PASS','reason':None,'process_attested':True}
            with patch.object(m,'expected_source',return_value='a'*40),patch.object(m,'load_artifact',return_value=Path(td)/'unused'),patch.object(m,'module_case',side_effect=lambda binary,pid,seal,label,name: (m.check_receipt(machine(),0,'wrong_seal') if name=='wrong_seal' else receipts[name])):
                self.assertEqual(m.run(args),2)
                report=json.loads(next(Path(td).glob('*.json')).read_text())
                self.assertFalse(report['chrootctl_process_attested'])
                self.assertEqual(report['state'],'BLOCKED')
    def test_live_requires_explicit_approval_before_download(self):
        with tempfile.TemporaryDirectory() as td:
            args=SimpleNamespace(run_id=123,expected_sha='a'*40,live=True,operator_approve=False,pid=100,
                                 approved_manifest_sha256='b'*64,approved_selinux='u:r:su:s0',output_root=Path(td))
            with patch.object(m,'expected_source',return_value='a'*40),patch.object(m,'load_artifact') as dl:
                self.assertEqual(m.run(args),2)
                dl.assert_not_called()
    def test_no_live_consumer_or_release_claims(self):
        with tempfile.TemporaryDirectory() as td:
            args=SimpleNamespace(run_id=123,expected_sha='a'*40,live=False,operator_approve=False,pid=None,
                                 approved_manifest_sha256='',approved_selinux='',output_root=Path(td))
            with patch.object(m,'expected_source',return_value='a'*40),patch.object(m,'load_artifact',return_value=Path(td)/'unused'):
                self.assertEqual(m.run(args),0)
                report=json.loads(next(Path(td).glob('*.json')).read_text())
                self.assertEqual(report['state'],'PASS_R1_DIAGNOSTIC_ARTIFACT_PREFLIGHT_ONLY')
                self.assertFalse(report['chrootctl_process_attested'])
                self.assertFalse(report['grants_issued'])
                self.assertFalse(report['external_provider_qualified'])
                self.assertFalse(report['android_selinux_consumer_socket_qualified'])

if __name__=='__main__':unittest.main()
