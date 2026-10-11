"""SB-Q03R1 review replay and negative tests; none promote G01."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/runtime'))
import pin_review as r
import source_build as b

COMMIT='a'*40
PARENT='b'*40
ELF=bytearray(64)
ELF[:7]=b'\x7fELF\x02\x01\x01'
ELF[18:20]=(183).to_bytes(2,'little')

class ReviewTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.bundle=self.root/'bundle'
        (self.bundle/'inputs').mkdir(parents=True);(self.bundle/'outputs').mkdir()
        self.arc=self.bundle/'inputs/magisk-rclone_arm64-v8a.zip'
        with zipfile.ZipFile(self.arc,'w') as z:
            z.writestr('system/vendor/bin/rclone',bytes(ELF))
            z.writestr('system/vendor/bin/fusermount3',bytes(ELF))
        sha=b.filehash(self.arc)
        self.release={'tag_name':'v1.75.0','immutable':False,'draft':False,
            'html_url':'https://github.com/NewFuture/rclone-fuse3-magisk/releases/tag/v1.75.0',
            'assets':[{'id':123,'name':'magisk-rclone_arm64-v8a.zip','size':self.arc.stat().st_size,
                       'digest':'sha256:'+sha,'browser_download_url':'https://github.com/NewFuture/rclone-fuse3-magisk/releases/download/v1.75.0/magisk-rclone_arm64-v8a.zip'}]}
        self.commit={'sha':COMMIT,'html_url':'https://github.com/BenjiThatFoxGuy/bclone/commit/'+COMMIT,
                     'parents':[{'sha':PARENT}], 'commit':{'verification':{'verified':False,'reason':'unsigned'}}}
        self.raw={'producer':'SB-Q03-source-provenance','evidence_class':'RAW_UNATTESTED',
                  'newfuture':{'sha256_candidate':sha,'size':self.arc.stat().st_size,'github_asset_id':123},
                  'bclone':{'commit_candidate':COMMIT},'source_lock_altered':False,
                  'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED'}
        self.lock=self.root/'source.lock.json'
        self.lock.write_bytes((ROOT/'scripts/dev/runtime/source.lock.json').read_bytes())
        self.patches=[mock.patch.object(r,'CANDIDATE_SHA',sha),mock.patch.object(r,'COMMIT',COMMIT),
                      mock.patch.object(r,'ASSET_ID',123), mock.patch.object(r,'BC_PARENT',PARENT)]
        for p in self.patches: p.start();self.addCleanup(p.stop)
        self.save()

    def save(self):
        for name,obj in [('inputs/newfuture-release.json',self.release),
                         ('inputs/bclone-commit.json',self.commit)]:
            (self.bundle/name).write_text(json.dumps(obj))
        self.raw['newfuture']['release_api_json_sha256']=b.filehash(self.bundle/'inputs/newfuture-release.json')
        self.raw['bclone']['github_commit_api_json_sha256']=b.filehash(self.bundle/'inputs/bclone-commit.json')
        (self.bundle/'outputs/skybind-upstream-raw-unattested.json').write_text(json.dumps(self.raw))
        (self.bundle/'outputs/SHA256SUMS').write_text(''.join(f'{b.filehash(self.bundle/name)}  {name}\n' for name in r.FILES))

    def review(self):return r.reconcile(self.bundle,self.lock)

    def test_consistent_evidence_still_denies_approval(self):
        before=self.lock.read_bytes()
        result=self.review()
        self.assertEqual(result['reconciliation'],'CONSISTENT_UNATTESTED')
        self.assertEqual(result['toolchain']['selected_go_for_future_builds'],'1.27.2')
        self.assertFalse(result['may_populate_source_lock'])
        self.assertEqual(result['gates'],'G01-G08_BLOCKED')
        self.assertEqual(result['final_seal'],'NOT_ISSUED')
        self.assertEqual(before,self.lock.read_bytes())

    def test_checksums_and_snapshot_identity_rejected(self):
        original=self.arc.read_bytes()
        self.arc.write_bytes(original+b'evil')
        with self.assertRaisesRegex(r.Rejected,'SHA256SUMS'):self.review()
        self.arc.write_bytes(original[:-1]+b'X');self.save()
        with self.assertRaisesRegex(r.Rejected,'archive changed'):self.review()
        self.arc.write_bytes(original);self.save()
        self.release['assets'][0]['id']=999;self.save()
        with self.assertRaisesRegex(r.Rejected,'asset identity'):self.review()

    def test_release_commit_and_fake_qualification_rejected(self):
        self.commit['commit']['verification']['verified']=True;self.save()
        with self.assertRaisesRegex(r.Rejected,'unsigned'):self.review()
        self.commit['commit']['verification']['verified']=False;self.save()
        self.raw['final_seal']='ISSUED';self.save()
        with self.assertRaisesRegex(r.Rejected,'qualification'):self.review()

    def test_zip_traversal_and_duplicate_rejected(self):
        with zipfile.ZipFile(self.arc,'a') as z:z.writestr('../bad',b'bad')
        self.save()
        # A re-pinned test candidate still must reject unsafe archive structure.
        with mock.patch.object(r,'CANDIDATE_SHA',b.filehash(self.arc)):
            self.release['assets'][0]['digest']='sha256:'+b.filehash(self.arc)
            self.release['assets'][0]['size']=self.arc.stat().st_size
            self.raw['newfuture']['size']=self.arc.stat().st_size
            self.raw['newfuture']['sha256_candidate']=b.filehash(self.arc)
            self.save()
            with self.assertRaisesRegex(r.Rejected,'ZIP traversal'):self.review()

    def test_symlink_inputs_and_lock_promotion_rejected(self):
        original=self.bundle/'inputs/bclone-commit.json'
        backup=self.root/'original.json';backup.write_bytes(original.read_bytes())
        original.unlink();original.symlink_to(backup)
        with self.assertRaisesRegex(r.Rejected,'symlinked'):self.review()
        original.unlink();original.write_bytes(backup.read_bytes());self.save()
        lock=json.loads(self.lock.read_text());lock['bclone']['commit']=COMMIT
        self.lock.write_text(json.dumps(lock))
        with self.assertRaisesRegex(r.Rejected,'source lock has pins'):self.review()

    def test_repo_ci_policy_has_exact_consistent_go_version(self):
        self.assertEqual(b.PIN_GO,'1.27.2')
        w=(ROOT/'.github/workflows/skybind-provider-reproducibility.yml').read_text()
        self.assertIn("go-version: '1.27.2'",w)
        self.assertNotIn("go-version: '1.27.1'",w)
        self.assertIn('workflow_dispatch:',w)
        self.assertNotIn('schedule:',w)
        self.assertIsNone(json.loads((ROOT/'scripts/dev/runtime/source.lock.json').read_text())['bclone']['go_version'])

if __name__=='__main__':unittest.main()
