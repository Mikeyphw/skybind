import json
import pathlib
import tomllib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]
class C03Contracts(unittest.TestCase):
 def test_completeness_and_status(self):
  d=json.loads((ROOT/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
  assert d['artifact_sequence'][2]['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED'
  assert d['artifact_sequence'][3]['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED'
  assert d['artifact_sequence'][-1]['status']=='PLANNED'
  assert all(d['coverage_map'][f'SB-O{i}']=='SB-C03' for i in range(20,25))
  assert d['starting_position']['gate_qualification']=={'SB-G01':'BLOCKED','SB-G02':'BLOCKED'}
 def test_exact_57_and_c03_coverage(self):
  c=json.loads((ROOT/'internal/control/operations.json').read_text())
  assert c['total']==57 and len(c['operations'])==57
  expected={'jobs.snapshot','jobs.preview','jobs.apply','jobs.status','job.run.preview','job.run','rc.metrics','provider.status','provider.remotes','provider.browse','provider.crypt.password.status','provider.crypt.password.set','provider.crypt.preview','provider.crypt.create','provider.crypt.recovery.status'}
  assert expected == {i['name'] for i in c['operations'] if i['implementing_overlay'] in ('SB-O20','SB-O21','SB-O22','SB-O23','SB-O24')}
 def test_devtool_workflow_and_seal(self):
  with (ROOT/'.devtool.toml').open('rb') as f:c=tomllib.load(f)
  assert c['targets']['skybind']['workflows']['jobs-providers']==['job:jobs-providers-source']
  assert c['targets']['skybind']['jobs']['jobs-providers-source']['metadata']['device_qualification']==False
  assert not any('seal' in key for t in c['targets'].values() for key in t['workflows'])
 def test_finite_api_no_generic_rc(self):
  wire=(ROOT/'internal/daemon/wiring.go').read_text()
  assert all(f'register("{i}"' in wire for i in ('rc.metrics','job.run','jobs.apply','provider.browse','provider.crypt.create'))
  assert 'rc.proxy' not in wire and 'os/exec' not in wire
if __name__=='__main__':unittest.main()
