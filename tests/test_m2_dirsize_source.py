"""Fail-closed M2 size compatibility source regressions, no Android build."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('m2_dirsize_gate',ROOT/'scripts/dev/android/m2_dirsize_source_gate.py')
GATE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

class DirectorySizeGateTests(unittest.TestCase):
    def test_source_positive(self):
        self.assertEqual(GATE.verify(ROOT)['state'], 'PASS_M2_DIRSIZE_SOURCE_ONLY')

    def reject_mutation(self, key, before, after):
        with tempfile.TemporaryDirectory(prefix='m2-size-') as folder:
            base=Path(folder)
            for rel in GATE.PATHS.values():
                p=base/rel;p.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,p)
            p=base/GATE.PATHS[key]
            data=p.read_text()
            self.assertIn(before,data)
            p.write_text(data.replace(before,after,1))
            with self.assertRaises(GATE.Violation): GATE.verify(base)

    def test_live_browse_failure_categories_are_preserved(self):
        import importlib.util
        source = ROOT / 'scripts/dev/android/m2_live_device.py'
        spec = importlib.util.spec_from_file_location('m2_live_dirsize', source)
        live = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(live)
        for suffix in ('VALIDATION','RESPONSE','AUTHORIZATION','TRANSPORT'):
            reason = 'SKYBIND_LIVE_FAILED_BROWSE_' + suffix
            state, classified = live.parse_live('INSTRUMENTATION_STATUS: stack=' + reason)
            with self.subTest(category=suffix):
                self.assertEqual((state, classified), ('FAILED', reason))

    def test_negative_go_file_size_bypass(self):
        self.reject_mutation('go','!entry.IsDir || entry.Size != -1','entry.Size != -1')

    def test_negative_go_directory_underflow(self):
        self.reject_mutation('go','entry.Size != -1','entry.Size < -1')

    def test_negative_android_file_size_bypass(self):
        self.reject_mutation('kt','isDir && size == -1L','size == -1L')

    def test_negative_android_directory_underflow(self):
        self.reject_mutation('kt','size == -1L','size < 0L')

    def test_negative_missing_go_regression(self):
        self.reject_mutation('go_test','TestBrowseRejectsInvalidNegativeSizes','NoNegativeCases')

    def test_negative_missing_android_regression(self):
        self.reject_mutation('kt_test','rejectsNegativeFileSizeAndDirectoryBelowUnknownMarker','NoNegativeCases')

    def test_negative_missing_live_classification(self):
        self.reject_mutation('live','SKYBIND_LIVE_FAILED_BROWSE_VALIDATION','SKYBIND_LIVE_FAILED_BROWSE')

    def test_negative_missing_host_classification(self):
        self.reject_mutation('host',"'SKYBIND_LIVE_FAILED_BROWSE_VALIDATION'", "'SKYBIND_LIVE_FAILED_BROWSE'")

    def test_negative_missing_grouped_tests(self):
        self.reject_mutation('grouped', 'tests.test_m2_dirsize_source', 'tests.test_missing_dirsize')

if __name__=='__main__': unittest.main()
