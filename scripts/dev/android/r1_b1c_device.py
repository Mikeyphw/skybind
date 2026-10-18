#!/usr/bin/env python3
"""B1-C source-bound Android provenance and bounded instrumentation acceptance.

Consumes an existing immutable QW3 H4 hosted attestation. NEVER creates a
GitHub build, uses root, clears app data, uninstalls, or enables the Go broker.
The optional --install-missing installs *only* when both packages are absent;
no -r or replacement is ever permitted. All output is qualification-scoped.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[3]
PIPELINE = 'be9ee025156643fe9a5c21d577dd0d2f'
SOURCE = '1b808119720ed3c042ffc2a8fa84ebe313697eb8'
RUN = 39070051696
APP = 'io.github.mikeyphw.skybind'
TEST = APP + '.test'
RUNNER = TEST + '/androidx.test.runner.AndroidJUnitRunner'
CASES = {
    ('io.github.mikeyphw.skybind.ScaffoldTest', 'appStartsWithoutBrokerOrRoot'),
    ('io.github.mikeyphw.skybind.UidPackageEvidenceTest', 'deniesUnknownOrUnpinnedCaller'),
}
ARTIFACT_DIR = ROOT / '.devtool/artifacts/github-downloads'
RECEIPTS = ROOT / 'build/evidence/android/b1c'
MAX_ZIP = 256 * 1024 * 1024
HEX64 = re.compile(r'^[0-9a-f]{64}$')

class Blocked(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def need(ok, reason):
    if not ok:
        raise Blocked(reason)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def hosted_attestation(pipeline=PIPELINE):
    need(pipeline == PIPELINE, 'PIPELINE_ID_NOT_ATTESTED_FOR_B1C')
    path = ROOT / 'build/evidence/r1-android-hosted' / pipeline / 'attestation.json'
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 16384,
         'ATTESTATION_MISSING_OR_INVALID')
    obj = json.loads(path.read_text())
    for field, val in {
        'status':'PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED',
        'repository':'Mikeyphw/skybind', 'head_sha':SOURCE, 'run_id':RUN,
        'device_qualified':False, 'release_qualified':False,
        'github_run_authenticated':True, 'signatures_inspected':True,
    }.items():
        need(obj.get(field) == val and type(obj.get(field)) is type(val),
             'ATTESTATION_' + field.upper() + '_MISMATCH')
    for field in ('app_sha256','test_sha256','artifact_zip_sha256','debug_signer_sha256'):
        need(isinstance(obj.get(field), str) and HEX64.fullmatch(obj[field]),
             'ATTESTATION_INVALID_' + field.upper())
    need(type(obj.get('run_attempt')) is int and obj['run_attempt'] > 0 and
         type(obj.get('artifact_id')) is int and obj['artifact_id'] > 0,
         'ATTESTATION_REMOTE_IDENTITY_INVALID')
    return obj


def verified_archive(receipt):
    need(ARTIFACT_DIR.is_dir() and not ARTIFACT_DIR.is_symlink(), 'VERIFIED_ARCHIVE_DIRECTORY_MISSING')
    matches = []
    # Explicitly limited to the Devtool controlled artifact location.
    for candidate in ARTIFACT_DIR.iterdir():
        if (candidate.suffix == '.zip' and not candidate.is_symlink() and
            candidate.is_file() and 0 < candidate.stat().st_size <= MAX_ZIP and
            digest(candidate) == receipt['artifact_zip_sha256']):
            matches.append(candidate)
    need(len(matches) == 1, 'AUTHENTICATED_ARTIFACT_NOT_UNIQUE_OR_MISSING')
    return matches[0]


def copy_verified_pair(archive, receipt, destination):
    need(not archive.is_symlink(), 'ARCHIVE_SYMLINK_REJECTED')
    expected = {'app-debug.apk':receipt['app_sha256'],
                'app-debug-androidTest.apk':receipt['test_sha256']}
    with zipfile.ZipFile(archive) as z:
        files = [x for x in z.infolist() if not x.is_dir()]
        names = {i.filename for i in files}
        need(len(names) == len(files), 'DUPLICATE_ARCHIVE_MEMBER')
        options = [set(expected)|{'android-build-manifest.json'},
                   {'android-build-evidence/'+k for k in expected} |
                   {'android-build-evidence/android-build-manifest.json'}]
        need(names in options, 'UNEXPECTED_ARCHIVE_MEMBERS')
        prefix = 'android-build-evidence/' if any(n.startswith('android-build-evidence/') for n in names) else ''
        result = {}
        for name, checksum in expected.items():
            item = z.getinfo(prefix+name)
            need(0 < item.file_size < MAX_ZIP, 'INVALID_APK_ARCHIVE_SIZE')
            target = destination/name
            with z.open(item) as src, target.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            need(digest(target) == checksum, 'HOSTED_APK_SHA256_MISMATCH')
            result[name] = target
    return result


def adb_call(adb, serial, *arguments, timeout=60):
    args = [adb, '-s', serial, *arguments]
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked('ADB_COMMAND_UNAVAILABLE_OR_TIMEOUT') from exc
    return result.returncode, result.stdout.decode('utf-8','replace'), result.stderr.decode('utf-8','replace')


def chosen_device(adb, serial):
    need(bool(shutil.which(adb)), 'ADB_NOT_FOUND')
    p = subprocess.run([adb, 'devices'], capture_output=True, text=True, timeout=15)
    need(p.returncode == 0, 'ADB_DEVICES_FAILED')
    lines = [ln.split() for ln in p.stdout.splitlines()[1:] if ln.strip()]
    ready = [ln[0] for ln in lines if len(ln)>=2 and ln[1]=='device']
    need(bool(ready), 'NO_AUTHORIZED_ADB_DEVICE')
    if serial:
        need(serial in ready, 'SELECTED_DEVICE_NOT_AUTHORIZED')
        return serial
    need(len(ready)==1, 'MULTIPLE_DEVICES_REQUIRE_EXPLICIT_SERIAL')
    return ready[0]


def getprop(adb, serial, name):
    code,out,_ = adb_call(adb,serial,'shell','getprop',name)
    need(code==0 and out.strip(), 'DEVICE_PROPERTY_UNAVAILABLE')
    return out.strip()


def installed_apk(adb, serial, package, local):
    code,out,err = adb_call(adb,serial,'shell','pm','path',package)
    need(code == 0, 'PACKAGE_MANAGER_QUERY_FAILED')
    lines=[ln.strip() for ln in out.splitlines() if ln.strip()]
    if not lines:
        need(not err.strip(), 'PACKAGE_MANAGER_QUERY_AMBIGUOUS')
        return None
    need(len(lines)==1 and lines[0].startswith('package:'), 'INSTALLED_APK_SPLITS_OR_AMBIGUITY')
    remote=lines[0][len('package:'):]
    need(remote.startswith('/data/app/') and remote.endswith('/base.apk') and
         re.fullmatch(r'[A-Za-z0-9_./+@=:\-~]+',remote) is not None,
         'INSTALLED_APK_PATH_UNTRUSTED')
    code,_,_ = adb_call(adb,serial,'pull',remote,str(local),timeout=90)
    need(code == 0 and local.is_file() and not local.is_symlink(), 'INSTALLED_APK_PULL_BLOCKED')
    return digest(local)


def check_installed(adb, serial, tmp, receipt):
    app = installed_apk(adb,serial,APP,tmp/'installed-app.apk')
    test = installed_apk(adb,serial,TEST,tmp/'installed-test.apk')
    if app is None and test is None:
        return 'ABSENT'
    need(app is not None and test is not None,'PARTIAL_INSTALLED_APK_PAIR')
    need(app == receipt['app_sha256'] and test == receipt['test_sha256'],
         'INSTALLED_APK_BYTES_DIFFER_FROM_HOSTED_EVIDENCE')
    return 'MATCHED'


def install_missing(adb, serial, pair):
    # No replacements, downgrades, data clears, uninstalls or privileged flags.
    for name in ('app-debug.apk','app-debug-androidTest.apk'):
        code,out,_ = adb_call(adb,serial,'install',*(['-t'] if name.endswith('androidTest.apk') else []),str(pair[name]),timeout=120)
        need(code==0 and out.strip().endswith('Success'), 'EXPLICIT_INSTALL_FAILED')


def parse_instrumentation(stdout):
    """Require exactly two distinct successful AndroidJUnitRunner test reports."""
    results={}
    pending={}
    for raw in stdout.replace('\r','').splitlines():
        if raw.startswith('INSTRUMENTATION_STATUS: '):
            content=raw[len('INSTRUMENTATION_STATUS: '):]
            if '=' in content:
                key,val=content.split('=',1)
                if key in ('class','test'):
                    pending[key]=val.strip()
        elif raw.startswith('INSTRUMENTATION_STATUS_CODE: '):
            text=raw.split(':',1)[1].strip()
            need(re.fullmatch(r'-?\d+',text) is not None,'MALFORMED_INSTRUMENTATION_STATUS')
            code=int(text)
            if code==0:
                key=(pending.get('class'),pending.get('test'))
                need(key in CASES and key not in results,'UNEXPECTED_OR_DUPLICATE_INSTRUMENTATION_CASE')
                results[key]='PASS'
            elif code not in (1,):
                raise Blocked('INSTRUMENTATION_CASE_FAILED')
            pending={}
    codes=re.findall(r'^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$', stdout,flags=re.M)
    need(codes==['-1'], 'INSTRUMENTATION_FINAL_STATUS_INVALID')
    need(set(results)==CASES,'INSTRUMENTATION_CASES_INCOMPLETE')
    need('INSTRUMENTATION_FAILED' not in stdout and 'FAILURES!!!' not in stdout,
         'INSTRUMENTATION_ERROR_MARKER')
    return {f'{k[0].rsplit(".",1)[-1]}#{k[1]}': 'PASS' for k in sorted(results)}


def instrument(adb, serial):
    methods=','.join(f'{cl}#{fn}' for cl,fn in sorted(CASES))
    code,out,err=adb_call(adb,serial,'shell','am','instrument','-w','-r','-e','class',methods,RUNNER,timeout=180)
    need(code==0,'INSTRUMENTATION_SHELL_COMMAND_FAILED')
    return parse_instrumentation(out)


def output_receipt(report):
    need(not RECEIPTS.is_symlink(), 'RECEIPT_DIRECTORY_SYMLINK')
    RECEIPTS.mkdir(parents=True, exist_ok=True)
    name='b1c-'+uuid.uuid4().hex+'.json'
    path=RECEIPTS/name
    with path.open('x',encoding='utf-8') as dst:
        json.dump(report,dst,sort_keys=True,indent=2)
        dst.write('\n')
    return str(path)


def run(args):
    report={'schema':'skybind-b1c-device-v1','state':'BLOCKED',
            'hosted_pipeline_id':args.pipeline_id,'hosted_source_sha':SOURCE,
            'hosted_run_id':RUN,'mode':args.mode,
            'recorded_at_utc':datetime.now(timezone.utc).isoformat(),
            'harness_sha256':digest(Path(__file__)),
            'device_qualified':False,
            'release_qualified':False,'production_broker_enabled':False,
            'automatic_uninstall':False,'automatic_data_clear':False,
            'automatic_reboot':False,'installation_performed':False,'tests':{}}
    try:
        receipt=hosted_attestation(args.pipeline_id)
        report['hosted_attestation']='PASS'
        report['hosted_artifact_sha256']=receipt['artifact_zip_sha256']
        archive=verified_archive(receipt)
        with tempfile.TemporaryDirectory(prefix='skybind-b1c-') as temporary:
            tmp=Path(temporary)
            pair=copy_verified_pair(archive,receipt,tmp)
            report['hosted_apk_bytes']='PASS'
            adb=shutil.which('adb')
            need(adb is not None,'ADB_NOT_FOUND')
            serial=chosen_device(adb,args.serial)
            report['device_serial_sha256']=hashlib.sha256(serial.encode()).hexdigest()
            report['device_api']=int(getprop(adb,serial,'ro.build.version.sdk'))
            report['device_abi']=getprop(adb,serial,'ro.product.cpu.abi')
            need(report['device_api']>=26,'DEVICE_API_BELOW_APK_MINIMUM')
            state=check_installed(adb,serial,tmp,receipt)
            report['installed_pair']=state
            if state=='ABSENT' and args.mode=='instrument' and args.install_missing:
                install_missing(adb,serial,pair)
                report['installation_performed']=True
                state=check_installed(adb,serial,tmp,receipt)
                report['installed_pair']=state
            if state=='ABSENT':
                report['state']='PREPARED_INSTALL_REQUIRED'
            elif args.mode=='preflight':
                report['state']='PASS_INSTALLED_PAIR_PROVENANCE'
            else:
                report['tests']=instrument(adb,serial)
                report['state']='PASS_B1C_DEVICE_INSTRUMENTATION'
                report['b1c_device_instrumentation_passed']=True
    except (Blocked, ValueError, KeyError, OSError, json.JSONDecodeError, zipfile.BadZipFile, subprocess.SubprocessError) as exc:
        report['state']='BLOCKED'
        report['reason']=exc.reason if isinstance(exc,Blocked) else type(exc).__name__.upper()
    receipt_path=output_receipt(report)
    print(json.dumps({'state':report['state'],'receipt':receipt_path,
                      'reason':report.get('reason'), 'tests':report['tests'],
                      'installed_pair':report.get('installed_pair')},sort_keys=True))
    return 0 if report['state'].startswith('PASS_') else 2


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-id',default=PIPELINE)
    parser.add_argument('--mode',choices=('preflight','instrument'),default='preflight')
    parser.add_argument('--serial',help='Required when more than one authorized adb transport is present')
    parser.add_argument('--install-missing',action='store_true',help='Explicitly install only if both packages are absent; never replace')
    args=parser.parse_args()
    if args.install_missing and args.mode!='instrument':
        parser.error('--install-missing requires --mode instrument')
    return run(args)


if __name__=='__main__':
    raise SystemExit(main())
