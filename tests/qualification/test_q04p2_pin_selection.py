"""SB-Q04P2: selected CI inputs never become release trust evidence."""
from __future__ import annotations
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

def load(module,filename):
    spec=importlib.util.spec_from_file_location(module,ROOT/'scripts/dev/runtime'/filename)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

pins=load('q04p2_pin_selection','pin_selection.py')
builder=load('q04p2_source_build','source_build.py')

class SelectedPinsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.lock=self.root/'source.lock.json'
        self.policy=self.root/'source.selection.json'
        self.original_lock=(ROOT/'scripts/dev/runtime/source.lock.json').read_bytes()
        self.original_policy=(ROOT/'scripts/dev/runtime/source.selection.json').read_bytes()
        self.reset()

    def reset(self):
        self.lock.write_bytes(self.original_lock);self.policy.write_bytes(self.original_policy)

    def check(self):return pins.verify(self.lock,self.policy)

    def put(self,field,obj):
        target=self.lock if field=='lock' else self.policy
        target.write_text(json.dumps(obj))

    def test_selected_pins_are_immutable_and_not_attested(self):
        r=self.check()
        self.assertEqual(r['status'],'INPUTS_SELECTED_UNATTESTED')
        self.assertTrue(r['may_run_raw_ci'])
        self.assertFalse(r['independent_attestation'])
        self.assertEqual(r['gate_g01'],'BLOCKED')
        self.assertEqual(r['final_seal'],'NOT_ISSUED')
        self.assertEqual(builder.load_lock(builder.DEFAULT_LOCK)['bclone']['commit'],pins.BCLONE_COMMIT)

    def test_any_single_pin_mutation_denied(self):
        for section,key,bad in [('newfuture','archive_sha256','a'*64),('newfuture','repository','evil'),
                                 ('bclone','commit','b'*40),('bclone','go_version','1.27.1'),
                                 ('bclone','ndk_revision','other')]:
            with self.subTest(section=section,key=key):
                self.reset()
                data=json.loads(self.lock.read_text());data[section][key]=bad
                self.put('lock',data)
                with self.assertRaises(pins.Rejected):self.check()

    def test_policy_scope_custody_and_approval_forgery_denied(self):
        for chain,key,value in [('newfuture','reported_vcs_modified',False),
              ('newfuture','rebuild_permitted',True),('newfuture','binary_custody','SIGNED'),
              ('bclone','github_signature','verified'),('bclone','source_dependency_review','APPROVED'),
              ('toolchain','authenticated_packages',True),('evidence_reference','class','ATTESTED'),
              (None,'independent_attestation',True),(None,'real_builds_executed',True),
              (None,'gate_g01','PASS'),(None,'final_seal','ISSUED'),(None,'authorization_scope','RELEASE')]:
            with self.subTest(chain=chain,key=key):
                self.reset();data=json.loads(self.policy.read_text())
                (data if chain is None else data[chain])[key]=value
                self.put('policy',data)
                with self.assertRaises(pins.Rejected):self.check()

    def test_lock_policy_rehash_cannot_override_known_candidates(self):
        data=json.loads(self.lock.read_text());data['bclone']['commit']='b'*40
        self.put('lock',data)
        pol=json.loads(self.policy.read_text())
        pol['source_lock_canonical_sha256']=hashlib.sha256(pins.canonical(data)).hexdigest()
        pol['bclone']['commit']='b'*40
        self.put('policy',pol)
        with self.assertRaisesRegex(pins.Rejected,'bclone'):self.check()

    def test_symlink_missing_and_invalid_json_denied(self):
        self.lock.unlink();self.lock.symlink_to(self.original_policy and self.policy)
        with self.assertRaisesRegex(pins.Rejected,'symlink'):self.check()
        self.lock.unlink();self.lock.write_text('{bad')
        with self.assertRaisesRegex(pins.Rejected,'invalid JSON'):self.check()
        self.lock.unlink()
        with self.assertRaisesRegex(pins.Rejected,'missing'):self.check()

    def test_ci_requires_selection_and_never_promotes_gate(self):
        w=(ROOT/'.github/workflows/skybind-provider-reproducibility.yml').read_text()
        a=w.index('pin_selection.py verify');b=w.index('source_build.py pins')
        self.assertLess(a,b)
        self.assertIn('lane: [A, B]',w)
        self.assertIn('verify-newfuture',w)
        self.assertNotIn('schedule:',w)
        self.assertNotIn('release create',w)
        self.assertIn('--bclone-build-dir dist/lane/bclone_build',w)
        src=(ROOT/'.github/workflows/skybind-source.yml').read_text()
        self.assertIn('check_q04p2_pin_selection.sh',src)
        q=(ROOT/'.devtool.toml').read_text()
        self.assertIn('q04p2-pin-selection-contract',q)

    def test_newfuture_prebuilt_unchanged_and_does_not_rebuild(self):
        policy=json.loads(self.policy.read_text())
        self.assertTrue(policy['newfuture']['prebuilt_only'])
        self.assertFalse(policy['newfuture']['rebuild_permitted'])
        self.assertEqual(policy['newfuture']['sha256'],pins.NEWFUTURE_SHA)
        w=(ROOT/'.github/workflows/skybind-provider-reproducibility.yml').read_text()
        self.assertIn('gh release download v1.75.0',w)
        self.assertNotIn('git clone https://github.com/NewFuture',w)
        self.assertNotIn('build-newfuture',w)

if __name__=='__main__':unittest.main()
