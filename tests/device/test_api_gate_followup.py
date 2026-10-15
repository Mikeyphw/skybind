#!/usr/bin/env python3
"""Host tests for follow-up Android gates. Cannot certify physical WebView/boot."""
import importlib.util
import json
import pathlib
import sys
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
D=ROOT/'scripts/dev/device'
sys.path.insert(0,str(D))
def load(name):
    spec=importlib.util.spec_from_file_location(name,D/(name+'.py'))
    obj=importlib.util.module_from_spec(spec);sys.modules[name]=obj;spec.loader.exec_module(obj)
    return obj
boot=load('boot_journal_gate')
web=load('webview_device_gate')

class Followup(unittest.TestCase):
    def sample(self,boot_id='a'*64,latest=10,queue='q'*64,owned=None):
        return {'boot_id_sha256':boot_id,'installed_binary_sha256':'b'*64,
                'api':{'events':{'latest':latest,'degraded':False}},
                'private_hashes':{'queued_edits':{'present':True,'sha256':queue},
                                  'offline_reviews':{'present':False}},
                'ce_available':'true','boot_completed':'1','owned_job_state':owned,
                'owned_interruption_event_seen':owned=='INTERRUPTED'}
    def test_same_boot_blocked(self):
        rows=boot.decide(self.sample(),self.sample())
        self.assertEqual(rows[0]['status'],'BLOCKED')
    def test_reboot_monotonic_and_preserved(self):
        rows=boot.decide(self.sample(owned='RUNNING'),self.sample('c'*64,11,owned='INTERRUPTED'),owned=True)
        self.assertEqual(rows[0]['status'],'PASS')
        self.assertEqual(rows[2]['status'],'PASS')
        self.assertEqual(rows[-2]['status'],'PASS')
        self.assertEqual(rows[-1]['status'],'BLOCKED')
    def test_event_reset_fail(self):
        rows=boot.decide(self.sample(),self.sample('c'*64,1))
        self.assertEqual(rows[2]['status'],'FAIL')
    def test_queued_edit_change_fail_closed(self):
        rows=boot.decide(self.sample(),self.sample('c'*64,11,queue='d'*64))
        self.assertIn('FAIL',[r['status'] for r in rows if 'queued_edits' in r['test']])
    def test_owned_job_not_proven(self):
        rows=boot.decide(self.sample(),self.sample('c'*64,11))
        self.assertEqual(rows[-2]['status'],'BLOCKED')
    def test_manager_check_foreground_only(self):
        self.assertTrue(web.foreground_manager('  topResumedActivity=ActivityRecord{123 u0 me.weishu.kernelsu/.Main t456}','me.weishu.kernelsu'))
        self.assertFalse(web.foreground_manager('  historic ActivityRecord{123 u0 me.weishu.kernelsu/.Main t456}','me.weishu.kernelsu'))
        self.assertFalse(web.foreground_manager('  topResumedActivity=ActivityRecord{123 u0 com.termux/.Main t456}','me.weishu.kernelsu'))
    def test_strict_webview_receipt(self):
        import datetime as dt
        stamp=dt.datetime.now(dt.timezone.utc).isoformat()
        sample={'schema_version':1,'kind':'SKYBIND_KSU_WEBVIEW_READONLY_PROBE',
                'recorded_at_utc':stamp,
                'observations':[{'test':'Actual KernelSU ksu.exec transport','status':'PASS'}]}
        values=web.parse_receipt(sample)
        self.assertEqual(values['Actual KernelSU ksu.exec transport'],'PASS')
        self.assertEqual(values['Embedded jobs.status presentation'],'BLOCKED')
        sample['observations'].append(sample['observations'][0])
        with self.assertRaises(boot.GateError):web.parse_receipt(sample)
    def test_partial_webview_always_blocked(self):
        outcomes=web.evaluate({name:'PASS' for name in web.CHECKS},True,True,'a'*64)
        self.assertEqual(sum(o['status']=='PASS' for o in outcomes),6)
        self.assertEqual(sum(o['status']=='BLOCKED' for o in outcomes),4)
        self.assertTrue(all(o['status']=='BLOCKED' for o in outcomes[-4:]))
    def test_wrapper_independent(self):
        t=(ROOT/'.devtool.toml').read_text()
        for command in ('api-webview-gate','api-boot-prepare','api-boot-verify'):
            self.assertIn('[wrapper.commands.'+command+']',t)
        self.assertNotIn('reboot',str((D/'boot_journal_gate.py').read_text().split('subprocess.run(')[1][:90]))
if __name__=='__main__':unittest.main()
