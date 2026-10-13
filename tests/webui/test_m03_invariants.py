"""Static WebUI contract tests complementary to Node and Go tests."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[2]
class M3Static(unittest.TestCase):
    def test_57_operations_unchanged(self):
        import json
        a=json.loads((ROOT/'internal/control/operations.json').read_text())
        b=json.loads((ROOT/'docs/contracts/typed-operations.json').read_text())
        self.assertEqual(a,b)
        self.assertEqual(a['total'],57)
    def test_mount_profile_safety_boundaries(self):
        app=(ROOT/'module/webroot/app.js').read_text()
        self.assertIn('effectiveVfsOptions(formValue(),state.editorProfiles)',app)
        self.assertIn("cachePressureAdvice(sample,config)",app)
        cache=(ROOT/'internal/mounts/cache/cache.go').read_text()
        self.assertIn('persistent writeback status unverified',cache)
        self.assertIn('stopped VFS may contain pending uploads',cache)
        self.assertIn('auto-prune disabled',cache)
        self.assertIn('--read-only',(ROOT/'internal/mounts/lifecycle/engine.go').read_text())
if __name__=='__main__':unittest.main()
