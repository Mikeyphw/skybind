"""Synthetic SB-Q04P1 contract tests. Never represent real CI source builds."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

ROOT=Path(__file__).resolve().parents[2]

def load(name, rel):
    spec=importlib.util.spec_from_file_location(name,ROOT/rel)
    assert spec and spec.loader
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

r=load('q04p_runtime','scripts/dev/runtime/skybind_runtime.py')
s=load('q04p_source_build','scripts/dev/runtime/source_build.py')
COMMIT='a'*40

def elf(tail=0):
    blob=bytearray(96)
    blob[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH',blob,16,2,183)
    blob[-1]=tail
    return bytes(blob)

def fixture(root:Path):
    archive=root/'magisk-rclone_arm64-v8a.zip'
    with ZipFile(archive,'w') as z:
        for name in ('system/vendor/bin/rclone','system/vendor/bin/fusermount3'):
            zi=ZipInfo(name);zi.create_system=3
            zi.external_attr=(stat.S_IFREG|0o755)<<16
            z.writestr(zi,elf())
    lock={'schema':1,'newfuture':{'repository':r.NEWFUTURE,'tag':'v1.75.0',
        'asset':archive.name,'archive_sha256':r.filehash(archive)},
        'bclone':{'repository':r.BCLONE,'commit':COMMIT,
                  'ndk_revision':s.PIN_NDK,'go_version':s.PIN_GO}}
    lp=root/'source.lock.json'
    lp.write_bytes(s.canonical(lock))
    return archive,lp

def stage(root:Path,lock:Path,tail=42):
    root.mkdir(parents=True,exist_ok=True)
    binary=root/'rclone';binary.write_bytes(elf(tail));binary.chmod(0o755)
    record={'schema_version':1,'qualification':'UNATTESTED_SOURCE_BUILD',
            'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED','provider':'bclone',
            'repository':r.BCLONE,'source_commit':COMMIT,
            'lock_sha256':s.filehash(lock), 'go_version':s.PIN_GO,
            'ndk_revision':s.PIN_NDK,'android_api':21,'goos':'android','goarch':'arm64',
            'binary_name':'rclone','binary_sha256':s.filehash(binary),
            'binary_size':binary.stat().st_size}
    provenance=root/'provenance.json';provenance.write_bytes(s.canonical(record))
    (root/'SHA256SUMS').write_text(
        f"{s.filehash(binary)}  rclone\n{s.filehash(provenance)}  provenance.json\n")
    return record

class SingleBuildAuthorityTests(unittest.TestCase):
    def test_verified_binary_reused_without_second_build(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset,lock=fixture(root)
            build=root/'built';proof=stage(build,lock)
            with patch.object(r,'build_bclone',side_effect=AssertionError('rebuild attempted')):
                r.assemble('bclone',asset,root/'bclone.zip',lock_path=lock,bclone_build_dir=build)
            package=r.verify_package(root/'bclone.zip')
            self.assertEqual(package['provider'],'bclone')
            self.assertEqual(package['files']['system/bin/rclone']['sha256'],proof['binary_sha256'])
            with ZipFile(root/'bclone.zip') as z:
                self.assertEqual(z.read('system/bin/rclone'),(build/'rclone').read_bytes())

    def test_stale_commit_and_changed_lock_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset,lock=fixture(root);build=root/'built';stage(build,lock)
            obj=json.loads(lock.read_text());obj['bclone']['commit']='b'*40;lock.write_bytes(s.canonical(obj))
            with self.assertRaisesRegex(r.Reject,'lock'):
                r.assemble('bclone',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)
            self.assertFalse((root/'bad.zip').exists())
            obj['bclone']['commit']=COMMIT;obj['bclone']['go_version']='1.27.1';lock.write_bytes(s.canonical(obj))
            with self.assertRaisesRegex(r.Reject,'pins'):
                r.assemble('bclone',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)

    def test_build_binary_and_receipt_tampering_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset,lock=fixture(root);build=root/'built';stage(build,lock)
            (build/'rclone').write_bytes(elf(34))
            with self.assertRaisesRegex(r.Reject,'receipt rejected'):
                r.assemble('bclone',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)
            stage(build,lock)
            proof=json.loads((build/'provenance.json').read_text())
            proof['repository']='wrong/project'
            (build/'provenance.json').write_bytes(s.canonical(proof))
            (build/'SHA256SUMS').write_text(
                f"{s.filehash(build/'rclone')}  rclone\n{s.filehash(build/'provenance.json')}  provenance.json\n")
            with self.assertRaisesRegex(r.Reject,'mismatches'):
                r.assemble('bclone',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)

    def test_missing_symlink_extra_receipts_and_invalid_elf_denied(self):
        for issue in ('missing','symlink','extra','elf'):
            with self.subTest(issue=issue),tempfile.TemporaryDirectory() as td:
                root=Path(td);asset,lock=fixture(root);build=root/'built';stage(build,lock)
                if issue=='missing':(build/'SHA256SUMS').unlink()
                if issue=='symlink':
                    (build/'rclone').unlink();(build/'rclone').symlink_to('/etc/hosts')
                if issue=='extra':(build/'secret.txt').write_text('unexpected')
                if issue=='elf':
                    (build/'rclone').write_bytes(b'not-elf')
                    pr=json.loads((build/'provenance.json').read_text())
                    pr['binary_sha256']=s.filehash(build/'rclone');pr['binary_size']=(build/'rclone').stat().st_size
                    (build/'provenance.json').write_bytes(s.canonical(pr))
                    (build/'SHA256SUMS').write_text(f"{s.filehash(build/'rclone')}  rclone\n{s.filehash(build/'provenance.json')}  provenance.json\n")
                with self.assertRaises(r.Reject):
                    r.assemble('bclone',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)

    def test_ambiguous_source_or_newfuture_build_input_denied(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset,lock=fixture(root);build=root/'built';stage(build,lock)
            with self.assertRaisesRegex(r.Reject,'mix'):
                r.assemble('bclone',asset,root/'bad.zip',root,root,lock,bclone_build_dir=build)
            with self.assertRaisesRegex(r.Reject,'NewFuture package'):
                r.assemble('newfuture',asset,root/'bad.zip',lock_path=lock,bclone_build_dir=build)
            self.assertFalse((root/'bad.zip').exists())

    def test_compare_real_synthetic_packages_bound_to_separate_lanes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);asset,lock=fixture(root)
            for lane in ('A','B'):
                b=root/lane/'bclone_build';stage(b,lock)
                p=root/lane/'packages';p.mkdir()
                r.assemble('newfuture',asset,p/'newfuture.zip',lock_path=lock)
                r.assemble('bclone',asset,p/'bclone.zip',lock_path=lock,bclone_build_dir=b)
            result=s.compare(root/'A/bclone_build',root/'B/bclone_build',root/'A/packages',root/'B/packages')
            self.assertEqual(result['status'],'BYTE_IDENTICAL_UNATTESTED')
            self.assertEqual(result['gate_g01'],'BLOCKED')
            self.assertEqual(result['final_seal'],'NOT_ISSUED')
            # Replacing a zipped binary must fail independently from a synthetic success receipt.
            b=root/'B/bclone_build';stage(b,lock,tail=41)
            with self.assertRaises(s.Rejected):
                s.compare(root/'A/bclone_build',b,root/'A/packages',root/'B/packages')

    def test_ci_and_devtool_must_use_exact_verified_output(self):
        workflow=(ROOT/'.github/workflows/skybind-provider-reproducibility.yml').read_text()
        between=workflow.split('Package exactly the separately verified build bytes',1)[1].split('Upload independent lane bytes',1)[0]
        self.assertIn('--bclone-build-dir dist/lane/bclone_build',between)
        self.assertNotIn('--bclone-checkout',between)
        self.assertEqual(workflow.count('source_build.py build'),1)
        self.assertIn('source_build.py compare',workflow)
        registry=(ROOT/'.devtool.toml').read_text()
        self.assertIn('[targets.skybind.jobs.q04p1-build-binding-contract]',registry)
        self.assertIn('q04p1-build-binding-contract = ["job:q04p1-build-binding-contract"]',registry)
        self.assertIn('go-version: \'1.27.2\'',workflow)

if __name__=='__main__':unittest.main()
