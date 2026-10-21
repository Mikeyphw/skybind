"""R1 opt-in PackageManager instrumentation outcome parser contract."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('r1_bkx', ROOT/'scripts/dev/android/r1_bkx_pm_device.py')
assert spec and spec.loader
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class BKXCase(unittest.TestCase):
    def test_exact_case_pass_and_no_qualification_leak(self):
        out=('INSTRUMENTATION_STATUS: numtests=1\n'
             'INSTRUMENTATION_STATUS: test=liveApprovedBKXSigningAndWrongSignerRejection\n'
             'INSTRUMENTATION_STATUS_CODE: 1\n'
             'INSTRUMENTATION_STATUS_CODE: 0\n'
             'INSTRUMENTATION_CODE: -1\n')
        self.assertEqual(m.interpret_instrumentation(out),('PASS_R1_BKX_PLATFORM_PM_OBSERVATION_ONLY',None))
        for forged in (out.replace('numtests=1','numtests=2'),out.replace('CODE: -1','CODE: 0'),out+'FAILURES!!!',out.replace('WRONG_SIGNER','WRONG_SIGNER')):
            if forged==out:continue
            self.assertNotEqual(m.interpret_instrumentation(forged)[0],'PASS_R1_BKX_PLATFORM_PM_OBSERVATION_ONLY')
    def test_missing_approved_signer_fails_closed(self):
        out='SKYBIND_R1_BLOCKED_OPERATOR_SIGNER_PIN_MISSING\nINSTRUMENTATION_CODE: -1\n'
        self.assertEqual(m.interpret_instrumentation(out)[0],'BLOCKED')
    def test_skipped_and_malformed_not_pass(self):
        for out in ('','INSTRUMENTATION_STATUS_CODE: -3', 'INSTRUMENTATION_STATUS: test=other\nINSTRUMENTATION_CODE: -1'):
            self.assertNotIn('PASS_',m.interpret_instrumentation(out)[0])
if __name__=='__main__':unittest.main()
