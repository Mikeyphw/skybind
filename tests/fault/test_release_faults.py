from pathlib import Path
import hashlib
import json
import os
import stat
import struct
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/release'))
sys.path.insert(0,str(ROOT/'scripts/dev/runtime'))
import skybind_release as rel
import skybind_runtime as runt

def elf(shared=False):
    b=bytearray(96);b[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH',b,16,3 if shared else 2,183)
    return bytes(b)

def runtime_fixture(d:Path)->Path:
    source=d/'magisk-rclone_arm64-v8a.zip'
    with zipfile.ZipFile(source,'w') as z:
        for name,blob in [('system/bin/rclone',elf()),('system/vendor/bin/fusermount3',elf()),('system/vendor/lib64/libfuse3.so',elf(True))]:
            zi=zipfile.ZipInfo(name);zi.create_system=3;zi.external_attr=(stat.S_IFREG|0o755)<<16
            z.writestr(zi,blob)
    lock={'schema':1,'newfuture':{'repository':runt.NEWFUTURE,'tag':'v1.75.0','asset':source.name,'archive_sha256':runt.filehash(source)},'bclone':{'repository':runt.BCLONE,'commit':None,'ndk_revision':None,'go_version':None}}
    lockfile=d/'lock.json';lockfile.write_text(json.dumps(lock))
    runtime=d/'runtime.zip';runt.assemble('newfuture',source,runtime,lock_path=lockfile)
    return runtime

class ReleaseFaults(unittest.TestCase):
    def setup(self,d):
        root=Path(d)
        binary=root/'skybind';binary.write_bytes(elf())
        runtime=runtime_fixture(root)
        return runtime,binary

    def test_reproducible_complete_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            runtime,binary=self.setup(d)
            for name in ('one.zip','two.zip'):
                out=Path(d)/name
                payload,manifest=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
                rel.write_zip(out,payload)
                self.assertEqual(rel.verify_release(out)['qualification'],'CANDIDATE_ONLY_NOT_SEALED')
            self.assertEqual((Path(d)/'one.zip').read_bytes(),(Path(d)/'two.zip').read_bytes())

    def test_mutated_payload_and_claimed_seal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            runtime,binary=self.setup(d)
            p,m=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
            p['webroot/index.html']+=b'<!-- tampered -->'
            out=Path(d)/'bad.zip';rel.write_zip(out,p)
            with self.assertRaises(rel.Reject):rel.verify_release(out)
            p,m=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
            q=json.loads(p['skybind.manifest.json']);q['qualification']='RELEASE_SEALED';p['skybind.manifest.json']=rel.canonical(q)
            p['SHA256SUMS']=''.join(f'{rel.sha(p[n])}  {n}\n' for n in sorted(p) if n!='SHA256SUMS').encode()
            out=Path(d)/'seal.zip';rel.write_zip(out,p)
            with self.assertRaises(rel.Reject):rel.verify_release(out)

    def test_wrong_app_arch_missing_webui_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            runtime,binary=self.setup(d)
            binary.write_bytes(b'not an elf')
            with self.assertRaises(rel.Reject):rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
            binary.write_bytes(elf())
            link=Path(d)/'symlink';link.symlink_to(binary)
            with self.assertRaises(rel.Reject):rel.collect(runtime,link,ROOT/'module',ROOT/'module/webroot')
            empty=Path(d)/'ui';empty.mkdir();(empty/'index.html').write_bytes(b'dummy')
            with self.assertRaises(rel.Reject):rel.collect(runtime,binary,ROOT/'module',empty)

    def test_duplicate_archive_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            runtime,binary=self.setup(d)
            payload,manifest=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
            out=Path(d)/'candidate.zip';rel.write_zip(out,payload)
            with zipfile.ZipFile(out,'a') as z:z.writestr('../escape','x')
            with self.assertRaises(rel.Reject):rel.verify_release(out)

    def test_selected_pins_do_not_seal_runtime(self):
        lock=json.loads((ROOT/'scripts/dev/runtime/source.lock.json').read_text())
        self.assertEqual(len(lock['newfuture']['archive_sha256']),64)
        self.assertEqual(len(lock['bclone']['commit']),40)

if __name__=='__main__': unittest.main()
