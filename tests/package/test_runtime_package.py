import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import struct
import tempfile
import unittest
from zipfile import ZipFile,ZipInfo

P=Path(__file__).resolve().parents[2]/'scripts/dev/runtime/skybind_runtime.py'
spec=importlib.util.spec_from_file_location('skybind_runtime',P)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def elf(shared=False):
    b=bytearray(96);b[:7]=b'\x7fELF\x02\x01\x01';struct.pack_into('<HH',b,16,3 if shared else 2,183)
    return bytes(b)

def fixture(d):
    a=d/'magisk-rclone_arm64-v8a.zip'
    with ZipFile(a,'w') as z:
        for name,blob in [('system/bin/rclone',elf()),('system/vendor/bin/fusermount3',elf()),('system/vendor/lib64/libfuse3.so',elf(True))]:
            info=ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFREG|0o755)<<16;z.writestr(info,blob)
    lock={'schema':1,'newfuture':{'repository':r.NEWFUTURE,'tag':'v1.75.0','asset':a.name,'archive_sha256':r.filehash(a)},'bclone':{'repository':r.BCLONE,'commit':None,'ndk_revision':None,'go_version':None}}
    l=d/'source.lock.json';l.write_text(json.dumps(lock));return a,l

class RuntimeTests(unittest.TestCase):
    def test_no_unpinned_production_build(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root);lock=json.loads(l.read_text());lock['newfuture']['archive_sha256']=None;l.write_text(json.dumps(lock))
            with self.assertRaises(r.Reject):r.assemble('newfuture',a,root/'out.zip',lock_path=l)
    def test_determinism_and_helper_parity_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root)
            x=r.assemble('newfuture',a,root/'one.zip',lock_path=l)
            y=r.assemble('newfuture',a,root/'two.zip',lock_path=l)
            self.assertEqual(x,y)
            pr=r.verify_package(root/'one.zip');self.assertEqual(pr['provider'],'newfuture')
            self.assertEqual(pr['files']['system/vendor/bin/fusermount3']['sha256'],r.digest(elf()))
    def test_archive_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root);a.write_bytes(a.read_bytes()+b'garbage')
            with self.assertRaises(r.Reject):r.assemble('newfuture',a,root/'out.zip',lock_path=l)
    def test_archive_traversal_symlink_duplicates_wrong_abi_and_missing_lib(self):
        for kind in ['traversal','symlink','duplicate','wrong_abi','missing_lib']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as d:
                root=Path(d);a,l=fixture(root)
                with ZipFile(a,'w') as z:
                    for name,blob in [('system/bin/rclone',elf() if kind!='wrong_abi' else b'notelf'),('system/vendor/bin/fusermount3',elf())]+([] if kind=='missing_lib' else [('system/vendor/lib64/libfuse3.so',elf(True))]):
                        info=ZipInfo(name);info.create_system=3;info.external_attr=(stat.S_IFREG|0o755)<<16;z.writestr(info,blob)
                    if kind=='traversal':z.writestr('../secret','bad')
                    if kind=='symlink':
                        zi=ZipInfo('link');zi.create_system=3;zi.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(zi,'/etc/passwd')
                    if kind=='duplicate':z.writestr('system/bin/rclone',elf())
                lock=json.loads(l.read_text());lock['newfuture']['archive_sha256']=r.filehash(a);l.write_text(json.dumps(lock))
                with self.assertRaises(r.Reject):r.assemble('newfuture',a,root/'out.zip',lock_path=l)
    def test_package_tamper(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root);r.assemble('newfuture',a,root/'out.zip',lock_path=l)
            with ZipFile(root/'out.zip','a') as z:z.writestr('random','X')
            with self.assertRaises(r.Reject):r.verify_package(root/'out.zip')
    def test_bclone_fails_without_full_pins_and_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root)
            with self.assertRaises(r.Reject):r.assemble('bclone',a,root/'out.zip',root,root,lock_path=l)
    def test_wrong_provider(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);a,l=fixture(root)
            with self.assertRaises(r.Reject):r.assemble('prebuilt',a,root/'out.zip',lock_path=l)
if __name__=='__main__':unittest.main()
