#!/usr/bin/env python3
"""Device evidence collector for an *ordinary* Android app process.

Does not perform any root mount mutation. A root-shell read never counts as an
ordinary-app read/write. Collection requires an already installed probe APK.
The signed/immutable Devtool run record must bind outputs before qualification.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,re,subprocess,sys,time

PACKAGE='org.skybind.probe'
ACTIVITY='org.skybind.probe/.ProbeActivity'
MAX=32*1024
NONCE_RE=re.compile(r'^[0-9a-f]{32}$')

class DeviceError(ValueError):pass

def run(adb:list[str],args:list[str],timeout:int=20)->str:
    p=subprocess.run(adb+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=False)
    if p.returncode:raise DeviceError('device command failed: '+str(args[:2])+': '+p.stderr.decode('utf-8','replace')[:240])
    if len(p.stdout)>MAX:raise DeviceError('oversized device response')
    return p.stdout.decode('utf-8','replace').strip()

def facts(adb:list[str])->dict:
    state=run(adb,['get-state'])
    if state!='device':raise DeviceError('device not online')
    props={key:run(adb,['shell','getprop',key]) for key in ('ro.build.fingerprint','ro.product.cpu.abi','ro.kernel.qemu','ro.build.version.sdk')}
    if props['ro.kernel.qemu'] not in ('','0'):raise DeviceError('emulator cannot qualify as physical device')
    if props['ro.product.cpu.abi']!='arm64-v8a':raise DeviceError('not an ARM64 device')
    if not props['ro.build.fingerprint'] or props['ro.build.fingerprint'].startswith('generic'):
        raise DeviceError('missing/unsuitable device fingerprint')
    return props

def validate_probe(probe:dict,nonce:str,target:str,reported_uid:int)->None:
    if probe.get('schema_version')!=1 or probe.get('nonce')!=nonce or probe.get('path')!=target:
        raise DeviceError('probe identity mismatch')
    if probe.get('package')!=PACKAGE or probe.get('status')!='APP_READ_WRITE_PASS':
        raise DeviceError('ordinary Android application did not prove read/write')
    if probe.get('uid')!=reported_uid or reported_uid in (0,2000) or reported_uid<10000:
        raise DeviceError('app UID not proven or privileged')
    if probe.get('write_bytes')!=32 or probe.get('read_bytes')!=32 or probe.get('read_matches') is not True:
        raise DeviceError('probe bytes/readback mismatch')


def capture(adb_binary:str,serial:str,path:str,output:pathlib.Path)->dict:
    # Device commands always receive argv arrays; no shell construction from paths.
    # ADB shell serializes arguments through a remote command parser on some
    # platform-tools versions. Reject metacharacters rather than relying on
    # client-specific quoting to prevent code execution in the device shell.
    if (not re.fullmatch(r'/[A-Za-z0-9_./-]{1,500}',path)
        or '..' in pathlib.PurePosixPath(path).parts or '//' in path or '/./' in path):
        raise DeviceError('unsafe target path or shell metacharacter')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',serial):
        raise DeviceError('invalid device serial')
    adb=[adb_binary,'-s',serial]
    props=facts(adb)
    pkgs=run(adb,['shell','cmd','package','list','packages','-U',PACKAGE])
    m=re.search(r'^package:'+re.escape(PACKAGE)+r'\s+uid:(\d+)$',pkgs,re.M)
    if not m:raise DeviceError('probe app not installed or package UID unavailable')
    uid=int(m.group(1))
    if uid<10000:raise DeviceError('expected unprivileged app UID')
    nonce=os.urandom(16).hex()
    # Activity executes as actual installed app; run-as reads *its written receipt*.
    # run-as alone is not treated as app-access evidence.
    try:
        run(adb,['shell','run-as',PACKAGE,'rm','-f','files/skybind-probe.json'])
    except DeviceError as e:raise DeviceError('debuggable probe readout unavailable: '+str(e))
    run(adb,['shell','am','start','-W','-n',ACTIVITY,'--es','nonce',nonce,'--es','path',path],timeout=30)
    report=None
    for _ in range(20):
        time.sleep(.3)
        try:
            report=run(adb,['shell','run-as',PACKAGE,'cat','files/skybind-probe.json'])
            if report:break
        except DeviceError:pass
    if not report:raise DeviceError('no app-process proof produced')
    try:result=json.loads(report)
    except (json.JSONDecodeError,ValueError):raise DeviceError('invalid app-process proof')
    validate_probe(result,nonce,path,uid)
    record={'schema_version':1,'kind':'SKYBIND_ORDINARY_APP_RW','qualification':'RAW_UNATTESTED',
            'device':props,'app_uid':uid,'app_report':result,'collected_at_unix':int(time.time()),
            'device_serial_sha256':hashlib.sha256(serial.encode()).hexdigest(),
            'warning':'Raw device result requires independent Devtool run provenance, companion scenarios and gate review.'}
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists() or output.is_symlink():raise DeviceError('evidence output already exists')
    fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as fp:
        json.dump(record,fp,indent=2,sort_keys=True);fp.write('\n');fp.flush();os.fsync(fp.fileno())
    return record

def main():
    p=argparse.ArgumentParser();p.add_argument('--adb',default='adb');p.add_argument('--serial',required=True)
    p.add_argument('--path',required=True);p.add_argument('--out',type=pathlib.Path,required=True)
    a=p.parse_args()
    try:
        output=capture(a.adb,a.serial,a.path,a.out)
        print(json.dumps({'status':output['qualification'],'kind':output['kind']}))
        return 0
    except (DeviceError, subprocess.TimeoutExpired, OSError) as e:
        print('Skybind device evidence BLOCKED: '+str(e),file=sys.stderr);return 3
if __name__=='__main__':sys.exit(main())
