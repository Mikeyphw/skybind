import json
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
class C04Contract(unittest.TestCase):
    def test_ledger_progression(self):
        p=json.loads((ROOT/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
        self.assertEqual([x['status'] for x in p['artifact_sequence'][:4]], ['SOURCE_IMPLEMENTED_NOT_PROMOTED']*4)
        self.assertTrue(all(x['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED' for x in p['artifact_sequence'][4:6]))
        self.assertEqual([x['status'] for x in p['artifact_sequence'][6:]],['SOURCE_IMPLEMENTED_NOT_PROMOTED','PLANNED'])
        self.assertEqual(p['starting_position']['gate_qualification'],{'SB-G01':'BLOCKED','SB-G02':'BLOCKED'})
    def test_no_webui_visual_parity_claim(self):
        self.assertTrue((ROOT/'module/webroot/index.html').exists())
        self.assertTrue((ROOT/'tests/fixtures/webui-reference/raw/index.html').exists())
    def test_transport_restrictions(self):
        content=(ROOT/'internal/webui/webui.go').read_text()
        self.assertIn('127.0.0.1:0',content)
        self.assertNotIn('0.0.0.0:0',content)
        self.assertNotIn('exec.Command(',content)
        self.assertIn('http.SameSiteStrictMode',content)
        self.assertIn('MaxBytesReader',content)
        self.assertIn('strictOrigin',content)
