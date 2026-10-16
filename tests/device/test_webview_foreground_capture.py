"""Isolated regression checks for Android foreground evidence collection."""
from __future__ import annotations
import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch

DEVICE=pathlib.Path(__file__).resolve().parents[2]/'scripts/dev/device'
sys.path.insert(0,str(DEVICE))
import webview_device_gate as gate

PKG='me.weishu.kernelsu'
OTHER='com.termux'
def snap(pkg=PKG,mode='topResumedActivity'):
    return f'\n mTaskHistory: old {PKG}/OldView\n {mode}=ActivityRecord{{abc u0 {pkg}/.ui.MainActivity t14}}\n'

class ForegroundTests(unittest.TestCase):
    def test_positive_current(self):
        self.assertTrue(gate.foreground_manager(snap(),PKG))
    def test_negative_termux_in_foreground(self):
        self.assertFalse(gate.foreground_manager(snap(OTHER),PKG))
    def test_negative_historical(self):
        self.assertFalse(gate.foreground_manager('lastResumedActivity=ActivityRecord{ u0 '+PKG+'/.Foo }',PKG))
    def test_other_manager_not_wrongly_matched(self):
        self.assertFalse(gate.foreground_manager(snap('com.rifsxd.ksunext'),PKG))
    def test_requires_two_consecutive_positive_snapshots(self):
        replies=iter([snap(OTHER),snap(),snap()])
        clock=[0.0]
        def tick():return clock[0]
        def sleep(n):clock[0]+=n
        ok,ev=gate.observe_foreground(PKG,observation_seconds=10,interval_seconds=2,
            root_command=lambda *_a,**_k:next(replies),clock=tick,sleep=sleep)
        self.assertTrue(ok)
        self.assertEqual(ev['attempts'],3)
        self.assertEqual(ev['positive_samples'],2)
        self.assertEqual(ev['status'],'MATCHED')
    def test_non_consecutive_positives_do_not_pass(self):
        clock=[0.0]
        replies=iter([snap(),snap(OTHER),snap(),snap(OTHER),snap()])
        def sleep(n):clock[0]+=n
        ok,ev=gate.observe_foreground(PKG,observation_seconds=5,interval_seconds=1,
            root_command=lambda *_a,**_k:next(replies),clock=lambda:clock[0],sleep=sleep)
        self.assertFalse(ok)
        self.assertEqual(ev['status'],'NOT_PROVEN')
    def test_dumpsys_failure_stays_blocked(self):
        clock=[0.0]
        def sleep(n):clock[0]+=n
        def fail(*_a,**_k):raise gate.GateError('su unavailable')
        ok,ev=gate.observe_foreground(PKG,observation_seconds=3,interval_seconds=1,
            root_command=fail,clock=lambda:clock[0],sleep=sleep)
        self.assertFalse(ok)
        self.assertGreaterEqual(ev['attempts'],2)
    def test_auto_manager_variant(self):
        clock=[0.0]
        def sleep(n):clock[0]+=n
        ok,ev=gate.observe_foreground('auto',observation_seconds=4,interval_seconds=1,
            root_command=lambda *_a,**_k:snap('com.rifsxd.ksunext'),
            clock=lambda:clock[0],sleep=sleep)
        self.assertTrue(ok)
    def test_input_constraints(self):
        with self.assertRaises(gate.GateError): gate.observe_foreground('evil',root_command=lambda *x,**k:snap())
        with self.assertRaises(gate.GateError): gate.observe_foreground(PKG,observation_seconds=1)
        with self.assertRaises(gate.GateError): gate.observe_foreground(PKG,interval_seconds=0)
    def test_fail_is_not_masked_by_missing_foreground(self):
        parsed={name:'PASS' for name in gate.CHECKS}
        parsed['Actual KernelSU ksu.exec transport']='FAIL'
        outcomes=gate.evaluate(parsed,False,True,'a'*64)
        states={x['test']:x['status'] for x in outcomes}
        self.assertEqual(states['Actual KernelSU ksu.exec transport'],'FAIL')
        self.assertEqual(states['Embedded jobs.status presentation'],'BLOCKED')
    def test_no_promotion_without_asset_match(self):
        parsed={name:'PASS' for name in gate.CHECKS}
        outcomes=gate.evaluate(parsed,True,False,'a'*64)
        self.assertTrue(all(x['status']=='BLOCKED' for x in outcomes if x['test'] in gate.CHECKS))
if __name__=='__main__':unittest.main()
