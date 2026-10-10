"""Skybind active eight-artifact campaign and immutable original obligation ledger.

This checks *planning/inventory*, never claims a release/device seal.
"""
import json
import tomllib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
DOCS=ROOT/'docs/roadmap'
TARGETS={'skybind','skybind_webui','skybind_runtime_inputs','skybind_android_device','skybind_release'}
def load():
 with (ROOT/'.devtool.toml').open('rb') as f: cfg=tomllib.load(f)
 data=json.loads((DOCS/'SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())
 return cfg,data
def check_all():
 cfg,data=load()
 assert cfg['workspace']['default_target']=='skybind'
 assert set(cfg['targets'])==TARGETS
 for item in cfg['targets'].values():
  assert (ROOT/item['root']).is_dir()
  assert 'bootstrap' in item['workflows']
 for name in ('SKYBIND_FEATURE_SPEC.md','SKYBIND_DEVTOOL_ROADMAP.md','SKYBIND_ORIGINAL_45_ITEM_INDEX.json','SKYBIND_ORIGINAL_45_ITEM_ROADMAP.md'):
  assert (DOCS/name).is_file(),name
 assert data['product']=='skybind'
 assert (data['delivery_count'],data['implementation_delivery_count'],data['remaining_gate_package_count'],data['final_seal_delivery_count'])==(8,6,1,1)
 packages=data['artifact_sequence'];assert len(packages)==8
 ids=[x['id'] for x in packages]
 assert ids==[f'SB-C{i:02d}' for i in range(1,7)]+['SB-CG1','SB-CFS1']
 original=json.loads((DOCS/'SKYBIND_ORIGINAL_45_ITEM_INDEX.json').read_text())
 assert original['overlay_count']==45 and original['typed_api_count']==57
 original_ids={x['id'] for x in original['implementation_overlays']+original['gate_overlays']+[original['final_seal']]}
 assert len(original_ids)==45
 coverage=data['coverage_map'];assert len(coverage)==34
 assert set(coverage)==original_ids-set(data['starting_position']['already_implemented_obligations'])-set(data['starting_position']['installed_gate_definitions'])
 assert set(coverage.values()) <= set(ids)
 ops=data['all_57_typed_operations'];assert len(ops)==57
 assert len({x['name'] for x in ops})==57
 live=json.loads((ROOT/'internal/control/operations.json').read_text())
 assert {x['name'] for x in ops}=={x['name'] for x in live['operations']}
 for e in packages:
  assert len(e['originals'])==len(set(e['originals']))
 assert all(x in ['BLOCKED'] for x in data['starting_position']['gate_qualification'].values())
 assert data['artifact_sequence'][0]['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED'
 # Source implementation status progresses as a strict prefix. Later overlays
 # must not be mislabeled delivered, and source passes never imply gates.
 delivered=[x['status']=='SOURCE_IMPLEMENTED_NOT_PROMOTED' for x in packages]
 assert delivered[:2]==[True,True]
 assert not any((not delivered[i]) and delivered[i+1] for i in range(len(delivered)-1))
 assert all(x['status'] in ('SOURCE_IMPLEMENTED_NOT_PROMOTED','PLANNED') for x in packages)

 assert 'dynamic runtime' in ' '.join(data['explicit_exclusions']).lower()
 assert not any('seal' in k for t in cfg['targets'].values() for k in t['workflows'])
 return cfg,data
def check_component(component):
 _,data=check_all()
 if component=='webui':assert 'direct' in str(data['preserved_contracts']).lower()
 elif component=='runtime':assert 'runtime' in str(data['preserved_contracts']).lower()
 elif component=='android':assert 'SB-G04' in data['coverage_map']
 elif component=='release':assert data['artifact_sequence'][-1]['status']=='PLANNED'
 else:raise ValueError('Unknown bootstrap component: '+component)
 return f'SKYBIND {component}: planning contract checked; implementation/device/seal NOT certified'
