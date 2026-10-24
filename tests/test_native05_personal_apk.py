"""Fail-closed NATIVE-05 pair/signer/version/download/install source-level acceptance."""
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts/dev/android'))
import personal_apk as p
import personal_apk_device as d

PIN = 'a' * 64
SHA = 'b' * 40

def artifact(name, package, version=8, *, debuggable=False, permissions=None, signer=PIN, instrument=False):
    return dict(name=name, package=package, min_sdk=26, target_sdk=35, version_code=version,
                version_name=f'0.2.0-personal.{version}',
                permissions=sorted(p.ALLOWED_PERMISSIONS if permissions is None and package == p.APP else
                                   ([] if permissions is None else permissions)),
                certificate_sha256=signer, debuggable=debuggable,
                instrumentation_for_app=instrument,
                sha256=('c' if package == p.APP else 'd') * 64,
                size_bytes=100)

def pair():
    return artifact(p.APP_FILE, p.APP), artifact(p.TEST_FILE, p.TEST, instrument=True)

class PersonalApkTests(unittest.TestCase):
    def test_correct_pair_passes(self):
        a, t = pair()
        p.assert_pair(a, t, version=8)

    def test_wrong_signer_version_debuggable_permissions_and_target_rejected(self):
        for field, value, which in [
            ('certificate_sha256', 'e'*64, 'test'),
            ('version_code', -1, 'test'),
            ('version_name', '0.1.0-dev', 'app'),
            ('package', 'other.pkg', 'app'),
            ('target_sdk', 29, 'app'),
            ('permissions', ['android.permission.INTERNET'], 'app'),
            ('debuggable', True, 'app'),
            ('instrumentation_for_app', False, 'test'),
        ]:
            with self.subTest(field=field):
                a, t = pair()
                (a if which == 'app' else t)[field] = value
                with self.assertRaises(p.CandidateError):
                    p.assert_pair(a, t, version=8)

    def test_androidtest_variant_version_can_differ(self):
        a,t = pair()
        t['version_code'] = 1
        t['version_name'] = '1.0'
        p.assert_pair(a,t,version=8)

    def test_aapt_androidtest_empty_or_missing_version_name_is_valid(self):
        fixtures = (
            "package: name='io.github.mikeyphw.skybind.test' versionCode='1' versionName='' platformBuildVersionCode='35'",
            "package: name='io.github.mikeyphw.skybind.test' versionCode='1' platformBuildVersionCode='35'",
            "package: versionCode='1' name='io.github.mikeyphw.skybind.test' versionName=''",
        )
        for line in fixtures:
            with self.subTest(line=line):
                package, version, version_name = p.parse_compiled_package_line(line)
                self.assertEqual((package, version, version_name), (p.TEST, 1, ''))
                app, test = pair()
                test.update(package=package, version_code=version, version_name=version_name)
                p.assert_pair(app, test, version=8)

    def test_aapt_package_missing_or_malformed_identity_still_refused(self):
        fixtures = (
            '', 'application: label=Skybind',
            "package: name='io.github.mikeyphw.skybind.test' versionName=''",
            "package: name='io.github.mikeyphw.skybind.test' versionCode='garbage'",
            "package: name='io.github.mikeyphw.skybind.test' versionCode='1' versionCode='2'",
            "package: name='io.github.mikeyphw.skybind.test' versionCode='1'\npackage: name='other' versionCode='1'",
        )
        for line in fixtures:
            with self.subTest(line=line):
                with self.assertRaises(p.CandidateError):
                    p.parse_compiled_package_line(line)

    def test_aapt_dump_full_pair_read_and_guarded_version_checks(self):
        appbadging = ("package: name='io.github.mikeyphw.skybind' versionCode='8' "
                      "versionName='0.2.0-personal.8'\nsdkVersion:'26'\ntargetSdkVersion:'35'")
        testbadging = ("package: name='io.github.mikeyphw.skybind.test' "
                       "versionCode='1' versionName=''\nsdkVersion:'26'\ntargetSdkVersion:'35'\n"
                       "instrumentation: name='androidx.test.runner.AndroidJUnitRunner' "
                       "targetPackage='io.github.mikeyphw.skybind'")
        with tempfile.TemporaryDirectory() as dname:
            apppath=pathlib.Path(dname)/p.APP_FILE
            testpath=pathlib.Path(dname)/p.TEST_FILE
            apppath.write_bytes(b'app')
            testpath.write_bytes(b'test')
            def fake_aapt(args, **kw):
                if args[2]=='badging':
                    return appbadging if args[-1]==str(apppath) else testbadging
                if args[2]=='xmltree':
                    return ("E: manifest (line=1)\n"
                            '  A: package="io.github.mikeyphw.skybind.test"\n'
                            '  A: android:versionCode(0x0101021b)=(type 0x10)0x1\n'
                            '  E: uses-sdk (line=2)\n'
                            '    A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                            '    A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n'
                            '  E: instrumentation (line=3)\n'
                            '    A: android:targetPackage="io.github.mikeyphw.skybind"\n')
                if args[2]=='permissions':
                    if args[-1]==str(apppath):
                        return '\n'.join("uses-permission: name='"+v+"'" for v in sorted(p.ALLOWED_PERMISSIONS))
                    return ''
                self.fail('unexpected aapt invocation')
            with patch.object(p, 'aapt_bin', return_value='/tools/aapt'), \
                 patch.object(p, 'run_checked', side_effect=fake_aapt):
                app=p.package_identity(apppath)
                test=p.package_identity(testpath)
            self.assertEqual(test['version_name'], '')
            self.assertTrue(test['instrumentation_for_app'])
            # aapt returns package properties; apksigner adds the checked cert.
            app['certificate_sha256'] = PIN
            test['certificate_sha256'] = PIN
            p.assert_pair(app,test,version=8)
            with self.assertRaises(p.CandidateError):
                p.assert_pair({**app, 'version_name':'0.1.0-dev'},test,version=8)
            with self.assertRaises(p.CandidateError):
                p.assert_pair(app,{**test,'instrumentation_for_app':False},version=8)

    def test_compiled_manifest_identity_fallback_and_strict_malformed_rejection(self):
        tree = ("N: android=http://schemas.android.com/apk/res/android\n"
                "  E: manifest (line=2)\n"
                '    A: android:versionCode(0x0101021b)=(type 0x10)0x0\n'
                '    A: package="io.github.mikeyphw.skybind.test" (Raw: "io.github.mikeyphw.skybind.test")\n'
                '    E: uses-sdk (line=3)\n'
                '      A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                '      A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n'
                '    E: instrumentation (line=4)\n'
                '      A: android:targetPackage(0x01010021)="io.github.mikeyphw.skybind" (Raw: "io.github.mikeyphw.skybind")\n')
        info = p.parse_compiled_manifest_tree(tree)
        self.assertEqual(info['package'], p.TEST)
        self.assertEqual(info['version_code'], 0)
        self.assertEqual(info['version_name'], '')
        self.assertTrue(info['instrumentation_for_app'])
        with tempfile.TemporaryDirectory() as dname:
            apk = pathlib.Path(dname) / p.TEST_FILE
            apk.write_bytes(b'apk fixture')
            def fake_aapt(args, **kw):
                if args[2] == 'badging':
                    return 'application: label=AndroidJUnitRunner\n'
                if args[2] == 'xmltree':
                    self.assertEqual(args[-1], 'AndroidManifest.xml')
                    return tree
                if args[2] == 'permissions':
                    return ''
                self.fail('unexpected invocation')
            with patch.object(p, 'aapt_bin', return_value='/tools/aapt'), \
                 patch.object(p, 'run_checked', side_effect=fake_aapt):
                self.assertEqual(p.package_identity(apk)['package'], p.TEST)
        for malformed in [
            tree.replace('A: package=', 'A: wrongpackage='),
            tree.replace('versionCode(0x0101021b)', 'versionCode(0x0101021b)')
                .replace('=(type 0x10)0x0', '="notanumber"'),
            tree.replace('A: package=', 'A: package="evil"\n    A: package='),
            tree.replace('targetSdkVersion(0x01010270)', 'unknownField(0x01010270)'),
        ]:
            with self.subTest(malformed=malformed[:50]):
                with self.assertRaises(p.CandidateError):
                    p.parse_compiled_manifest_tree(malformed)

    def test_androidtest_manifest_without_version_code_uses_explicit_null(self):
        tree = ('E: manifest (line=1)\n'
                '  A: package="io.github.mikeyphw.skybind.test" (Raw: "io.github.mikeyphw.skybind.test")\n'
                '  E: uses-sdk (line=2)\n'
                '    A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                '    A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n'
                '  E: instrumentation (line=3)\n'
                '    A: android:targetPackage(0x01010021)="io.github.mikeyphw.skybind"\n')
        doc = p.parse_compiled_manifest_tree(tree, android_test=True)
        self.assertIsNone(doc['version_code'])
        self.assertEqual(doc['package'], p.TEST)
        self.assertTrue(doc['instrumentation_for_app'])
        app,test = pair()
        test['version_code'] = doc['version_code']
        test['version_name'] = doc['version_name']
        p.assert_pair(app,test,version=8)
        with self.assertRaisesRegex(p.CandidateError,'COMPILED_MANIFEST_VERSION_CODE_INVALID'):
            p.parse_compiled_manifest_tree(tree, android_test=False)
        for malformed in [
            tree.replace('A: package=', 'A: omittedPackage='),
            tree.replace('io.github.mikeyphw.skybind"', 'evil.target"'),
        ]:
            with self.subTest(malformed=malformed[:60]):
                try:
                    obj=p.parse_compiled_manifest_tree(malformed,android_test=True)
                except p.CandidateError:
                    continue
                test.update(package=obj['package'],instrumentation_for_app=obj['instrumentation_for_app'])
                with self.assertRaises(p.CandidateError):
                    p.assert_pair(app,test,version=8)

    def test_androidtest_badging_optional_code_parses_but_malformed_does_not(self):
        sample="package: name='io.github.mikeyphw.skybind.test' versionName=''"
        with self.assertRaises(p.CandidateError):
            p.parse_compiled_package_line(sample)
        self.assertEqual(p.parse_compiled_package_line(sample,android_test=True), (p.TEST,None,''))
        for bad in [sample+" versionCode='abc'", sample+" name='other'",sample+" versionCode='-1'"]:
            with self.subTest(bad=bad):
                with self.assertRaises(p.CandidateError):
                    p.parse_compiled_package_line(bad,android_test=True)

    def test_real_hosted_shape_blank_versioncode_badging_and_versionless_binary(self):
        """The 40109002928 diagnostics showed binary versionCode absent."""
        badging = ("package: name='io.github.mikeyphw.skybind.test' "
                   "versionCode='' versionName=''\n"
                   "sdkVersion:'26'\ntargetSdkVersion:'35'\n"
                   "instrumentation: name='androidx.test.runner.AndroidJUnitRunner' "
                   "targetPackage='io.github.mikeyphw.skybind'")
        tree = ('E: manifest (line=1)\n'
                '  A: package="io.github.mikeyphw.skybind.test"\n'
                '  E: uses-sdk (line=2)\n'
                '    A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                '    A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n'
                '  E: instrumentation (line=3)\n'
                '    A: android:targetPackage="io.github.mikeyphw.skybind"\n')
        self.assertEqual(p.parse_compiled_package_line(badging,android_test=True),
                         (p.TEST,None,''))
        with self.assertRaisesRegex(p.CandidateError, 'COMPILED_PACKAGE_IDENTITY_UNAVAILABLE'):
            p.parse_compiled_package_line(badging,android_test=False)
        with tempfile.TemporaryDirectory() as dname:
            apk = pathlib.Path(dname)/p.TEST_FILE
            apk.write_bytes(b'bounded compiled fixture')
            def fake_aapt(args, **kw):
                if args[2] == 'badging': return badging
                if args[2] == 'xmltree': return tree
                if args[2] == 'permissions': return ''
                self.fail('unexpected SDK command')
            with patch.object(p,'aapt_bin',return_value='/sdk/build-tools/35.0.0/aapt'), \
                 patch.object(p,'run_checked',side_effect=fake_aapt):
                test = p.package_identity(apk)
            self.assertEqual(test['package'], p.TEST)
            self.assertEqual(test['min_sdk'],26)
            self.assertIsNone(test['version_code'])
            self.assertEqual(test['version_name'],'')
            self.assertTrue(test['instrumentation_for_app'])
            app,_=pair()
            test['certificate_sha256']=app['certificate_sha256']
            p.assert_pair(app,test,version=8)
            # The same binary rejects contradictory badging without treating
            # it as a missing optional version or silently skipping xmltree.
            for fragment in ("versionCode='3'", "name='evil.test' versionCode=''",
                             "versionCode='bogus'","versionCode='' versionCode='0'"):
                changed=badging.replace("versionCode=''", fragment, 1)
                with self.subTest(fragment=fragment):
                    with patch.object(p,'aapt_bin',return_value='/sdk/aapt'), \
                         patch.object(p,'run_checked',side_effect=lambda args,**kw:
                           changed if args[2]=='badging' else tree if args[2]=='xmltree' else ''):
                        with self.assertRaises(p.CandidateError):
                            p.package_identity(apk)
            # Synthetic badging 0 is reconciled only with an absent XML code;
            # the metadata receipt remains explicit null, never invented 0.
            with patch.object(p,'aapt_bin',return_value='/sdk/aapt'), \
                 patch.object(p,'run_checked',side_effect=lambda args,**kw:
                   badging.replace("versionCode=''", "versionCode='0'")
                   if args[2]=='badging' else tree if args[2]=='xmltree' else ''):
                self.assertIsNone(p.package_identity(apk)['version_code'])

    def test_blank_version_for_app_and_malformed_present_test_are_rejected(self):
        for line in ("package: name='io.github.mikeyphw.skybind' versionCode='' versionName='0.2.0-personal.2'",
                     "package: name='io.github.mikeyphw.skybind.test' versionCode='broken'",
                     "package: name='io.github.mikeyphw.skybind.test' versionCode=-1",
                     "package: name='io.github.mikeyphw.skybind.test' versionCode='' name='evil'"):
            with self.subTest(line=line):
                with self.assertRaises(p.CandidateError):
                    p.parse_compiled_package_line(line,android_test=line.find('.test')>=0)

    def test_generated_test_manifest_missing_version_code_still_full_package_check(self):
        tree = ('E: manifest (line=1)\n'
                '  A: package="io.github.mikeyphw.skybind.test"\n'
                '  E: uses-sdk (line=2)\n'
                '    A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                '    A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n'
                '  E: instrumentation (line=3)\n'
                '    A: android:targetPackage(0x01010021)="io.github.mikeyphw.skybind"\n')
        with tempfile.TemporaryDirectory() as dname:
            apk = pathlib.Path(dname) / p.TEST_FILE
            apk.write_bytes(b'compiled-fixture')
            def fake_aapt(args,**kw):
                if args[2]=='badging': return 'application: label=AndroidJUnitRunner\n'
                if args[2]=='xmltree': return tree
                if args[2]=='permissions': return ''
                self.fail('unexpected invocation')
            with patch.object(p,'aapt_bin',return_value='/sdk/build-tools/35.0.0/aapt'), \
                 patch.object(p,'run_checked',side_effect=fake_aapt):
                meta=p.package_identity(apk)
            self.assertEqual(meta['package'],p.TEST)
            self.assertIsNone(meta['version_code'])
            self.assertTrue(meta['instrumentation_for_app'])

    def test_public_diagnostics_classifies_blank_test_version_without_values(self):
        import personal_apk_diagnostics as diag
        with tempfile.TemporaryDirectory() as tmp:
            apk = pathlib.Path(tmp)/p.TEST_FILE
            apk.write_bytes(b'fixture')
            def fake_run(argv,**kw):
                stdout = ("package: name='io.github.mikeyphw.skybind.test' versionCode='' versionName=''\n"
                          if argv[2] == 'badging' else '')
                return type('P',(),{'stdout':stdout,'stderr':'', 'returncode':0})()
            with patch.object(diag.subprocess,'run',side_effect=fake_run):
                result=diag.examine(apk, '/sdk/aapt')
            self.assertEqual(result['badging']['package_line_count'],1)
            self.assertEqual(result['badging']['package_attribute_state'],
                             {'name':'present','versionCode':'empty','versionName':'empty'})
            self.assertNotIn(p.TEST,json.dumps(result))

    def test_safe_diagnostics_resolves_same_aapt_as_verifier(self):
        import personal_apk_diagnostics as diag
        with tempfile.TemporaryDirectory() as dname:
            apk=pathlib.Path(dname)/p.TEST_FILE
            apk.write_bytes(b'test')
            ran=[]
            def fake_process(argv,**kw):
                ran.append(argv)
                return type('Proc',(),{'returncode':0,'stdout':(
                    'E: manifest (line=1)\n  A: package="io.github.mikeyphw.skybind.test"\n'
                    '  E: instrumentation (line=2)\n    A: android:targetPackage="io.github.mikeyphw.skybind"\n'),
                    'stderr':'private-hypothetical-content'})()
            with patch.object(diag.subprocess,'run',side_effect=fake_process):
                result=diag.examine(apk,'/sdk/build-tools/35.0.0/aapt')
            self.assertTrue(all(argv[0]=='/sdk/build-tools/35.0.0/aapt' for argv in ran))
            self.assertIn('package',result['xmltree']['fields'])
            self.assertNotIn('private-hypothetical-content',json.dumps(result))

    def test_badging_xmltree_disagreement_is_rejected(self):
        tree = ('E: manifest (line=1)\n'
                '  A: package="evil.app" (Raw: "evil.app")\n'
                '  A: android:versionCode(0x0101021b)=(type 0x10)0x1\n'
                '  E: uses-sdk (line=2)\n'
                '    A: android:minSdkVersion(0x0101020c)=(type 0x10)0x1a\n'
                '    A: android:targetSdkVersion(0x01010270)=(type 0x10)0x23\n')
        with tempfile.TemporaryDirectory() as tmp:
            apk = pathlib.Path(tmp) / p.TEST_FILE
            apk.write_bytes(b'test')
            with patch.object(p, 'aapt_bin', return_value='/tools/aapt'), \
                 patch.object(p, 'run_checked', side_effect=lambda args, **kwargs:
                         ("package: name='io.github.mikeyphw.skybind.test' versionCode='1' versionName=''\nsdkVersion:'26'\ntargetSdkVersion:'35'"
                          if args[2]=='badging' else tree)):
                with self.assertRaises(p.CandidateError):
                    p.package_identity(apk)

    def test_androidtest_version_zero_never_qualifies_main_app(self):
        a, t = pair()
        t['version_code'] = 0
        t['version_name'] = ''
        p.assert_pair(a, t, version=8)
        with self.assertRaises(p.CandidateError):
            p.assert_pair({**a, 'version_code':0}, t, version=8)

    def test_invalid_version_rejected(self):
        for version in (0, 1, 2100000001):
            a,t = pair()
            with self.assertRaises(p.CandidateError):
                p.assert_pair(a,t,version=version)

    def test_hosted_source_identity_requires_main_dispatch(self):
        env = {'GITHUB_ACTIONS':'true','GITHUB_REPOSITORY':p.REPO,
               'GITHUB_REF':'refs/heads/main','GITHUB_EVENT_NAME':'workflow_dispatch',
               'GITHUB_SHA':SHA,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'1'}
        self.assertEqual(p.github_identity(env)['run_id'],123)
        for attr, bad in [('GITHUB_REF','refs/heads/test'),('GITHUB_EVENT_NAME','pull_request'),
                          ('GITHUB_SHA','invalid'),('GITHUB_REPOSITORY','attacker/fork')]:
            with self.subTest(attr=attr):
                with self.assertRaises(p.CandidateError):
                    p.github_identity({**env,attr:bad})

    def test_manifest_bindings_reject_all_drift(self):
        a,t = pair()
        doc = {'schema_version':1,'status':'PERSONAL_APK_CANDIDATE_ONLY',
               'release_qualified':False,'device_qualified':False,'owner_approved':False,
               'independent_attestation':False,'repository':p.REPO,'ref':'refs/heads/main',
               'workflow':'Skybind Personal APK (candidate only)', 'source_sha':SHA,'run_id':123,
               'signing_certificate_pin_sha256':PIN,'channel':'personal',
               'build_type':'personal','test_build_type':'personal',
               'signing_key_role':'existing-persistent-development-key',
               'requested_version_code':8,'permission_inventory':sorted(p.ALLOWED_PERMISSIONS),
               'capability_source_sha256':{'android-app/x':'f'*64},'app':a,'test_apk':t}
        with patch.object(p,'file_record',side_effect=[a,t]):
            self.assertFalse(p.verify_manifest(doc,None,None,expected_sha=SHA,
                               expected_run=123,expected_pin=PIN)['release_qualified'])
        for key,value in [('release_qualified',True),('device_qualified',True),('owner_approved',True),
                          ('requested_version_code',7),('source_sha','other'),('run_id',9),
                          ('signing_certificate_pin_sha256','e'*64),('permission_inventory',[])]:
            with self.subTest(key=key):
                with patch.object(p,'file_record',side_effect=[a,t]):
                    with self.assertRaises(p.CandidateError):
                        p.verify_manifest({**doc,key:value},None,None,
                                          expected_sha=SHA,expected_run=123,expected_pin=PIN)
        with patch.object(p,'file_record',side_effect=[a,{**t,'sha256':'e'*64}]):
            with self.assertRaises(p.CandidateError):
                p.verify_manifest(doc,None,None)

    def test_bad_signer_pin_and_live_trust_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(pathlib.Path,'home',return_value=pathlib.Path(tmp)):
                with self.assertRaises(p.CandidateError):
                    d.pin_from_owner(None)
            with self.assertRaises(p.CandidateError):
                d.pin_from_owner('wrongpin')

    def test_install_preflight_no_data_loss_or_wrong_cert(self):
        a, t = pair()
        source = {'app':a,'test_apk':t}
        def make_record(which):
            return a if which == p.APP else t
        with patch.object(d, 'pull_record', side_effect=lambda serial,pkg,tmp: make_record(pkg)):
            state = d.inspect_installed('serial',source,PIN)
            self.assertEqual(state['state'],'ALREADY_INSTALLED_IDENTICAL_PAIR')
        olda={**a,'version_code':7,'sha256':'2'*64}
        oldt={**t,'version_code':7,'sha256':'3'*64}
        with patch.object(d, 'pull_record', side_effect=[olda,oldt]):
            self.assertEqual(d.inspect_installed('serial',source,PIN)['state'],
                             'SAME_SIGNER_HIGHER_VERSION_UPGRADE')
        with patch.object(d, 'pull_record', side_effect=[{**olda,'version_code':9},
                                                       {**oldt,'version_code':9}]):
            with self.assertRaises(p.CandidateError):
                d.inspect_installed('serial',source,PIN)
        with patch.object(d, 'pull_record', side_effect=[{**olda,'certificate_sha256':'e'*64},oldt]):
            with self.assertRaises(p.CandidateError):
                d.inspect_installed('serial',source,PIN)
        with patch.object(d, 'pull_record', side_effect=[olda,None]):
            with self.assertRaises(p.CandidateError):
                d.inspect_installed('serial',source,PIN)

    def test_device_dry_run_cannot_invoke_adb_install(self):
        a,t = pair()
        m={'app':a,'test_apk':t,'source_sha':SHA,'requested_version_code':8}
        with patch.object(d,'verify_folder',return_value=(m,{})),\
             patch.object(d,'inspect_installed',return_value={'state':'ABSENT','old_version':None}),\
             patch.object(d,'adb',side_effect=AssertionError('install invoked')):
            result = d.device_action(pathlib.Path('/fixture'),'serial',PIN,do_install=False,sha=SHA)
            self.assertFalse(result['installer_invoked'])
        with patch.object(d,'verify_folder',return_value=(m,{})),\
             patch.object(d,'inspect_installed',return_value={'state':'ALREADY_INSTALLED_IDENTICAL_PAIR','old_version':8}),\
             patch.object(d,'adb',side_effect=AssertionError('install invoked')):
            with self.assertRaises(p.CandidateError):
                d.device_action(pathlib.Path('/fixture'),'serial',PIN,do_install=True,sha=SHA)

    def test_failed_verifier_has_bounded_compiled_identity_diagnostics(self):
        workflow=(ROOT/'.github/workflows/skybind-personal-apk.yml').read_text()
        self.assertIn('Bounded compiled APK metadata diagnostics on verifier failure', workflow)
        self.assertIn('if: failure()', workflow)
        self.assertIn('scripts/dev/android/personal_apk_diagnostics.py', workflow)
        self.assertIn('DIAGNOSTIC_ONLY_NOT_RELEASE_QUALIFIED',
                      (ROOT/'scripts/dev/android/personal_apk_diagnostics.py').read_text())
        self.assertNotIn('cat personal-apk-evidence', workflow)

    def test_known_workflow_and_gradle_surface(self):
        workflow=(ROOT/'.github/workflows/skybind-personal-apk.yml').read_text()
        gradle=(ROOT/'android-app/app/build.gradle.kts').read_text()
        for token in ('workflow_dispatch:', 'refs/heads/main', 'ci-prepare',
                      ':app:assemblePersonalAndroidTest','skybindPersonalVersionCode',
                      'PERSONAL_APK_MANIFEST.json', 'upload-artifact@', 'always()'):
            self.assertIn(token, workflow)
        for token in ('testBuildType = if (personalRequested)', 'isDebuggable = false',
                      'EXPLICIT_MONOTONIC_PERSONAL_VERSION_CODE_REQUIRED',
                      'skybindPersistentDebug', 'personalVersion'):
            self.assertIn(token, gradle)
        self.assertNotIn('uninstall', workflow)

if __name__=='__main__':
    unittest.main()
