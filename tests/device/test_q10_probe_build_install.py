"""Q10 local contract tests. Android commands are mocked; no device claims."""
import importlib.util
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('q10', ROOT / 'scripts/devtool/skybind_app_probe.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Q10ProbeTests(unittest.TestCase):
    def test_original_app_source_locked(self):
        mod.source_check()
        self.assertEqual(len(mod.SOURCE_DIGESTS), 5)
        self.assertIn('Process.myUid()', (ROOT/'tests/device/probe-app/app/src/main/java/org/skybind/probe/ProbeActivity.java').read_text())

    def test_devtool_workflows_and_existing_device_source(self):
        obj = tomllib.loads((ROOT/'.devtool.toml').read_text())
        wrappers = obj['wrapper']['commands']
        jobs = obj['targets']['skybind_android_device']['jobs']
        workflows = obj['targets']['skybind_android_device']['workflows']
        for name, workflow in [('build-app-probe','app-probe-build'),('install-app-probe','app-probe-install'),('app-probe','app-probe-build-install')]:
            self.assertEqual(wrappers[name]['target'],'skybind_android_device')
            self.assertEqual(wrappers[name]['workflow'],workflow)
            self.assertEqual(workflows[workflow],['job:'+workflow])
            self.assertIn(workflow,jobs)
        self.assertIn('physical-app-probe',workflows)
        self.assertEqual(obj['targets']['skybind_android_device']['root'],'tests/device')

    def test_build_command_debug_only_no_network(self):
        cmd = mod.helper_command(Path('/private/helper'))
        self.assertIn(':app:assembleDebug',cmd)
        self.assertNotIn('assembleRelease',cmd)
        self.assertIn('never',cmd)
        self.assertIn('deny',cmd)
        self.assertIn('auto',cmd)
        self.assertEqual(cmd[cmd.index('--android-platform')+1],'35')

    def test_install_script_hash_staging_cleanup(self):
        s=mod.installation_script(Path('/data/data/com.termux/files/home/Code/skybind/build/app-probe/probe.apk'), 'a'*64,'b'*24)
        self.assertIn('/system/bin/pm install -r',s)
        self.assertIn('/system/bin/toybox sha256sum',s)
        self.assertIn('trap ',s)
        self.assertIn('pm list packages -U org.skybind.probe',s)
        self.assertNotIn('mount ',s)
        self.assertNotIn('chmod 777',s)
        with self.assertRaises(mod.ProbeError):
            mod.installation_script(Path('/tmp/probe.apk'),'bad','b'*24)

    def valid_zip(self,p):
        with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('AndroidManifest.xml', os.urandom(1500))
            z.writestr('classes.dex', b'dex\n'+os.urandom(1600))

    def test_apk_invalid_and_duplicate_members_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'file.apk'
            p.write_text('hello')
            with self.assertRaises(mod.ProbeError):mod.checked_apk(p)
            self.valid_zip(p)
            self.assertEqual(mod.checked_apk(p),hashlib.sha256(p.read_bytes()).hexdigest())
            p.unlink()
            p.symlink_to('/etc/passwd')
            with self.assertRaises(mod.ProbeError):mod.checked_apk(p)

    def test_receipt_checksum_and_source_binding(self):
        with tempfile.TemporaryDirectory() as folder:
            d=Path(folder)
            p=d/mod.APK_NAME
            self.valid_zip(p)
            good={'schema_version':1,'type':'SKYBIND_Q10_DEBUG_APP_BUILD','package':mod.PACKAGE,
                  'variant':'debug','apk_name':mod.APK_NAME,'apk_sha256':mod.sha(p.read_bytes()),
                  'app_source_sha256':dict(mod.SOURCE_DIGESTS),'release_seal':'NOT_ISSUED'}
            (d/'build-receipt.json').write_text(json.dumps(good))
            with mock.patch.object(mod,'OUT',d):
                self.assertEqual(mod.install_receipt()[1],good['apk_sha256'])
                p.write_bytes(p.read_bytes()+b'corruption')
                with self.assertRaises(mod.ProbeError):mod.install_receipt()
                self.valid_zip(p)
                good['apk_sha256']=mod.sha(p.read_bytes());good['app_source_sha256']['tests/device/probe-app/build.gradle']='f'*64
                (d/'build-receipt.json').write_text(json.dumps(good))
                with self.assertRaises(mod.ProbeError):mod.install_receipt()

    def test_install_rejects_non_root(self):
        with mock.patch.object(mod.os.path,'isdir',return_value=True),mock.patch.object(mod,'install_receipt',return_value=(Path('/x.apk'),'a'*64)),mock.patch.object(mod.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'not root','denied')):
            with self.assertRaises(mod.ProbeError):mod.install()

    def test_install_rejects_false_success_or_privileged_uid(self):
        root=subprocess.CompletedProcess([],0,'0\n','')
        bad=subprocess.CompletedProcess([],0,'Success\npackage:org.skybind.probe uid:0\n','')
        with mock.patch.object(mod.os.path,'isdir',return_value=True),mock.patch.object(mod,'install_receipt',return_value=(Path('/x.apk'),'a'*64)),mock.patch.object(mod.subprocess,'run',side_effect=[root,bad]):
            with self.assertRaises(mod.ProbeError):mod.install()
        good=subprocess.CompletedProcess([],0,'Success\npackage:org.skybind.probe uid:10256\n','')
        with mock.patch.object(mod.os.path,'isdir',return_value=True),mock.patch.object(mod,'install_receipt',return_value=(Path('/x.apk'),'a'*64)),mock.patch.object(mod.subprocess,'run',side_effect=[root,good]):
            mod.install()

    def test_explicit_commands_only(self):
        self.assertEqual(mod.main(['nonsense']),2)
        self.assertEqual(mod.main([]),2)

if __name__=='__main__':unittest.main()
