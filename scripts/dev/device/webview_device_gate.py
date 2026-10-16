#!/usr/bin/env python3
"""Foreground actual WebUI host + in-page read-only receipt, RAW not a seal.

Use the same Android WebUI host (KernelSU Manager or WebUI X Portable)
for receipt generation and foreground observation. Does not conflate
WebUI X ksu compatibility bridge with native KernelSU manager evidence.
Never collects raw dumpsys text, screenshots, tokens, names or paths.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile
from api_acceptance import DeviceRPC
from boot_journal_gate import OUT, source_info, utc, write_json_exclusive, root, GateError

MANAGERS={'me.weishu.kernelsu','com.rifsxd.ksunext'}
# Exact installed host IDs. Spoofed builds must be individually selected and
# established by real Android foreground evidence; never wildcard arbitrary apps.
WEBUI_X_HOSTS={'com.dergoogler.mmrl.wx'}
SPOOFED_WEBUI_X_HOSTS={'vtebo2.rezdpneqo9vt.d2wjkhzv77ptrycwv': 'v438-release'}
HOSTS=MANAGERS | WEBUI_X_HOSTS | set(SPOOFED_WEBUI_X_HOSTS)
# No silent auto-acceptance of a spoofed package: require explicit operator selection.
AUTO_HOSTS=MANAGERS | WEBUI_X_HOSTS

def host_type(package):
    if package in SPOOFED_WEBUI_X_HOSTS:
        return 'webuix_spoofed_user_reported'
    return 'webuix_portable' if package in WEBUI_X_HOSTS else ('kernelsu_manager' if package in MANAGERS else 'unknown')
INSTALLED_JS='/data/adb/modules/skybind/webroot/api_qa_probe.js'
CHECKS={'Actual KernelSU ksu.exec transport','Embedded operation.events read and cursor',
        'Embedded jobs.status presentation'}
MAX_RECEIPT_BYTES=16*1024


def select_receipt_source(explicit=None, home=None):
    """Resolve only named receipt locations. Never scan arbitrary device files."""
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    home = Path(home if home is not None else os.environ.get('HOME', str(Path.home())))
    candidates = (home/'Downloads/skybind-webview-probe.json',
                  home/'storage/downloads/skybind-webview-probe.json',
                  Path('/storage/emulated/0/Download/skybind-webview-probe.json'))
    for candidate in candidates:
        if candidate.is_file() and not candidate.is_symlink():
            return str(candidate)
    raise GateError('No WebView receipt found. In your actual WebUI host > Skybind > More > Device qualification, '
                    'tap Observe embedded transport, then Copy sanitized receipt. '
                    'For Termux:API use SKYBIND_QA_WEBVIEW_RECEIPT=clipboard; '
                    'otherwise save skybind-webview-probe.json in Downloads and retry.')


def load_receipt_bytes(source):
    """Read opt-in clipboard or named file without emitting private content."""
    if source == 'clipboard':
        if shutil.which('termux-clipboard-get') is None:
            raise GateError('Clipboard mode requires Termux:API (termux-clipboard-get). '
                            'Alternatively save the copied JSON to a file and set SKYBIND_QA_WEBVIEW_RECEIPT.')
        try:
            completed = subprocess.run(['termux-clipboard-get'], stdout=subprocess.PIPE,
                                       stderr=subprocess.DEVNULL, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise GateError('Termux clipboard is inaccessible; save the sanitized receipt as a JSON file instead')
        if completed.returncode != 0:
            raise GateError('Termux:API clipboard request failed; save the sanitized receipt as a JSON file instead')
        raw = completed.stdout
    else:
        path=Path(source).expanduser()
        if not path.is_file() or path.is_symlink():
            raise GateError('WebView receipt file does not exist or is a symlink; '
                            'set SKYBIND_QA_WEBVIEW_RECEIPT to the absolute JSON path')
        if not 0 < path.stat().st_size <= MAX_RECEIPT_BYTES:
            raise GateError('WebView receipt must be nonempty and at most 16 KiB')
        raw=path.read_bytes()
    if not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise GateError('WebView receipt unavailable or oversized (max 16 KiB)')
    return raw

RESUMED_KEYS=re.compile(r'\b(?:topResumedActivity|mTopResumedActivity|mResumedActivity|resumedActivity)\b')


def foreground_manager(dump, manager):
    """Match ONLY current resumed activity records, not historical or process caches."""
    if manager not in HOSTS:
        raise GateError('unrecognized WebUI host package')
    for line in dump.splitlines():
        if not RESUMED_KEYS.search(line):
            continue
        if re.search(r'(?<![\w.])'+re.escape(manager)+r'/',line):
            return True
    return False


def observe_foreground(manager, *, observation_seconds=45, interval_seconds=2,
                       root_command=root, clock=time.monotonic,
                       sleep=time.sleep):
    """Bounded live observation; two consecutive positive snapshots are required.

    Observing the MANAGER is not itself proof that a particular WebView page
    was visible. The separate in-page, timestamped receipt is still required.
    Raw dumpsys content is never persisted or logged.
    """
    if manager not in HOSTS and manager != 'auto':
        raise GateError('unrecognized WebUI host package')
    if not (2 <= observation_seconds <= 90):
        raise GateError('foreground observation window must be 2..90 seconds')
    if not (1 <= interval_seconds <= 10):
        raise GateError('foreground sample interval must be 1..10 seconds')
    start=clock()
    attempts=0
    consecutive=0
    positive_samples=0
    matched=None
    reason='no consecutive resumed-activity samples matched a configured Android WebUI host'
    candidates=sorted(AUTO_HOSTS) if manager=='auto' else [manager]
    while clock()-start < observation_seconds or attempts==0:
        attempts+=1
        try:
            dump=root_command('/system/bin/dumpsys activity activities',timeout=12,max_bytes=2*1024*1024)
            found=next((pkg for pkg in candidates if foreground_manager(dump,pkg)),None)
        except (GateError,subprocess.SubprocessError, OSError, TimeoutError):
            found=None
            reason='foreground activity snapshot was unavailable or did not show the manager'
        if found:
            positive_samples+=1
            consecutive = consecutive+1 if matched==found else 1
            matched=found
            if consecutive>=2:
                return True, {'attempts':attempts,'positive_samples':positive_samples,
                              'matched_host_sha256':hashlib.sha256(found.encode()).hexdigest(),
                              'matched_host_type':host_type(found),
                              'requirement':'two consecutive currently-resumed activity snapshots',
                              'status':'MATCHED'}
        else:
            matched=None
            consecutive=0
        remaining=observation_seconds-(clock()-start)
        if remaining<=0:
            break
        sleep(min(interval_seconds,remaining))
    return False, {'attempts':attempts,'positive_samples':positive_samples,
                   'requirement':'two consecutive currently-resumed activity snapshots',
                   'status':'NOT_PROVEN','reason':reason}

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

def evaluate(parsed,fg,js_match,bin_hash, observed_host_type='kernelsu_manager'):
    outcomes=[]
    def case(name,status,detail):outcomes.append({'test':name,'status':status,'detail':detail})
    spoofed=observed_host_type=='webuix_spoofed_user_reported'
    webuix=observed_host_type in ('webuix_portable','webuix_spoofed_user_reported')
    host_label=('Spoofed WebUI X foreground Activity (package match only)' if spoofed else
                'WebUI X foreground Activity' if webuix else
                'KernelSU foreground Activity' if observed_host_type=='kernelsu_manager'
                else 'Android WebUI host foreground Activity')
    case(host_label, 'PASS' if fg else 'BLOCKED',
         'two foreground Activity samples for the selected Android WebUI host' if fg
         else 'foreground Android WebUI host not proven')
    case('Installed QA WebView asset matches source', 'PASS' if js_match else 'BLOCKED',
         'exact installed script digest compared to source' if js_match else 'asset missing or differs from source')
    case('Installed Skybind ELF digest observable', 'PASS' if bin_hash else 'BLOCKED',
         'ELF SHA-256 captured' if bin_hash else 'installed ELF not observable')
    for name in sorted(CHECKS):
        reported=parsed.get(name,'BLOCKED')
        status=reported if (fg and js_match) or reported=='FAIL' else 'BLOCKED'
        display_name=('WebUI X ksu.exec-compatible transport (in-page report)'
                      if webuix and name=='Actual KernelSU ksu.exec transport' else name)
        case(display_name,status,'WebView-produced sanitized callback observation; not independently attested; '
             + ('WebUI X compatibility bridge; spoofed host authenticity NOT attested' if spoofed else
                'WebUI X compatibility bridge, NOT native KernelSU manager' if webuix else 'native manager host'))
    for name in ('Visual navigation/preview/confirmation','Live progress and cursor after close/reopen',
                 'Owned job cancellation','Transient ksu.exec failure and safe recovery'):
        case(name,'BLOCKED','requires separate UI interaction and sanitized device evidence')
    return outcomes

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt-file',help='Sanitized WebView JSON file, or clipboard with Termux:API')
    p.add_argument('--host-package','--manager-package',dest='host_package',
                   choices=['auto',*sorted(HOSTS)],
                   default=os.environ.get('SKYBIND_QA_WEBVIEW_HOST',os.environ.get('SKYBIND_QA_MANAGER_PACKAGE','auto')),
                   help='Exact Android WebUI host; spoofed builds require explicit selection (auto only recognizes stock hosts)')
    p.add_argument('--foreground-delay',type=int,default=0,help='Optional pre-observation delay (0..60 s)')
    p.add_argument('--foreground-window',type=int,default=45,help='Bounded live foreground observation window (2..90 s)')
    p.add_argument('--output-dir',type=Path,default=OUT)
    a=p.parse_args(argv)
    try:
        if not 0<=a.foreground_delay<=60:raise GateError('foreground delay must be 0..60 seconds')
        source=select_receipt_source(a.receipt_file or os.environ.get('SKYBIND_QA_WEBVIEW_RECEIPT'))
        raw_bytes=load_receipt_bytes(source)
        try:
            data=json.loads(raw_bytes.decode('utf-8'))
        except (UnicodeError, json.JSONDecodeError):
            raise GateError('Receipt is not valid JSON; copy the sanitized probe output from the actual Skybind WebView')
        parsed=parse_receipt(data)
        if not 2 <= a.foreground_window <= 90:
            raise GateError('foreground observation window must be 2..90 seconds')
        print('Receipt verified. Return to Skybind in your actual WebUI host (e.g. WebUI X); watching resumed Activity '
              'for up to '+str(a.foreground_window)+' seconds.',flush=True)
        if a.foreground_delay:
            time.sleep(a.foreground_delay)
        fg,foreground_evidence=observe_foreground(a.host_package,
                            observation_seconds=a.foreground_window)
        repo=Path(__file__).resolve().parents[3]
        local=repo/'module/webroot/api_qa_probe.js'
        installed=installed_js_sha()
        js_match=bool(installed and local.is_file() and installed==hashlib.sha256(local.read_bytes()).hexdigest())
        bin_hash=DeviceRPC().installed_binary_hash()
        # A non-matching host cannot be inferred from the receipt or from a manager inventory.
        observed_type=foreground_evidence.get('matched_host_type','unproven') if fg else 'unproven'
        display_type=observed_type if fg else (host_type(a.host_package) if a.host_package!='auto' else 'unproven')
        outcomes=evaluate(parsed,fg,js_match,bin_hash,observed_host_type=display_type)
        counts={x:sum(c['status']==x for c in outcomes) for x in ('PASS','FAIL','BLOCKED')}
        session=hashlib.sha256((str(data['recorded_at_utc'])+str(time.monotonic_ns())).encode()).hexdigest()[:32]
        report={'schema_version':1,'kind':'SKYBIND_KSU_WEBVIEW_RAW_GATE',
                'captured_at_utc':utc(),'qualification':'RAW_UNATTESTED_NOT_RELEASE_QUALIFIED',
                'source':source_info(),'foreground_evidence':foreground_evidence,'installed_binary_sha256':bin_hash,
                'installed_qa_js_sha256':installed,
                'selected_host_package_sha256':hashlib.sha256(a.host_package.encode()).hexdigest(),
                'selected_host_type':host_type(a.host_package) if a.host_package != 'auto' else 'auto',
                'host_version_user_reported':SPOOFED_WEBUI_X_HOSTS.get(a.host_package),
                'host_app_authenticity':'NOT_ATTESTED_PACKAGE_MATCH_ONLY' if a.host_package in SPOOFED_WEBUI_X_HOSTS else 'NOT_ATTESTED',
                'observed_host_type':observed_type,
                'receipt_sha256':hashlib.sha256(raw_bytes).hexdigest(),
                'observations':outcomes,'counts':counts,
                'limitations':['Foreground Android host snapshots do not prove the WebView page identity',
                               'A WebUI X ksu.exec-compatible bridge is not native KernelSU manager proof',
                               'Spoofed host package/version and signing authenticity are not attested by foreground observation',
                               'No direct screenshot or view-layout verification',
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
        print('WEBVIEW GATE BLOCKED: '+str(e),file=sys.stderr)
        return 3
    except Exception:
        print('WEBVIEW GATE BLOCKED: unexpected collector exception (private details suppressed)',file=sys.stderr)
        return 3

if __name__=='__main__':sys.exit(main())
