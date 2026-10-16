#!/usr/bin/env python3
"""Skybind V9: disposable fixture preparation and fail-closed WebUI X acceptance.

Prepare is *opt-in* and writes only a unique remote subtree and Downloads fixture.
Collect is read-only. Neither mode cancels jobs, reboots, modifies offline edits,
or marks a reload as proof that Android closed and reopened its hosting Activity.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

from api_acceptance import (DeviceRPC, EXCHANGE, OUTROOT, HEX_ID, validated_base,
                            TestBlocked, TestFail)
from boot_journal_gate import GateError, source_info, utc, root, write_json_exclusive, boot_identity
from webview_device_gate import (observe_foreground, host_type, HOSTS, load_receipt_bytes,
                                 select_receipt_source)

KIND = 'SKYBIND_WEBUIX_INTERACTIVE_V9'
QA_ASSET = '/data/adb/modules/skybind/webroot/interactive_qa.js'
ACK = 'I_AUTHORIZE_DISPOSABLE_V9'
NAMES = ('navigation_preview', 'reconnection', 'owned_cancellation', 'read_only_bridge_recovery')
STATES = ('PASS', 'FAIL', 'BLOCKED')
HOME_STATE = Path.home()/'.local/state/skybind-qa-v9'


def digest(v: bytes|str)->str:
    return hashlib.sha256(v.encode() if isinstance(v,str) else v).hexdigest()


def stamp_check(value, *, now=None):
    if not isinstance(value,str):raise GateError('V9 receipt timestamp missing')
    try: parsed=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise GateError('V9 receipt timestamp invalid')
    if parsed.tzinfo is None:raise GateError('V9 timestamp must have timezone')
    age=((now or dt.datetime.now(dt.timezone.utc))-parsed).total_seconds()
    if not -60<=age<=900:raise GateError('V9 receipt is not fresh (max 15 min)')


def check_receipt(value):
    if not isinstance(value,dict) or value.get('schema_version')!=1 or value.get('kind')!=KIND:
        raise GateError('Unsupported V9 interactive receipt')
    stamp_check(value.get('recorded_at_utc'))
    doc=value.get('document_id')
    if not isinstance(doc,str) or not re.fullmatch(r'[A-Za-z0-9-]{4,100}',doc):
        raise GateError('V9 document identity invalid')
    obs=value.get('observations')
    if not isinstance(obs,dict) or any(k not in NAMES for k in obs) or len(obs)>4:
        raise GateError('V9 case names unexpected')
    for k,item in obs.items():
        if not isinstance(item,dict) or item.get('status') not in STATES:
            raise GateError('Invalid V9 case status')
        for key in ('run_id',):
            if key in item and (not isinstance(item[key],str) or not HEX_ID.fullmatch(item[key])):
                raise GateError('V9 owned run identity invalid')
    return obs


def attested_ui_structure(package: str, *, command=root):
    """Android accessibility hierarchy, sanitized in memory. Never persist raw XML."""
    try:
        value=command('/system/bin/uiautomator dump /dev/tty',timeout=20,max_bytes=131072)
        start=value.find('<?xml')
        if start<0: return {'valid_hierarchy':False,'skybind_page':False,'preview_control':False}
        xml=value[start:]
        xml=xml[:xml.rfind('</hierarchy>')+len('</hierarchy>')]
        hierarchy=ET.fromstring(xml)
        nodes=list(hierarchy.iter('node'))
        return {'valid_hierarchy':True,
                'host_package_present':any(n.attrib.get('package')==package for n in nodes),
                'skybind_page':any('Skybind' in n.attrib.get('text','') for n in nodes),
                'preview_control':any(('Preview transfer policy' in n.attrib.get('text','') or
                                        'V9: Interactive device qualification' in n.attrib.get('text',''))
                                       for n in nodes)}
    except (GateError,OSError,ET.ParseError,ValueError):
        return {'valid_hierarchy':False,'skybind_page':False,'preview_control':False}


def root_asset_hash():
    try:
        got=root('if [ -L '+QA_ASSET+' ] || [ ! -f '+QA_ASSET+' ]; then exit 4; fi; /system/bin/sha256sum '+QA_ASSET)
    except GateError:return None
    match=re.fullmatch(r'([a-f0-9]{64})\s+\S+',got)
    return match.group(1) if match else None


def safe_jobs(rpc):
    doc=rpc.call('jobs.status',args={}).get('result')
    if not isinstance(doc,dict) or not isinstance(doc.get('runs'),list):
        raise GateError('authoritative jobs.status.runs missing')
    return {x['id']:x for x in doc['runs'] if isinstance(x,dict) and isinstance(x.get('id'),str)
            and HEX_ID.fullmatch(x['id'])}


def owned_events(rpc, run_id):
    result=rpc.call('operation.events',args={'cursor':0,'limit':64,'operation_id':run_id,'wait_ms':0}).get('result')
    if not isinstance(result,dict) or not isinstance(result.get('events'),list):
        raise GateError('operation.events does not provide an authoritative page')
    events=[e for e in result['events'] if isinstance(e,dict) and
            (e.get('operation_id')==run_id or e.get('run_id')==run_id)]
    return {'cancelled':any(e.get('type')=='job.cancelled' for e in events),
            'progress':sum(e.get('type')=='job.progress' for e in events),
            'terminal':any(e.get('type') in ('job.completed','job.failed','job.cancelled','job.interrupted') for e in events),
            'gap':bool(result.get('gap') or result.get('degraded') or result.get('cursor_reset')),
            'latest_cursor':result.get('latest_cursor')}


def claim_result(obs, *, foreground, asset_matches, ui, jobs, ownership, events, host):
    """Fail closed; independent evidence is stronger than client-reported PASS."""
    rows=[]
    for name in NAMES:
        claim=obs.get(name,{})
        detail={'in_page_status':claim.get('status','BLOCKED')}
        verdict='BLOCKED'
        if claim.get('status')=='FAIL': verdict='FAIL'
        elif not foreground or not asset_matches:
            detail['reason']='foreground Android host and installed QA asset required'
        elif name=='navigation_preview':
            # Stock WebUI controls need to be observable in actual Android UI hierarchy.
            if (claim.get('status')=='PASS' and claim.get('preview_is_readonly_kind') is True and
                claim.get('trusted_navigation') is True and claim.get('trusted_preview') is True and
                claim.get('confirm_enabled') is True and ui.get('host_package_present') and
                ui.get('skybind_page') and ui.get('preview_control')):
                verdict='PASS'
            else:detail['reason']='UI hierarchy, real navigation, or preview confirmation not independently established'
        elif name=='reconnection':
            run_id=claim.get('run_id')
            job=jobs.get(run_id)
            if (claim.get('status')=='PASS' and job and ownership and
                run_id not in ownership.get('baseline_run_ids',[]) and
                events and not events.get('gap')):
                detail['document_reopen_and_authoritative_job']='OBSERVED'
            detail['reason']='Android host actually closing/reopening is not independently observed by this collector'
            # No inference that a document reload is a full host relaunch.
        elif name=='owned_cancellation':
            run_id=claim.get('run_id')
            job=jobs.get(run_id)
            launched=obs.get('navigation_preview',{}).get('trusted_copy_launch') or {}
            matching_paths=bool(ownership and launched.get('trusted_confirm') is True and
                                launched.get('kind')=='copy' and
                                launched.get('source_endpoint_sha256')==ownership.get('source_sha256') and
                                launched.get('destination_endpoint_sha256')==ownership.get('destination_sha256'))
            newly_created=bool(ownership and run_id not in ownership.get('baseline_run_ids',[]))
            if (claim.get('trusted_cancel') and matching_paths and newly_created and job and
                job.get('state')=='CANCELLED' and events and events.get('cancelled')):
                verdict='PASS'
            else:detail['reason']='owned cancellation UI action, exact endpoints or authoritative terminal event missing'
            detail['disposable_workspace_identity_correlated']=matching_paths
        elif name=='read_only_bridge_recovery':
            if (claim.get('status')=='PASS' and claim.get('one_shot_fault_consumed') is True and
                claim.get('ui_recovered') is True and claim.get('mutations_dispatched_during_test')==0 and
                claim.get('replay_cursor_monotonic') is True):
                verdict='PASS'
            else:detail['reason']='one-shot read-only injected callback recovery not fully observed'
            detail['scope']='synthetic read-only callback only; no actual KernelSU outage proof'
        rows.append({'test':name,'status':verdict,'evidence':detail})
    return rows


def prepare(rpc,base,ack,out,mb):
    if ack!=ACK:raise GateError('explicit SKYBIND_QA_ACK=I_AUTHORIZE_DISPOSABLE_V9 required')
    base=validated_base(base)
    if not (1<=mb<=32):raise GateError('fixture size must be 1..32 MiB')
    # Existing configured base must be browsable. Never use remote roots or queued edits.
    listed=rpc.call('remote.list',args={'endpoint':base}).get('result')
    if not isinstance(listed,list):raise GateError('configured disposable parent is not accessible')
    session='skybind_v9_'+secrets.token_hex(8)
    workspace=base+'/'+session
    source=workspace+'/source'
    destination=workspace+'/destination'
    baseline=safe_jobs(rpc)
    for endpoint in (workspace,source,destination):
        proof=rpc.call('remote.mkdir.preview','preview',{'endpoint':endpoint}).get('result')
        if not isinstance(proof,dict) or not isinstance(proof.get('proof'),str):raise GateError('fixture mkdir preview refused')
        result=rpc.call('remote.mkdir.run','run',{'endpoint':endpoint,'proof':proof['proof']}).get('result')
        if not isinstance(result,dict) or result.get('created') is not True:raise GateError('fixture mkdir failed')
    EXCHANGE.mkdir(parents=True,exist_ok=True)
    if EXCHANGE.is_symlink() or not EXCHANGE.is_dir():raise GateError('exchange directory is unsafe')
    folder=EXCHANGE/session/'outgoing'
    folder.mkdir(parents=True,exist_ok=False)
    path=folder/'owned-v9.bin'
    # Generate unpredictable content only under unique disposable Downloads location.
    with path.open('xb') as f:
        for _ in range(mb):f.write(secrets.token_bytes(1024*1024))
    payload={'direction':'upload','remote':source,'local':session+'/outgoing'}
    proof=rpc.call('remote.media.preview','preview',payload).get('result')
    if not isinstance(proof,dict) or not isinstance(proof.get('proof'),str):raise GateError('fixture upload preview refused')
    launched=rpc.call('remote.media.start','run',{**payload,'proof':proof['proof']}).get('result')
    rid=launched.get('id') if isinstance(launched,dict) else None
    if not isinstance(rid,str) or not HEX_ID.fullmatch(rid):raise GateError('fixture upload run identity not produced')
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        job=safe_jobs(rpc).get(rid)
        if job and job.get('state')=='COMPLETED':break
        if job and job.get('state') in ('FAILED','CANCELLED','INTERRUPTED'):
            raise GateError('disposable fixture upload did not complete')
        time.sleep(2)
    else:raise GateError('disposable fixture upload timed out; workspace retained for review')
    # Retain only safe absolute endpoints in PRIVATE, mode 0600.
    receipt={'schema_version':1,'kind':'SKYBIND_V9_OWNERSHIP',
             'session':session,'created_at_utc':utc(),'source':source,'destination':destination,
             'source_sha256':digest(source),'destination_sha256':digest(destination),
             'baseline_run_ids':sorted(set(baseline)|{rid}),
             'fixture_upload_id':rid,'fixture_size_bytes':mb*1024*1024,
             'boot_id_sha256':boot_identity(),'installed_elf_sha256':rpc.installed_binary_hash()}
    HOME_STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    if HOME_STATE.is_symlink():raise GateError('ownership directory cannot be symlink')
    file=HOME_STATE/(session+'.json')
    write_json_exclusive(file,receipt)
    out.mkdir(parents=True,exist_ok=True)
    public={'schema_version':1,'kind':'SKYBIND_V9_FIXTURE_CREATED',
            'session':session,'ownership_file':str(file),
            'source_endpoint_sha256':digest(source),'destination_endpoint_sha256':digest(destination),
            'file_bytes':mb*1024*1024,'auto_cleanup':False,
            'note':'Use ordinary Skybind Remote browser to select these exact disposable paths; do not use offline-queued paths. No test job has been cancelled.'}
    # Only local CLI prints the private endpoint values; do not export to public ZIP.
    public_file=out/('skybind-v9-fixture-'+session+'.json')
    write_json_exclusive(public_file,public)
    print('PREPARED: '+str(public_file))
    print('OWNERSHIP: '+str(file))
    print('Use the private ownership JSON (source/destination fields) to select both disposable folders inside Skybind.')
    return 0


def collect(rpc,receipt_source,host,ownership_file,out):
    if host not in HOSTS or host=='auto':raise GateError('explicit recognized Android host required')
    raw=load_receipt_bytes(select_receipt_source(receipt_source))
    if len(raw)>65536:raise GateError('V9 receipt too large')
    try:doc=json.loads(raw)
    except ValueError:raise GateError('V9 receipt is not JSON')
    observations=check_receipt(doc)
    ownership=None
    if ownership_file:
        p=Path(ownership_file).expanduser().resolve()
        if HOME_STATE.resolve() not in p.parents or p.is_symlink():
            raise GateError('ownership evidence must be a regular file under private V9 state')
        if p.stat().st_size>16384:raise GateError('ownership receipt oversized')
        ownership=json.loads(p.read_text())
        if ownership.get('kind')!='SKYBIND_V9_OWNERSHIP':raise GateError('ownership file unsupported')
        if (ownership.get('boot_id_sha256')!=boot_identity() or
            ownership.get('installed_elf_sha256')!=rpc.installed_binary_hash()):
            raise GateError('ownership evidence belongs to a different boot or installed ELF')
    print('V9 receipt verified. Return to Skybind inside your real WebUI X host.',flush=True)
    foreground,fg=observe_foreground(host)
    src=Path(__file__).resolve().parents[3]/'module/webroot/interactive_qa.js'
    installed=root_asset_hash()
    matched=bool(installed and src.is_file() and digest(src.read_bytes())==installed)
    ui=attested_ui_structure(host) if foreground else {}
    jobs=safe_jobs(rpc)
    run_id=(observations.get('owned_cancellation') or observations.get('reconnection') or {}).get('run_id')
    events=owned_events(rpc,run_id) if run_id and HEX_ID.fullmatch(run_id) else None
    rows=claim_result(observations,foreground=foreground,asset_matches=matched,ui=ui,
                      jobs=jobs,ownership=ownership,events=events,host=host)
    counts={state:sum(x['status']==state for x in rows) for state in STATES}
    session=secrets.token_hex(16)
    report={'schema_version':1,'kind':'SKYBIND_WEBUIX_V9_RAW_GATE','captured_at_utc':utc(),
            'qualification':'RAW_UNATTESTED_NOT_RELEASE_QUALIFIED',
            'source':source_info(),'selected_host_package_sha256':digest(host),
            'host_type':host_type(host),'foreground':fg,'installed_qa_js_sha256':installed,
            'asset_matches_source':matched,'installed_binary_sha256':rpc.installed_binary_hash(),
            'android_accessibility':ui,'receipt_sha256':digest(raw),
            'ownership_session_sha256':digest(ownership['session']) if ownership else None,
            'cases':rows,'counts':counts,'limitations':[
                'No release seal or host APK signing attestation',
                'Document reload is not proof of host Activity closure',
                'Synthetic read-only injected callback is not an actual ksu.exec outage',
                'No backend operation is cancelled or started by this collector',
                'Exact remote paths, credentials, raw accessibility XML, and queued edits are never exported']}
    out.mkdir(parents=True,exist_ok=True)
    dest=out/('skybind-webuix-v9-'+session+'.json')
    write_json_exclusive(dest,report)
    with zipfile.ZipFile(dest.with_suffix('.zip'),'x',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(dest,arcname=dest.name)
    print('REPORT: '+str(dest)+'\nCOUNTS: '+str(counts))
    return 1 if counts['FAIL'] else 0


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','collect'))
    p.add_argument('--remote-base',default=os.getenv('SKYBIND_QA_REMOTE_BASE'))
    p.add_argument('--ack',default=os.getenv('SKYBIND_QA_ACK'))
    p.add_argument('--fixture-mib',type=int,default=8)
    p.add_argument('--receipt-file',default=os.getenv('SKYBIND_QA_V9_RECEIPT'))
    p.add_argument('--host-package',default=os.getenv('SKYBIND_QA_WEBVIEW_HOST'))
    p.add_argument('--ownership-file',default=os.getenv('SKYBIND_QA_V9_OWNERSHIP'))
    p.add_argument('--output-dir',type=Path,default=OUTROOT)
    a=p.parse_args(argv)
    try:
        rpc=DeviceRPC()
        if a.mode=='prepare':return prepare(rpc,a.remote_base or '',a.ack,a.output_dir,a.fixture_mib)
        return collect(rpc,a.receipt_file,a.host_package,a.ownership_file,a.output_dir)
    except (GateError,TestFail,TestBlocked,OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as e:
        print('V9 GATE BLOCKED: '+str(e)[:190],file=sys.stderr);return 3
    except Exception:
        print('V9 GATE BLOCKED: unexpected error (private details suppressed)',file=sys.stderr);return 3

if __name__=='__main__':sys.exit(main())
