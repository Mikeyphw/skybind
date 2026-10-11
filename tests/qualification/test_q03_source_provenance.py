"""SB-Q03 negative contract fixtures. Never external G01 attestations."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts/dev/runtime'))
import source_provenance as p


def git(repo: Path, *args: str) -> str:
    cp = subprocess.run(['git','-C',str(repo),*args], check=True, capture_output=True, text=True)
    return cp.stdout.strip()


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.working = tempfile.TemporaryDirectory()
        self.addCleanup(self.working.cleanup)
        self.root = Path(self.working.name)
        self.repo = self.root/'bclone';self.repo.mkdir()
        git(self.repo, 'init','-q')
        git(self.repo, 'config','user.name','Fixture')
        git(self.repo, 'config','user.email','fixture@example.invalid')
        git(self.repo,'remote','add','origin',f'https://github.com/{p.BC}.git')
        (self.repo/'go.mod').write_text('module example.invalid/bclone\n\ngo 1.27\n')
        (self.repo/'go.sum').write_text('fake-versions from fixture\n')
        git(self.repo,'add','go.mod','go.sum')
        git(self.repo,'commit','-qm','fixture 1')
        (self.repo/'README').write_text('more source\n')
        git(self.repo,'add','README')
        git(self.repo,'commit','-qm','fixture 2')
        self.head = git(self.repo,'rev-parse','HEAD')
        self.parent = git(self.repo,'rev-parse','HEAD^')
        git(self.repo,'checkout','--detach','-q',self.head)
        self.arc = self.root/p.ASSET
        self.arc.write_bytes(b'fake-asset-not-an-ELF-or-qualification\n')
        sha = p.sha_file(self.arc)
        self.release = {'tag_name':p.TAG,'draft':False,'prerelease':False,
                        'html_url':f'https://github.com/{p.NF}/releases/tag/{p.TAG}',
                        'assets':[{'name':p.ASSET,'id':123456,'size':self.arc.stat().st_size,
                                   'digest':'sha256:'+sha,
                                   'browser_download_url':f'https://github.com/{p.NF}/releases/download/{p.TAG}/{p.ASSET}'}]}
        self.commit = {'sha':self.head,'html_url':f'https://github.com/{p.BC}/commit/{self.head}',
                       'parents':[{'sha':self.parent}],
                       'commit':{'verification':{'verified':True,'reason':'valid'}}}
        self.release_path = self.root/'release.json';self.commit_path = self.root/'commit.json'
        self.lock = self.root/'source.lock.json'
        self.lock.write_bytes((ROOT/'scripts/dev/runtime/source.lock.json').read_bytes())
        self.save()

    def save(self):
        self.release_path.write_text(json.dumps(self.release))
        self.commit_path.write_text(json.dumps(self.commit))

    def collect(self):
        return p.collect(self.arc,self.repo,self.release_path,self.commit_path,None,self.lock)

    def test_valid_observations_are_never_independent_attestation(self):
        start = self.lock.read_bytes()
        proof = self.collect()
        self.assertEqual(proof['newfuture']['sha256_candidate'],p.sha_file(self.arc))
        self.assertEqual(proof['bclone']['commit_candidate'],self.head)
        self.assertTrue(proof['bclone']['github_claims_signature_verified'])
        self.assertEqual(proof['evidence_class'],'RAW_UNATTESTED')
        self.assertEqual(proof['gate_g01'],'BLOCKED')
        self.assertEqual(proof['final_seal'],'NOT_ISSUED')
        self.assertFalse(proof['auto_approval'])
        self.assertFalse(proof['source_lock_pins_populated'])
        self.assertEqual(self.lock.read_bytes(),start)
        out = self.root/'report.json'
        p.write_report(out,proof,self.repo,self.lock)
        self.assertEqual(out.read_bytes(),p.q02.canonical(proof))
        self.assertEqual(out.stat().st_mode & 0o777,0o600)
        with self.assertRaisesRegex(p.Rejected,'overwrite'):
            p.write_report(out,proof,self.repo,self.lock)
        self.assertEqual(self.lock.read_bytes(),start)

    def test_wrong_archive_and_api_digest_and_api_url_fail(self):
        self.arc.write_bytes(self.arc.read_bytes()+b'tamper')
        with self.assertRaisesRegex(p.Rejected,'size'): self.collect()
        self.arc.write_bytes(b'fake-asset-not-an-ELF-or-qualification\n')
        self.release['assets'][0]['digest']='sha256:'+'a'*64;self.save()
        with self.assertRaisesRegex(p.Rejected,'SHA-256'):self.collect()
        self.release['assets'][0]['digest']='sha256:'+p.sha_file(self.arc)
        self.release['assets'][0]['browser_download_url']='https://attacker.invalid/'+p.ASSET
        self.save()
        with self.assertRaisesRegex(p.Rejected,'official'):self.collect()

    def test_missing_duplicate_or_draft_asset_fail(self):
        self.release['draft']=True;self.save()
        with self.assertRaisesRegex(p.Rejected,'draft'):self.collect()
        self.release['draft']=False
        self.release['assets'].append(copy.deepcopy(self.release['assets'][0]));self.save()
        with self.assertRaisesRegex(p.Rejected,'duplicated'):self.collect()
        self.release['assets']=[self.release['assets'][0]]
        self.release['assets'][0].pop('digest');self.save()
        with self.assertRaisesRegex(p.Rejected,'digest'):self.collect()

    def test_git_wrong_parent_dirty_branch_and_origin_fail(self):
        self.commit['parents']=[{'sha':'b'*40}];self.save()
        with self.assertRaisesRegex(p.Rejected,'parent'):self.collect()
        self.commit['parents']=[{'sha':self.parent}];self.save()
        (self.repo/'evil-untracked').write_text('unexpected')
        with self.assertRaisesRegex(p.Rejected,'modifications'):self.collect()
        (self.repo/'evil-untracked').unlink()
        git(self.repo,'checkout','-q','-B','branch-fixture',self.head)
        with self.assertRaisesRegex(p.Rejected,'detached'):self.collect()
        git(self.repo,'checkout','--detach','-q',self.head)
        git(self.repo,'remote','set-url','origin','https://example.invalid/fork.git')
        with self.assertRaisesRegex(p.Rejected,'canonical'):self.collect()

    def test_lock_never_filled_or_conflicting_reviewed_pin_fails(self):
        lock = json.loads(self.lock.read_text())
        lock['newfuture']['archive_sha256']='c'*64
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(p.Rejected,'contradicts'):self.collect()
        lock['newfuture']['archive_sha256']=p.sha_file(self.arc)
        self.lock.write_text(json.dumps(lock))
        self.assertFalse(self.collect()['source_lock_pins_populated'])
        self.assertEqual(json.loads(self.lock.read_text())['bclone']['commit'],None)

    def test_refuse_evidence_in_checkout_and_input_symlink(self):
        with self.assertRaisesRegex(p.Rejected,'inside'):
            p.write_report(self.repo/'report.json',self.collect(),self.repo,self.lock)
        link = self.root/'fake.json'
        link.symlink_to(self.release_path)
        with self.assertRaisesRegex(p.Rejected,'non-symlink'):
            p.collect(self.arc,self.repo,link,self.commit_path,None,self.lock)

    def test_toolchain_observation_never_promotes_and_invalid_ndk_fails(self):
        ndk = self.root/'ndk';ndk.mkdir()
        (ndk/'source.properties').write_text('Pkg.Revision = 28.2.13676358\n')
        tool = p.inspect_toolchain(ndk)
        self.assertEqual(tool['observed_ndk_revision'],p.q02.PIN_NDK)
        self.assertFalse(tool['toolchain_pins_reviewed'])
        self.assertIn('1.27.2',tool['security_review_required'])
        (ndk/'source.properties').write_text('Pkg.Revision = unrecognizable\nPkg.Revision = repeated\n')
        with self.assertRaisesRegex(p.Rejected,'ambiguous'):p.inspect_toolchain(ndk)

    def test_workflow_and_devtool_source_only(self):
        w=(ROOT/'.github/workflows/skybind-upstream-provenance.yml').read_text()
        self.assertIn('workflow_dispatch:',w)
        self.assertNotIn('schedule:',w)
        self.assertIn('source_provenance.py collect',w)
        self.assertNotIn('source.lock.json\n',w)
        self.assertNotIn('release create',w)
        self.assertIn('RAW_UNATTESTED',w)
        t=tomllib.loads((ROOT/'.devtool.toml').read_text())
        self.assertIn('q03-upstream-provenance-contract',t['targets']['skybind']['workflows'])
        self.assertEqual(t['wrapper']['commands']['q03-upstream-provenance-contract']['target'],'skybind')
        l=json.loads((ROOT/'scripts/dev/runtime/source.lock.json').read_text())
        self.assertIsNone(l['newfuture']['archive_sha256'])
        self.assertTrue(all(l['bclone'][x] is None for x in ('commit','ndk_revision','go_version')))


if __name__=='__main__': unittest.main()
