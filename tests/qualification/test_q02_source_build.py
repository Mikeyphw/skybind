"""SB-Q02 local contract/negative tests. Fake compilers != independent builds."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import tomllib
import zipfile
import stat
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
P = ROOT/'scripts/dev/runtime/source_build.py'
spec = importlib.util.spec_from_file_location('sb_q02_builder',P)
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def elf() -> bytes:
    out=bytearray(96)
    out[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH',out,16,2,183)
    return bytes(out)


def pins() -> dict:
    return {'schema':1, 'newfuture':{'repository':b.NEWFUTURE_REPO,
             'tag':'v1.75.0','asset':'magisk-rclone_arm64-v8a.zip','archive_sha256':'a'*64},
            'bclone':{'repository':b.BCLONE_REPO,'commit':'b'*40,
                      'ndk_revision':b.PIN_NDK,'go_version':b.PIN_GO}}


class BuilderContractTests(unittest.TestCase):
    def test_current_unattested_lock_must_not_produce_real_build(self):
        with self.assertRaisesRegex(b.Rejected,'BLOCKED'):
            b.load_lock(b.DEFAULT_LOCK)
        self.assertFalse((ROOT/'build/evidence/sb_g01_provider_builds.json').is_file())

    def test_reviewed_lock_values_required_not_invented(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source.lock.json'; obj=pins()
            for group,key,value in [('newfuture','archive_sha256',None),
                                    ('bclone','commit',None),
                                    ('bclone','ndk_revision','28.1'),
                                    ('bclone','go_version','1.26.0')]:
                broken=json.loads(json.dumps(obj));broken[group][key]=value
                p.write_text(json.dumps(broken))
                with self.subTest(key=key),self.assertRaises(b.Rejected):b.load_lock(p)
            p.write_text(json.dumps(obj))
            self.assertEqual(b.load_lock(p)['bclone']['commit'],'b'*40)

    def test_git_checkout_exact_detached_clean_and_official_origin(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)
            subprocess.run(['git','init','-q',str(p)],check=True)
            subprocess.run(['git','-C',str(p),'config','user.name','test'],check=True)
            subprocess.run(['git','-C',str(p),'config','user.email','test@example.invalid'],check=True)
            subprocess.run(['git','-C',str(p),'remote','add','origin',
                            'https://github.com/'+b.BCLONE_REPO+'.git'],check=True)
            (p/'go.mod').write_text('module example.invalid/test\n\ngo 1.24\n')
            (p/'go.sum').write_text('fixture\n')
            subprocess.run(['git','-C',str(p),'add','go.mod','go.sum'],check=True)
            subprocess.run(['git','-C',str(p),'commit','-qm','fixture'],check=True)
            head=b.command(['git','rev-parse','HEAD'],cwd=p)
            with self.assertRaisesRegex(b.Rejected,'detached'):b.verify_checkout(p,head)
            subprocess.run(['git','-C',str(p),'checkout','--detach','-q'],check=True)
            self.assertEqual(len(b.verify_checkout(p,head)),2)
            (p/'scratch').write_text('untracked')
            with self.assertRaisesRegex(b.Rejected,'dirty'):b.verify_checkout(p,head)
            (p/'scratch').unlink()
            subprocess.run(['git','-C',str(p),'remote','set-url','origin','https://evil.invalid/x.git'],check=True)
            with self.assertRaisesRegex(b.Rejected,'origin'):b.verify_checkout(p,head)

    def test_elf_checks_fail_closed_on_linker_or_unshipped_shared_library(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'rclone';p.write_bytes(elf())
            readelf=Path(t)/'llvm-readelf'
            def fake(argv,**kw):
                if argv[1]=='-h':return 'Class: ELF64\nMachine: AArch64'
                if argv[1]=='-l':return '[Requesting program interpreter: /system/bin/linker64]'
                return 'Shared library: [libc.so]'
            with patch.object(b,'command',side_effect=fake):
                self.assertEqual(b.inspect_elf(p,readelf)['needed'],['libc.so'])
            def evil(argv,**kw):
                if argv[1]=='-h':return 'Class: ELF64\nMachine: AArch64'
                if argv[1]=='-l':return '[Requesting program interpreter: /linux/ld-linux-aarch64.so.1]'
                return 'Shared library: [libfuse3.so]'
            with patch.object(b,'command',side_effect=evil),self.assertRaises(b.Rejected):
                b.inspect_elf(p,readelf)
            def bad_lib(argv,**kw):
                if argv[1]=='-h':return 'ELF64 AArch64'
                if argv[1]=='-l':return ''
                return 'Shared library: [libfuse3.so]'
            with patch.object(b,'command',side_effect=bad_lib),self.assertRaisesRegex(b.Rejected,'shared library'):
                b.inspect_elf(p,readelf)

    def test_synthetic_go_build_repeatable_and_rejects_provenance_tamper(self):
        # In-memory fakes only exercise invariant wiring; NOT toolchain/device evidence.
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);checkout=p/'source';checkout.mkdir()
            (checkout/'go.mod').write_text('module example.invalid/test\n')
            (checkout/'go.sum').write_text('example checksum\n')
            cc=p/'clang';cc.write_bytes(b'fake-compiler-for-unit-test')
            ndk=p/'ndk';ndk.mkdir()
            lock=p/'source.lock.json';lock.write_text(json.dumps(pins()))
            def cmd(argv,**kwargs):
                if argv[:2] == ['go','list']: return 'example.invalid/test\nmodule@v0.1.0'
                if argv[:2] == ['go','build']:
                    Path(argv[argv.index('-o')+1]).write_bytes(elf())
                    return ''
                if argv[:2] == ['git','status']: return ''
                raise AssertionError('unexpected command: '+str(argv))
            proof={'format':'ELF64','machine':'AArch64','abi':'arm64-v8a',
                   'interpreter':'/system/bin/linker64','needed':['libc.so']}
            with patch.object(b,'verify_checkout',return_value=(b.filehash(checkout/'go.mod'),b.filehash(checkout/'go.sum'))), \
                 patch.object(b,'verify_toolchain',return_value=(cc,cc,'clang pinned fixture')), \
                 patch.object(b,'inspect_elf',return_value=proof),patch.object(b,'command',side_effect=cmd):
                a=b.build(checkout,ndk,p/'run1',lock)
                z=b.build(checkout,ndk,p/'run2',lock)
            self.assertEqual(a,z)
            self.assertEqual(b.compare(p/'run1',p/'run2')['status'],'BYTE_IDENTICAL_UNATTESTED')
            (p/'run2'/'rclone').write_bytes(b'tampered')
            with self.assertRaises(b.Rejected):b.compare(p/'run1',p/'run2')
            with self.assertRaises(b.Rejected):b.compare(p/'run1',p/'run1')

    def test_source_automation_has_separate_lanes_no_mutable_source(self):
        txt=(ROOT/'.github/workflows/skybind-provider-reproducibility.yml').read_text()
        self.assertIn('lane: [A, B]',txt)
        self.assertIn('workflow_dispatch:',txt)
        self.assertNotIn('schedule:',txt)
        self.assertNotIn('release create',txt)
        self.assertNotIn('latest-stable',txt)
        self.assertIn('checkout --detach',txt)
        self.assertIn('source_build.py compare',txt)
        self.assertIn('source_build.py verify-newfuture',txt)
        self.assertIn('cache: false',txt)
        data=tomllib.loads((ROOT/'.devtool.toml').read_text())
        self.assertEqual(data['wrapper']['commands']['q02-provider-build-contract']['target'],'skybind')
        self.assertIn('q02-provider-source-contract',data['targets']['skybind']['workflows'])

    def test_newfuture_pinned_archive_and_elf_inspection_do_not_attest(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); z=root/'magisk-rclone_arm64-v8a.zip'
            with zipfile.ZipFile(z,'w') as archive:
                for name in ('system/vendor/bin/rclone','system/vendor/bin/fusermount3'):
                    info=zipfile.ZipInfo(name);info.create_system=3
                    info.external_attr=(stat.S_IFREG|0o755)<<16
                    archive.writestr(info,elf())
            obj=pins();obj['newfuture']['archive_sha256']=b.filehash(z)
            lock=root/'source.lock.json';lock.write_text(json.dumps(obj))
            with patch.object(b,'verify_toolchain',return_value=(root/'clang',root/'readelf','clang')), \
                 patch.object(b,'inspect_elf',return_value={'abi':'arm64-v8a'}):
                result=b.verify_newfuture(z,root,lock)
                self.assertEqual(result['status'],'PIN_MATCH_UNATTESTED')
                self.assertFalse(result['static_fuse_runtime_qualified'])
                self.assertEqual(len(result['files']),2)
                z.write_bytes(z.read_bytes()+b'tamper')
                with self.assertRaises(b.Rejected):b.verify_newfuture(z,root,lock)

    def test_compare_rejects_packaged_runtime_or_helper_substitution(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            # Construct synthetic local-only lane outputs, never used for a gate receipt.
            def lane(name):
                p=root/name;p.mkdir()
                binary=p/'rclone';binary.write_bytes(elf())
                record={'schema_version':1,'qualification':'UNATTESTED_SOURCE_BUILD',
                        'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED','provider':'bclone',
                        'binary_name':'rclone','source_commit':'b'*40,'lock_sha256':'a'*64,
                        'goos':'android','goarch':'arm64','go_version':b.PIN_GO,
                        'ndk_revision':b.PIN_NDK,'android_api':b.API_LEVEL,
                        'binary_sha256':b.filehash(binary),'binary_size':binary.stat().st_size}
                (p/'provenance.json').write_bytes(b.canonical(record))
                (p/'SHA256SUMS').write_text(f"{b.filehash(binary)}  rclone\n{b.filehash(p/'provenance.json')}  provenance.json\n")
                return p
            x,y=lane('x'),lane('y')
            for lane_dir in (x,y):
                packages=root/(lane_dir.name+'-packages');packages.mkdir()
                for provider in ('bclone','newfuture'):
                    with zipfile.ZipFile(packages/(provider+'.zip'),'w') as archive:
                        archive.writestr('system/bin/rclone',elf())
                        archive.writestr('system/vendor/bin/fusermount3',elf())
                        archive.writestr('runtime.provenance.json',json.dumps({
                            'provider':provider,'bclone':{'commit':'b'*40}}))
            def checked(argv,**kw):
                self.assertEqual(argv[2],'verify')
                return 'synthetic output checked by fixture'
            with patch.object(b,'command',side_effect=checked):
                result=b.compare(x,y,root/'x-packages',root/'y-packages')
                self.assertEqual(result['status'],'BYTE_IDENTICAL_UNATTESTED')
                # Tamper exactly one bclone package runtime, with fake verifier mocked.
                with zipfile.ZipFile(root/'y-packages/bclone.zip','w') as archive:
                    archive.writestr('system/bin/rclone',b'wrong-runtime')
                    archive.writestr('system/vendor/bin/fusermount3',elf())
                    archive.writestr('runtime.provenance.json',json.dumps({
                        'provider':'bclone','bclone':{'commit':'b'*40}}))
                with self.assertRaisesRegex(b.Rejected,'packaged bclone differs'):
                    b.compare(x,y,root/'x-packages',root/'y-packages')

    def test_package_builder_delegated_no_old_ambient_compilation(self):
        txt=(ROOT/'scripts/dev/runtime/skybind_runtime.py').read_text()
        start=txt.index('def build_bclone(');end=txt.index('def provenance(',start)
        impl=txt[start:end]
        self.assertIn('source_build.py',impl)
        self.assertNotIn('go\',\'build',impl)
        self.assertIn("lock_path)",txt)

if __name__=='__main__':unittest.main()
