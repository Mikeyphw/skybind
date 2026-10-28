from pathlib import Path
import json
import tomllib
import unittest
from scripts.devtool.typed_catalog_contract import validate_live_catalog
ROOT=Path(__file__).resolve().parents[2]
class IntegrationContracts(unittest.TestCase):
  def test_all_57_operations_and_copy_reference(self):
    catalog=json.loads((ROOT/'internal/control/operations.json').read_text())
    canonical=json.loads((ROOT/'docs/contracts/typed-operations.json').read_text())
    historical, current = validate_live_catalog(ROOT, live=catalog)
    self.assertEqual(len(historical),57)
    self.assertEqual(len(current),59)
    self.assertEqual({e['name'] for e in catalog['operations']},{e['name'] for e in canonical['operations']})
    self.assertTrue((ROOT/'module/webroot/style.css').read_bytes())
    self.assertTrue((ROOT/'tests/fixtures/webui-reference/manifest.json').is_file())
  def test_progress_no_fake_gates_and_devtool_workflows(self):
    plan=json.loads((ROOT/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
    self.assertEqual([x['status'] for x in plan['artifact_sequence'][:6]],['SOURCE_IMPLEMENTED_NOT_PROMOTED']*6)
    self.assertEqual([x['status'] for x in plan['artifact_sequence'][6:]],['SOURCE_IMPLEMENTED_NOT_PROMOTED']*2)
    self.assertEqual(plan['starting_position']['gate_qualification'],{'SB-G01':'BLOCKED','SB-G02':'BLOCKED'})
    with (ROOT/'.devtool.toml').open('rb') as f: cfg=tomllib.load(f)
    self.assertIn('integration-source',cfg['targets']['skybind']['workflows'])
    self.assertIn('release-candidate-source',cfg['targets']['skybind_release']['workflows'])
    self.assertIn('device-matrix-source',cfg['targets']['skybind_android_device']['workflows'])
    self.assertFalse(any(j.get('metadata',{}).get('final_seal') is True for j in cfg['targets']['skybind_release']['jobs'].values()))
  def test_no_install_download_or_mutable_runtime(self):
    hooks=[(ROOT/'module'/name).read_text() for name in ('customize.sh','service.sh','post-fs-data.sh','uninstall.sh')]
    content='\n'.join(line for hook in hooks for line in hook.splitlines() if not line.lstrip().startswith('#'))
    for bad in ('curl ','wget ','rclone update','rclone selfupdate','--allow-other-user', 'umount -l'):
      self.assertNotIn(bad,content)
if __name__=='__main__':unittest.main()
