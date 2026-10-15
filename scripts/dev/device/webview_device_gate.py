#!/usr/bin/env python3
"""Foreground KernelSU + in-WebView sanitized read-only receipt, RAW not a seal.

Copy the JSON from Skybind > More > Device qualification on the real
KernelSU WebView into a local file. Launch this collector from Termux, then
switch BACK to the KernelSU WebView before its foreground observation.
Never collects raw dumpsys text, screenshots, tokens, names or remote paths.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import zipfile
from api_acceptance import DeviceRPC
from boot_journal_gate import OUT, source_info, utc, write_json_exclusive, root, GateError

MANAGERS={'me.weishu.kernelsu','com.rifsxd.ksunext'}
INSTALLED_JS='/data/adb/modules/skybind/webroot/api_qa_probe.js'
CHECKS={'Actual KernelSU ksu.exec transport','Embedded operation.events read and cursor',
        'Embedded jobs.status presentation'}

def foreground_manager(dump, manager):
    if manager not in MANAGERS:raise GateError('unrecognized KernelSU manager package')
    # Ignore historical Activities and process caches. Only resumed/foreground.
    lines=[line for line in dump.splitlines() if re.search(r'(topResumedActivity|mResumedActivity|ResumedActivity|resumedActivity)',line)]
    return any(re.search(r'(?<![\w.])'+re.escape(manager)+r'/',line) for line in lines)

def installed_js_sha():
    cmd='if [ -L '+INSTALLED_JS+' ] || [ ! -f '+INSTALLED_JS+' ]; then exit 4; fi; /system/bin/sha256sum '+INSTALLED_JS
    try: result=root(cmd)
    except GateError:return None
    match=re.fullmatch(r'([0-9a-f]{64})\s+\S+',result)
    return match.group(1) if match else None

def parse_receipt(raw):
    if not isinstance(raw,dict) or raw.get('schema_version')!=1 or raw.get('kind')!='SKYBIND_KSU_WEBVIEW_READONLY_PROBE':
        raise GateError('unsupported embedded receipt schema')
    stamp=raw.get('recorded_at_utc')
    if not isinstance(stamp,str):raise GateError('missing WebView capture timestamp')
    try: d=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    except ValueError:raise GateError('invalid WebView capture time')
    age=(dt.datetime.now(dt.timezone.utc)-d).total_seconds()
    if age < -60 or age > 900:raise GateError('WebView capture timestamp outside 15-minute window')
    observations=raw.get('observations')
    if not isinstance(observations,list) or len(observations)>16:raise GateError('invalid WebView receipt observations')
    out={}
    for item in observations:
        if not isinstance(item,dict):raise GateError('invalid observation')
        name, status=item.get('test'),item.get('status')
        if name in CHECKS:
            if status not in ('PASS','FAIL','BLOCKED') or name in out:raise GateError('duplicate/bad gate status')
            out[name]=status
    for name in CHECKS:
        if name not in out:out[name]='BLOCKED'
    return out

def evaluate(parsed,fg,js_match,bin_hash):
    outcomes=[]
    def case(name,status,detail):outcomes.append({'test':name,'status':status,'detail':detail})
    case('KernelSU foreground Activity', 'PASS' if fg else 'BLOCKED',
         'physical foreground manager captured' if fg else 'foreground KernelSU WebView not proven')
    case('Installed QA WebView asset matches source', 'PASS' if js_match else 'BLOCKED',
         'exact installed script digest compared to source' if js_match else 'asset missing or differs from source')
    case('Installed Skybind ELF digest observable', 'PASS' if bin_hash else 'BLOCKED',
         'ELF SHA-256 captured' if bin_hash else 'installed ELF not observable')
    for name in sorted(CHECKS):
        status=parsed.get(name,'BLOCKED') if (fg and js_match) else 'BLOCKED'
        case(name,status,'WebView-produced sanitized callback observation; not independently attested')
    for name in ('Visual navigation/preview/confirmation','Live progress and cursor after close/reopen',
                 'Owned job cancellation','Transient ksu.exec failure and safe recovery'):
        case(name,'BLOCKED','requires separate UI interaction and sanitized device evidence')
    return outcomes

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt-file',type=Path,default=Path(os.environ.get('SKYBIND_QA_WEBVIEW_RECEIPT','/nonexistent')))
    p.add_argument('--manager-package',choices=sorted(MANAGERS),default=os.environ.get('SKYBIND_QA_MANAGER_PACKAGE','me.weishu.kernelsu'))
    p.add_argument('--foreground-delay',type=int,default=12)
    p.add_argument('--output-dir',type=Path,default=OUT)
    a=p.parse_args(argv)
    try:
        if not 0<=a.foreground_delay<=60:raise GateError('foreground delay must be 0..60 seconds')
        if not a.receipt_file.is_file() or a.receipt_file.is_symlink() or a.receipt_file.stat().st_size>16384:
            raise GateError('WebView receipt unavailable or oversized')
        data=json.loads(a.receipt_file.read_text('utf-8'))
        parsed=parse_receipt(data)
        if a.foreground_delay:
            print('Switch to the real KernelSU Skybind WebView now. Foreground capture in '+str(a.foreground_delay)+'s.',flush=True)
            time.sleep(a.foreground_delay)
        dump=root('/system/bin/dumpsys activity activities',timeout=20,max_bytes=2*1024*1024)
        fg=foreground_manager(dump,a.manager_package)
        repo=Path(__file__).resolve().parents[3]
        local=repo/'module/webroot/api_qa_probe.js'
        installed=installed_js_sha()
        js_match=bool(installed and local.is_file() and installed==hashlib.sha256(local.read_bytes()).hexdigest())
        bin_hash=DeviceRPC().installed_binary_hash()
        outcomes=evaluate(parsed,fg,js_match,bin_hash)
        counts={x:sum(c['status']==x for c in outcomes) for x in ('PASS','FAIL','BLOCKED')}
        session=hashlib.sha256((str(data['recorded_at_utc'])+str(time.monotonic_ns())).encode()).hexdigest()[:32]
        report={'schema_version':1,'kind':'SKYBIND_KSU_WEBVIEW_RAW_GATE',
                'captured_at_utc':utc(),'qualification':'RAW_UNATTESTED_NOT_RELEASE_QUALIFIED',
                'source':source_info(),'installed_binary_sha256':bin_hash,
                'installed_qa_js_sha256':installed,
                'manager_package_sha256':hashlib.sha256(a.manager_package.encode()).hexdigest(),
                'receipt_sha256':hashlib.sha256(a.receipt_file.read_bytes()).hexdigest(),
                'observations':outcomes,'counts':counts,
                'limitations':['No direct screenshot or view-layout verification',
                               'In-page JSON is untrusted client-reported material',
                               'No screenshot, transfer, operation cancel, or mutation attempted',
                               'Do not upgrade blocked functionality based on other backend tests']}
        output=a.output_dir/('skybind-webview-raw-'+session+'.json')
        write_json_exclusive(output,report)
        with zipfile.ZipFile(output.with_suffix('.zip'),'x',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(output,arcname=output.name)
        print('REPORT: '+str(output)+'\nCOUNTS: '+str(counts),flush=True)
        return 1 if counts['FAIL'] else 0
    except (GateError,ValueError,KeyError,TypeError,OSError,json.JSONDecodeError) as e:
        print('WEBVIEW GATE BLOCKED: '+str(e)[:150],file=sys.stderr)
        return 3
    except Exception:
        print('WEBVIEW GATE BLOCKED: unexpected collector exception (private details suppressed)',file=sys.stderr)
        return 3

if __name__=='__main__':sys.exit(main())
