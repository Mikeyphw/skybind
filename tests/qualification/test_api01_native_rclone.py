"""API01 deterministic native rclone packaging and transparent config launcher."""
from pathlib import Path
import json, os, subprocess, sys, tempfile, unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts/dev/release'))
sys.path.insert(0,str(ROOT/'tests/fault'))
from test_release_faults import ReleaseFaults, rel

class NativeRcloneCLI(unittest.TestCase):
    def test_candidate_keeps_native_elf_and_launcher_separate(self):
        with tempfile.TemporaryDirectory() as td:
            runtime,binary=ReleaseFaults().setup(td)
            files,manifest=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
            self.assertTrue(rel.is_arm64_elf(files[rel.NATIVE_ENGINE]))
            self.assertFalse(rel.is_arm64_elf(files[rel.PUBLIC_LAUNCHER]))
            self.assertEqual(manifest['runtime_source_engine_sha256'],rel.sha(files[rel.NATIVE_ENGINE]))
            proof=json.loads(files['runtime.provenance.json'])
            self.assertEqual(proof['engine_path'],rel.NATIVE_ENGINE)
            self.assertIn(rel.PUBLIC_LAUNCHER,proof['files'])
            self.assertIn(rel.PUBLIC_ALIAS,proof['files'])
            self.assertEqual(files[rel.PUBLIC_LAUNCHER],files[rel.PUBLIC_ALIAS])
            out=Path(td)/'candidate.zip'
            rel.write_zip(out,files)
            self.assertEqual(rel.verify_release(out)['qualification'],'CANDIDATE_ONLY_NOT_SEALED')

    def test_tampered_wrapper_or_provider_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            runtime,binary=ReleaseFaults().setup(td)
            for target in (rel.PUBLIC_LAUNCHER,rel.PUBLIC_ALIAS,rel.NATIVE_ENGINE):
                files,_=rel.collect(runtime,binary,ROOT/'module',ROOT/'module/webroot')
                files[target]+=b'\nmalicious'
                out=Path(td)/('mutated_'+target.rsplit('/',1)[-1]+'.zip')
                rel.write_zip(out,files)
                with self.assertRaises(rel.Reject):rel.verify_release(out)

    def test_launcher_forwards_arguments_and_forces_canonical_default(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);launcher=base/'rclone';alias=base/'skybind-rclone';engine=base/'skybind-rclone-engine'
            launcher.write_bytes((ROOT/'module/rclone-launcher.sh').read_bytes())
            alias.write_bytes(launcher.read_bytes())
            engine.write_text('#!/bin/sh\nprintf "ENV=%s\\n" "$RCLONE_CONFIG"\nprintf "ARG=%s\\n" "$@"\n')
            engine.chmod(0o755)
            run=subprocess.run(['/bin/sh',str(launcher),'copy','--config','/tmp/other.conf','--','remote:x','/tmp/y'],
               env={**os.environ,'RCLONE_CONFIG':'/tmp/hostile.conf'},text=True,capture_output=True,timeout=3)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('ENV=/data/adb/skybind/config/rclone.conf',run.stdout)
            using_alias=subprocess.run(['/bin/sh',str(alias),'serve','restic','--stdio'],
                env={**os.environ,'RCLONE_CONFIG':'/tmp/hostile.conf'},text=True,capture_output=True,timeout=3)
            self.assertEqual(using_alias.returncode,0,using_alias.stderr)
            self.assertIn('ARG=serve',using_alias.stdout)
            self.assertIn('ARG=restic',using_alias.stdout)
            self.assertIn('ARG=--stdio',using_alias.stdout)
            for arg in ('copy','--config','/tmp/other.conf','--','remote:x','/tmp/y'):
                self.assertIn('ARG='+arg,run.stdout)
            engine.unlink()
            bad=subprocess.run(['/bin/sh',str(launcher),'version'],text=True,capture_output=True,timeout=3)
            self.assertEqual(bad.returncode,127)
            self.assertNotIn('/data/adb/skybind/config/rclone.conf',bad.stderr)

if __name__=='__main__':unittest.main()
