#!/usr/bin/env python3
"""Source-only NATIVE-05 safety gate. Does not compile Android or promote release."""
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[3]

class GateError(Exception): pass

def need(value, code):
    if not value: raise GateError(code)

def verify(root=ROOT):
    def source(name):
        p=root/name
        need(p.is_file() and not p.is_symlink(), 'SOURCE_MISSING:'+name)
        return p.read_text()
    gradle=source('android-app/app/build.gradle.kts')
    hosted=source('.github/workflows/skybind-personal-apk.yml')
    signing=source('scripts/dev/android/stable_signing.py')
    impl=source('scripts/dev/android/personal_apk.py')
    device=source('scripts/dev/android/personal_apk_device.py')
    native=source('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/R1AuthorityService.kt')
    need('require(personalRequested || personalVersionArg == null)' in gradle and
         'EXPLICIT_MONOTONIC_PERSONAL_VERSION_CODE_REQUIRED' in gradle and
         'isDebuggable = false' in gradle and
         'testBuildType = if (personalRequested) "personal" else "debug"' in gradle and
         'signingConfig = signingConfigs.getByName("skybindPersistentDebug")' in gradle and
         'applicationId = "io.github.mikeyphw.skybind"' in gradle,
         'PERSONAL_BUILD_TYPE_OR_SIGNING_IDENTITY_UNSAFE')
    need("'SKYBIND_ANDROID_SIGNER_SHA256'" in signing and
         'SIGNING_KEY_ROTATION_REFUSED' in signing and
         'STABLE_SIGNER_FINGERPRINT_MISMATCH' in signing,
         'PERSISTENT_SIGNER_FAIL_CLOSED_CONTRACT_MISSING')
    for phrase in ('workflow_dispatch:', "github.ref == 'refs/heads/main'", 'stable_signing.py ci-prepare',
                   ':app:assemblePersonal', ':app:assemblePersonalAndroidTest',
                   'personal_apk.py create', 'personal_apk.py verify',
                   'upload-artifact@', 'SKYBIND_ANDROID_SIGNER_SHA256',
                   'if: always()', 'retention-days:'):
        need(phrase in hosted, 'HOSTED_PERSONAL_APK_POLICY_MISSING:'+phrase)
    need('def parse_compiled_package_line(' in impl and
         'COMPILED_PACKAGE_ATTRIBUTES_AMBIGUOUS' in impl and
         "fields.get('versionName', '')" in impl and
         'COMPILED_PACKAGE_IDENTITY_UNAVAILABLE' in impl,
         'HOSTED_AAPT_ANDROIDTEST_METADATA_PARSER_MISSING')
    for code in ('COMPILED_PERMISSION_DRIFT', 'DEBUGGABLE_PERSONAL_APP_REFUSED',
                 'APK_TEST_SIGNER_DRIFT', 'ANDROIDTEST_TARGET_ID_MISMATCH',
                 'GITHUB_IDENTITY_INVALID', 'MANIFEST_OVERCLAIMS_QUALIFICATION',
                 'EXPECTED_SOURCE_MISMATCH', 'TRUSTED_LOCAL_SIGNER_PIN_MISMATCH'):
        need(code in impl, 'HOSTED_MANIFEST_VERIFIER_GUARD_MISSING:'+code)
    for code in ('DOWNGRADE_OR_SAME_VERSION_REPLACEMENT_REFUSED',
                 'INSTALLED_SIGNER_MISMATCH', 'PARTIAL_INSTALLED_APP_TEST_PAIR',
                 'POST_INSTALL_PAIR_MISMATCH', 'INSTALL_REQUIRES_ABSENT_OR_STRICTLY_NEWER_PAIR',
                 'HOSTED_RUN_UNTRUSTED_OR_INCOMPLETE'):
        need(code in device, 'DEVICE_UPGRADE_GUARD_MISSING:'+code)
    need("device.add_argument('--install', action='store_true'" in device and
         "if not do_install:" in device and
         "adb(serial, 'install', '-r'," in device and
         all(token not in device for token in ("adb(serial, 'uninstall'", "'pm', 'clear'", "'install', '-d'")),
         'INSTALL_MUST_BE_OPT_IN_AND_NONDESTRUCTIVE')
    root_manifest=ET.fromstring(source('android-app/app/src/main/AndroidManifest.xml'))
    android='{http://schemas.android.com/apk/res/android}'
    app=root_manifest.find('application')
    need(app is not None and app.attrib.get(android+'label')=='@string/app_name' and
         app.attrib.get(android+'icon')=='@mipmap/ic_launcher', 'APP_BRANDING_MISSING')
    strings=ET.fromstring(source('android-app/app/src/main/res/values/strings.xml'))
    need(any(tag.attrib.get('name')=='app_name' and tag.text=='Skybind' for tag in strings),
         'APP_NAME_STRING_MISSING')
    need('R.drawable.ic_stat_skybind' in native, 'NOTIFICATION_BRANDING_MISSING')
    ET.fromstring(source('android-app/app/src/main/res/drawable/ic_stat_skybind.xml'))
    source('android-app/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')
    source('android-app/app/src/main/res/drawable/ic_launcher_monochrome.xml')
    return {'state':'PASS_NATIVE05_PERSONAL_APK_SOURCE_ONLY',
            'android_compiled':False,'signer_verified_on_ci':False,
            'installed_pair_verified':False,'release_qualified':False}

if __name__=='__main__':
    try:
        print(json.dumps(verify(),sort_keys=True))
    except (GateError,OSError,ET.ParseError) as exc:
        print(json.dumps({'state':'FAILED_NATIVE05_SOURCE_GUARD','reason':str(exc)}))
        raise SystemExit(2)
