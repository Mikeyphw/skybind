"""SB-Q10R2 native Devtool Android project contract and receipt checks."""
import importlib.util,hashlib,json,os,subprocess,tempfile,tomllib,unittest,zipfile
from pathlib import Path
from unittest import mock
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('q10', ROOT/'scripts/devtool/skybind_app_probe.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Q10NativeTargetTests(unittest.TestCase):
    def test_native_target_matches_devtool_hud(self):
        c=tomllib.loads((ROOT/'.devtool.toml').read_text());t=c['targets']['skybind_app_probe']
        self.assertEqual(t['runner'],'android');self.assertEqual(t['platform'],'android')
        self.assertEqual(t['execution_environment'],'chroot');self.assertEqual(t['chroot_name'],'androidos')
        self.assertEqual(t['root'],'tests/device/probe-app')
        self.assertEqual(t['tasks']['build'],[':app:assembleDebug'])
        self.assertEqual(t['android']['aapt2_provider'],'auto')
        self.assertEqual(t['android']['prefer_native_termux'],False)
        self.assertEqual(t['bootstrap'],{'downloads':'missing','network':'allow'})
        self.assertEqual(t['gradle']['max_workers'],2)
        self.assertEqual(t['workflows']['app-probe-build'],['runner:android#build','job:stage'])
        self.assertEqual(t['workflows']['app-probe-build-install'],['runner:android#build','job:stage','job:install'])
        self.assertEqual(t['jobs']['stage']['execution_environment'],'native-termux')
        self.assertEqual(t['jobs']['install']['execution_environment'],'native-termux')
        for name in ('build-app-probe','app-probe','install-app-probe'):
            self.assertEqual(c['wrapper']['commands'][name]['target'],'skybind_app_probe')
        self.assertIn('physical-app-probe',c['targets']['skybind_android_device']['workflows'])
    def test_android_versions_are_hud_versions(self):
        project=ROOT/'tests/device/probe-app'
        self.assertIn("version '9.3.1'",(project/'build.gradle').read_text())
        a=(project/'app/build.gradle').read_text()
        for marker in ('compileSdk 36',"buildToolsVersion '36.0.0'",'targetSdk 36','JavaVersion.VERSION_21'):
            self.assertIn(marker,a)
        self.assertIn('VERSION=9.7.1',(project/'gradlew').read_text())
        self.assertIn('SHA256=acd53f1e',(project/'gradlew').read_text())
        self.assertIn('org.gradle.jvmargs=-Xmx1152m',(project/'gradle.properties').read_text())
    def test_source_bound(self):
        mod.source_check()
        self.assertEqual(len(mod.SOURCE_DIGESTS),5)
        self.assertIn('Process.myUid()', (ROOT/'tests/device/probe-app/app/src/main/java/org/skybind/probe/ProbeActivity.java').read_text())
    @staticmethod
    def fake_apk(path):
        with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('AndroidManifest.xml',os.urandom(1600));z.writestr('classes.dex',b'dex\n'+os.urandom(2000))
    def test_stage_produces_receipt_and_blocks_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);probe=d/'probe';native=probe/'app/build/outputs/apk/debug/app-debug.apk'
            native.parent.mkdir(parents=True);self.fake_apk(native)
            with mock.patch.object(mod,'PROBE',probe), mock.patch.object(mod,'OUT',d/'out'), mock.patch.dict(os.environ,{'PREFIX':'/data/data/com.termux/files/usr'},clear=False):
                apk=mod.stage();receipt=json.loads((d/'out/build-receipt.json').read_text())
                self.assertEqual(receipt['apk_sha256'],hashlib.sha256(apk.read_bytes()).hexdigest())
                self.assertEqual(mod.install_receipt()[0],apk)
                apk.write_bytes(b'broken')
                with self.assertRaises(mod.ProbeError):mod.install_receipt()
    def test_invalid_apk_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'bad.apk';p.write_text('bad')
            with self.assertRaises(mod.ProbeError):mod.checked_apk(p)
            p.unlink();p.symlink_to('/etc/passwd')
            with self.assertRaises(mod.ProbeError):mod.checked_apk(p)
    def test_install_script_is_bounded(self):
        s=mod.installation_script(Path('/data/adb/probe.apk'),'a'*64,'b'*24)
        self.assertIn('/system/bin/pm install -r',s)
        self.assertIn('toybox sha256sum',s)
        self.assertNotIn('chmod 777',s)
    def test_stage_not_build_helper(self):
        text=(ROOT/'scripts/devtool/skybind_app_probe.py').read_text()
        self.assertNotIn('build-apk',text)
        self.assertNotIn('android-platform',text)
        self.assertEqual(mod.main([]),2)
    def test_gate_stays_blocked(self):
        p=json.loads((ROOT/'scripts/dev/runtime/source.selection.json').read_text())
        self.assertEqual(p['gate_g01'],'BLOCKED')
        self.assertEqual(p['final_seal'],'NOT_ISSUED')
        self.assertFalse(p['independent_attestation'])
if __name__=='__main__': unittest.main()
