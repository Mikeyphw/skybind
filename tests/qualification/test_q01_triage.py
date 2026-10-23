"""Fail-closed negative fixtures and independent-gate passthrough checks."""
from pathlib import Path
import io, json, os, stat, struct, sys, tempfile, unittest, zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/qualification'))
import skybind_qualify as q

class Triage(unittest.TestCase):
    def test_personal_status_does_not_require_external_trust(self):
        s=q.actual_status(ROOT)
        self.assertEqual(s['personal_release_policy'],'SKYBIND_PERSONAL_V1')
        self.assertEqual(len(s['gate_statuses']),8)
        self.assertIn(s['final_status'],('PERSONAL_RELEASE_PENDING','PERSONAL_RELEASE_APPROVED'))
        self.assertTrue(s['personal_scope_only'])

    def test_archive_never_pins_itself(self):
        lock=json.loads((ROOT/'scripts/dev/runtime/source.lock.json').read_text())
        with tempfile.TemporaryDirectory() as t:
            f=Path(t)/lock['newfuture']['asset']
            with zipfile.ZipFile(f,'w') as z:
                for n in ('rclone','fusermount3','libfuse3.so'):
                    z.writestr(n,b'fixture')
            result=q.inspect_newfuture(f,ROOT)
            self.assertFalse(result['pin_matches'])
            self.assertEqual(result['source_authenticity'],'UNVERIFIED_BY_LOCAL_INSPECTION')
            self.assertEqual(result['qualification'],'RAW_UNATTESTED')
            self.assertEqual(len(lock['newfuture']['archive_sha256']),64)

    def test_zip_path_traversal_and_symlink_denied(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'test.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('../bad',b'b');z.writestr('rclone',b'b')
                z.writestr('fusermount3',b'b');z.writestr('libfuse3.so',b'b')
            with self.assertRaises(ValueError):q.verify_zip_structure(path)
            with zipfile.ZipFile(path,'w') as z:
                info=zipfile.ZipInfo('rclone');info.create_system=3;info.external_attr=(stat.S_IFLNK|0o777)<<16
                z.writestr(info,b'elsewhere')
                z.writestr('fusermount3',b'b');z.writestr('libfuse3.so',b'b')
            with self.assertRaises(ValueError):q.verify_zip_structure(path)


    def test_newfuture_v175_static_distribution_is_reported_not_qualified(self):
        lock=json.loads((ROOT/'scripts/dev/runtime/source.lock.json').read_text())
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/lock['newfuture']['asset']
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('system/vendor/bin/rclone',b'fixture')
                z.writestr('system/vendor/bin/fusermount3',b'fixture')
            inspected=q.inspect_newfuture(archive,ROOT)
            self.assertEqual(inspected['inventory']['libfuse_member_count'],0)
            self.assertEqual(inspected['inventory']['fuse_delivery'],'reviewed_static_helper_layout')
            self.assertEqual(inspected['qualification'],'RAW_UNATTESTED')
            self.assertFalse(inspected['pin_matches'])
            with self.assertRaises(ValueError):
                q.verify_zip_structure(archive,'v1.74.0')

    def test_unreviewed_empty_lib_layout_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            archive=Path(t)/'candidate.zip'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('a/rclone',b'fake')
                z.writestr('a/fusermount3',b'fake')
            with self.assertRaises(ValueError):
                q.verify_zip_structure(archive,'v1.75.0')

    def test_output_external_exclusive_private(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw.json'
            q.safe_write_external({'qualification':'RAW_UNATTESTED'},p,ROOT)
            self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):q.safe_write_external({},p,ROOT)
            with self.assertRaises(ValueError):q.safe_write_external({},ROOT/'docs'/'bad.json',ROOT)

    def test_status_main_never_returns_fake_gate_failure_as_command_failure(self):
        with patch.dict(os.environ,{'SKYBIND_VERIFIED_GATE_EVIDENCE_DIR':'',
          'SKYBIND_GATE_TRUST_PUBKEY':'','SKYBIND_GATE_TRUST_KEY_SHA256':'',
          'SKYBIND_FINAL_SEAL_EVIDENCE_DIR':'','SKYBIND_FINAL_SEAL_PUBKEY':'',
          'SKYBIND_FINAL_SEAL_PUBKEY_SHA256':''}):
            with patch('sys.stdout',new_callable=io.StringIO) as fp:
                self.assertEqual(q.main(['status'],root=ROOT),0)
            data=json.loads(fp.getvalue())
            self.assertIn(data['final_status'],('PERSONAL_RELEASE_PENDING','PERSONAL_RELEASE_APPROVED'))
            self.assertEqual(data['personal_release_policy'],'SKYBIND_PERSONAL_V1')

if __name__=='__main__':unittest.main()
