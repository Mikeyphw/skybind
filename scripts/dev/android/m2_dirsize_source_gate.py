#!/usr/bin/env python3
"""M2 directory size compatibility: source-only; no device, Gradle or root."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[3]
PATHS={
  'go':'internal/provider/provider.go',
  'go_test':'internal/provider/provider_browse_directory_size_test.go',
  'kt':'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RemoteBrowseReader.kt',
  'kt_test':'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/RemoteDirectorySizeTest.kt',
  'live':'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveRootBrowserAcceptanceTest.kt',
  'host':'scripts/dev/android/m2_live_device.py',
  'grouped':'scripts/dev/android/r1_b1c_security_source.py',
}
class Violation(Exception):pass

def need(yes, reason):
    if not yes:raise Violation(reason)

def verify(root=ROOT):
    src={}
    for name,rel in PATHS.items():
        p=root/rel
        need(p.is_file() and not p.is_symlink(), 'MISSING_'+name)
        src[name]=p.read_text()
    need('(entry.Size < 0 && (!entry.IsDir || entry.Size != -1))' in src['go'] and
         'entry.Size < 0 {' not in src['go'], 'GO_DIRECTORY_SIZE_CONTRACT')
    need('require(size >= 0 || (isDir && size == -1L))' in src['kt'] and
         'require(size >= 0)' not in src['kt'], 'ANDROID_DIRECTORY_SIZE_CONTRACT')
    need('TestBrowseAcceptsRcloneUnknownDirectorySize' in src['go_test'] and
         'TestBrowseRejectsInvalidNegativeSizes' in src['go_test'], 'GO_NEGATIVE_TESTS_MISSING')
    need('permitsSevenUnknownSizeDirectoriesAndSixteenFiles' in src['kt_test'] and
         'rejectsNegativeFileSizeAndDirectoryBelowUnknownMarker' in src['kt_test'], 'ANDROID_NEGATIVE_TESTS_MISSING')
    codes=['BROWSE_AUTHORIZATION','BROWSE_VALIDATION','BROWSE_RESPONSE','BROWSE_TRANSPORT']
    for code in codes:
        token='SKYBIND_LIVE_FAILED_'+code
        need(token in src['live'] and token in src['host'], 'LIVE_DIAGNOSTIC_MISSING_'+code)
    need('except (_: IllegalArgumentException)' not in src['live'], 'INVALID_KOTLIN_CATCH')
    need('tests.test_m2_dirsize_source' in src['grouped'] and
         'scripts/dev/android/m2_dirsize_source_gate.py' in src['grouped'] and
         "'./internal/provider', '-run'" in src['grouped'],
         'GROUPED_CHECK_MISSING')
    return {'state':'PASS_M2_DIRSIZE_SOURCE_ONLY','device_tested':False,'daemon_modified':False,
            'release_qualified':False}

if __name__=='__main__':
    try: print(json.dumps(verify(), sort_keys=True))
    except (Violation,OSError,UnicodeError) as exc:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(exc)},sort_keys=True));raise SystemExit(2)
