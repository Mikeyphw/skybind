#!/usr/bin/env python3
"""Host-only contract tests; they do not substitute for physical device runs."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

P=Path(__file__).resolve().parents[2]/'scripts/dev/device/api_acceptance.py'
spec=importlib.util.spec_from_file_location('api_acceptance',P)
qa=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=qa
spec.loader.exec_module(qa)

class FixtureRPC:
    def __init__(self):self.calls=[]
    def raw(self,argv,timeout=40):return 0,'Skybind test (commit)'
    def call(self,op,cls='query',args=None,expect_ok=True,timeout=40):
        self.calls.append((op,cls,args,expect_ok))
        if not expect_ok:return {'ok':False}
        if op=='operation.events':
            if (args or {}).get('cursor',0)==0:return {'ok':True,'result':{'events':[{'sequence':4},{'sequence':5}],'next_cursor':5}}
            return {'ok':True,'result':{'events':[{'sequence':6}],'next_cursor':6}}
        if op=='jobs.status':return {'ok':True,'result':{'runs':[]}}
        if op=='remote.list':return {'ok':True,'result':[]}
        return {'ok':True,'result':{}}

class Unit(unittest.TestCase):
    def test_remote_base_safety(self):
        for x in ('gdrive:Skybind-QA','foo:Tests/ab_012'):
            self.assertEqual(qa.validated_base(x),x)
        for x in ('gdrive:','gdrive:/','gdrive:../x','gdrive:a/../b','gdrive:a b','gdrive:a\\b','gdrive:a//b','x:folder;rm','/etc/passwd','gdrive:a\n'):
            with self.assertRaises(ValueError):qa.validated_base(x)
    def test_counts(self):
        r=[{'status':'PASS'},{'status':'FAIL'},{'status':'BLOCKED'}]
        self.assertEqual(qa.aggregate_counts(r),{'PASS':1,'FAIL':1,'BLOCKED':1})
    def test_sanitize_job(self):
        s=qa.scrubbed_run_summary({'name':'remote:private/file','source':'secrets','state':'COMPLETED','bytes':4,'total_bytes':5,'percent':80,'reason':'token'})
        self.assertEqual(s,{'state':'COMPLETED','bytes':4,'total_bytes':5,'percent':80})
    def test_sanitize_event(self):
        got=qa.safe_event({'sequence':7,'type':'job.progress','operation_id':'untrusted','progress':{'bytes':10,'total_bytes':20,'source':'private','files_done':1},'secret':'NO'})
        self.assertEqual(got,{'sequence':7,'type':'job.progress','progress':{'bytes':10,'total_bytes':20,'files_done':1}})
    def test_jobs_status_empty_array(self):
        q=qa.Qualifier(FixtureRPC(),'readonly',None,Path(tempfile.mkdtemp()))
        self.assertEqual(q.running_jobs(),{'historical_runs_count':0,'currently_active_count':0,'numeric_contract_checked':True})
    def test_jobs_status_null_is_a_real_failure(self):
        class NullRPC(FixtureRPC):
            def call(self,op,cls='query',args=None,expect_ok=True,timeout=40):
                if op=='jobs.status':return {'ok':True,'result':{'runs':None}}
                return super().call(op,cls,args,expect_ok,timeout)
        q=qa.Qualifier(NullRPC(),'readonly',None,Path(tempfile.mkdtemp()))
        with self.assertRaisesRegex(qa.TestFail,'null or missing'):q.running_jobs()
    def test_jobs_status_numeric_contract(self):
        class RunRPC(FixtureRPC):
            def __init__(self,run):self.run=run
            def call(self,op,cls='query',args=None,expect_ok=True,timeout=40):
                if op=='jobs.status':return {'ok':True,'result':{'runs':[self.run]}}
                return super().call(op,cls,args,expect_ok,timeout)
        base={'id':'0'*32,'state':'RUNNING','bytes':4,'total_bytes':10,'percent':40,
              'files_done':1,'files_total':2,'errors':0,'retry_error':False}
        q=qa.Qualifier(RunRPC(base),'readonly',None,Path(tempfile.mkdtemp()))
        self.assertEqual(q.running_jobs()['currently_active_count'],1)
        for invalid in [dict(base,percent=200),dict(base,bytes=-1),dict(base,retry_error='yes'),
                        dict(base,percent=50,total_bytes=None)]:
            q=qa.Qualifier(RunRPC(invalid),'readonly',None,Path(tempfile.mkdtemp()))
            with self.assertRaises(qa.TestFail):q.running_jobs()

    def test_cursor_contract(self):
        r=FixtureRPC();q=qa.Qualifier(r,'readonly',None,Path(tempfile.mkdtemp()))
        result=q.events_contract()
        self.assertEqual(result['last_cursor'],5)
        self.assertEqual(r.calls[0][0],'operation.events')
    def test_negative_operations(self):
        r=FixtureRPC();q=qa.Qualifier(r,'readonly',None,Path(tempfile.mkdtemp()))
        self.assertEqual(q.negative()['unsafe_operations_rejected'],6)
        self.assertTrue(all(not x[3] for x in r.calls if x[3]))
    def test_readonly_remote(self):
        r=FixtureRPC();q=qa.Qualifier(r,'readonly','alpha:tests',Path(tempfile.mkdtemp()))
        self.assertEqual(q.readonly_remote()['listed_entries'],0)
    def test_missing_remote_blocked(self):
        q=qa.Qualifier(FixtureRPC(),'readonly',None,Path(tempfile.mkdtemp()))
        with self.assertRaises(qa.TestBlocked):q.readonly_remote()
    def test_no_disposable_without_ack(self):
        with tempfile.TemporaryDirectory() as td:
            r=FixtureRPC();q=qa.Qualifier(r,'disposable','alpha:test',Path(td))
            before=os.environ.pop('SKYBIND_QA_ACK',None)
            try:
                code=q.run_all()
                self.assertEqual(code,0)
                self.assertTrue(any(x['test']=='DISPOSABLE authorization' and x['status']=='BLOCKED' for x in q.records))
                self.assertFalse(any(x[0] in ('remote.mkdir.run','remote.transfer.start','remote.media.start') for x in r.calls if x[3]))
                doc=json.loads(next(Path(td).glob('*.json')).read_text())
                self.assertEqual(doc['counts']['FAIL'],0)
            finally:
                if before is not None:os.environ['SKYBIND_QA_ACK']=before
    def test_rpc_classes(self):
        class Captured(qa.DeviceRPC):
            def raw(self,argv,timeout=40):
                self.last=argv
                return 0,json.dumps({'ok':True,'result':{'proof':'a'}})
        r=Captured()
        r.call('remote.mkdir.preview','preview',{'endpoint':'alpha:path'})
        self.assertEqual(r.last[:3],['rpc','remote.mkdir.preview','preview'])
        with self.assertRaises(qa.TestBlocked):r.call('bad;echo','run')
    def test_wrapper_execution_contract_present(self):
        # Verifies structure independently of an installed Devtool binary.
        text=(P.parents[3]/'.devtool.toml').read_text() if (P.parents[3]/'.devtool.toml').is_file() else ''
        if text:
            self.assertIn('[wrapper.commands.api-device-readonly]',text)
            self.assertIn('[wrapper.commands.api-device-disposable]',text)

if __name__=='__main__':unittest.main()
