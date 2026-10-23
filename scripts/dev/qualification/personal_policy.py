#!/usr/bin/env python3
"""Skybind personal release authority. Local evidence + explicit owner decision.

No independent signatures, external custody, four-manager matrix, or fake tests.
Approval is a scope-limited owner decision, not a security certification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
STATE = Path.home()/'.local/state/skybind/personal-release'
BASE_SHA = 'b46d2d57d1029971e0dcce731782b607ccf9ca7b'
GATES = tuple(f'SB-G{i:02d}' for i in range(1, 9))
EVIDENCE_KEYS = ('q16', 'q17', 'r1', 'm2m3')
MAX_JSON = 512_000
HEX64 = re.compile(r'^[0-9a-f]{64}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
MANAGERS = ('kernelsu', 'kernelsu-next', 'magisk', 'apatch', 'other')

class Rejected(Exception): pass

def sha(b: bytes) -> str: return hashlib.sha256(b).hexdigest()
def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def need(ok, code):
    if not ok: raise Rejected(code)
def safe_json(path: Path) -> tuple[dict,str]:
    need(not path.is_symlink() and path.is_file() and 1 <= path.stat().st_size <= MAX_JSON,
         'UNSAFE_OR_MISSING_EVIDENCE:'+path.name)
    raw=path.read_bytes()
    try: data=json.loads(raw)
    except (ValueError,UnicodeError) as e: raise Rejected('INVALID_JSON:'+path.name) from e
    need(isinstance(data,dict),'EVIDENCE_NOT_OBJECT:'+path.name)
    return data,sha(raw)
def git(root:Path,*args:str)->str:
    try:p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,timeout=15,check=False)
    except (OSError,subprocess.TimeoutExpired) as e: raise Rejected('GIT_UNAVAILABLE') from e
    need(p.returncode==0,'GIT_'+args[0].upper()+'_FAILED')
    return p.stdout.strip()
def source(root:Path)->dict:
    need(root.is_dir() and not root.is_symlink(), 'UNSAFE_SOURCE_ROOT')
    head=git(root,'rev-parse','HEAD')
    need(bool(HEX40.fullmatch(head)), 'SOURCE_COMMIT_INVALID')
    need(not git(root,'status','--porcelain','--untracked-files=normal'), 'DIRTY_SOURCE')
    # An overlay can change the gate tooling without changing these actual product files.
    paths=['docs/contracts/typed-operations.json','internal/control/operations.json',
           'internal/control/control.go','internal/control/catalog.go','internal/daemon/wiring.go',
           'internal/mounts/config/config.go','internal/previewproof/proof.go',
           'internal/journal/journal.go','cmd/skybind/main.go']
    hashes={}
    for rel in paths:
        p=root/rel
        need(p.is_file() and not p.is_symlink(),'SOURCE_FILE_MISSING:'+rel)
        hashes[rel]=digest(p)
    need(hashes[paths[0]]==hashes[paths[1]],'TYPED_CATALOG_BYTES_DIFFER')
    catalog=json.loads((root/paths[1]).read_bytes())
    need(catalog.get('total')==57 and len(catalog.get('operations',[]))==57,'OPERATIONS_NOT_57')
    lock=root/'scripts/dev/runtime/source.lock.json'
    ld,hashlock=safe_json(lock)
    need(isinstance(ld.get('newfuture'),dict) and isinstance(ld.get('bclone'),dict),'INVALID_SOURCE_LOCK')
    need(bool(HEX64.fullmatch(str(ld['newfuture'].get('archive_sha256','')))),'NEWFUTURE_PIN_MISSING')
    need(bool(HEX40.fullmatch(str(ld['bclone'].get('commit','')))),'BCLONE_PIN_MISSING')
    return {'commit':head,'source_hashes':hashes,'lock_sha256':hashlock,
            'bclone_commit':ld['bclone']['commit'],'newfuture_asset_sha256':ld['newfuture']['archive_sha256']}

def state_root(root:Path,folder:Path)->Path:
    parent=folder.parent
    need(not folder.is_symlink() and not parent.is_symlink(),'STATE_SYMLINK')
    need(not folder.resolve().is_relative_to(root.resolve()),'STATE_INSIDE_SOURCE')
    return folder

def read_setup(root:Path,folder:Path)->dict:
    state_root(root,folder)
    p=folder/'evidence.json'
    if not p.exists():return {'schema_version':1,'paths':{},'sha256':{}}
    doc,_=safe_json(p)
    need(doc.get('schema_version')==1 and isinstance(doc.get('paths'),dict) and
         isinstance(doc.get('sha256'),dict),'INVALID_PERSONAL_EVIDENCE_INDEX')
    return doc

def load_evidence(root:Path,folder:Path)->tuple[dict,dict,list[str]]:
    index=read_setup(root,folder); docs={}; hashes={};fail=[]
    for key in EVIDENCE_KEYS:
        name=index['paths'].get(key)
        if not isinstance(name,str) or not name:
            fail.append('EVIDENCE_NOT_CONFIGURED_'+key.upper());continue
        try:
            path=Path(name)
            need(path.is_absolute(),'EVIDENCE_PATH_NOT_ABSOLUTE')
            need(not path.resolve().is_relative_to(root.resolve()),'EVIDENCE_INSIDE_REPO')
            doc,h=safe_json(path)
            need(index['sha256'].get(key)==h,'EVIDENCE_CHANGED_'+key.upper())
            docs[key]=doc;hashes[key]=h
        except (Rejected,OSError,ValueError) as e:fail.append(str(e)[:120])
    return docs,hashes,fail

def verify_q16(doc:dict,s:dict)->bool:
    lanes=doc.get('lanes',{})
    if not (doc.get('campaign')=='SB-Q16' and
        doc.get('status')=='TWO_REAL_PROVIDER_LANES_VERIFIED_RAW_NOT_INDEPENDENTLY_ATTESTED' and
        doc.get('source_lock_sha256')==s['lock_sha256'] and
        bool(HEX40.fullmatch(str(doc.get('run',{}).get('commit','')))) and
        isinstance(lanes,dict) and set(lanes)=={'A','B'}):return False
    a,b=lanes['A'],lanes['B']
    if not(isinstance(a,dict) and isinstance(b,dict) and a.get('job_id')!=b.get('job_id')
           and all(type(x.get('job_id')) is int for x in (a,b))):return False
    for key in ('official_asset_sha256','source_build_binary_sha256'):
        if a.get(key)!=b.get(key) or not HEX64.fullmatch(str(a.get(key,''))):return False
    if a['official_asset_sha256']!=s['newfuture_asset_sha256']:return False
    pa,pb=a.get('provider_packages'),b.get('provider_packages')
    if not(isinstance(pa,dict) and isinstance(pb,dict) and set(pa)=={'bclone','newfuture'} and pa==pb):return False
    if not all(HEX64.fullmatch(str(h)) for h in pa.values()):return False
    comp=doc.get('comparison',{})
    return (comp.get('status')=='BYTE_IDENTICAL_UNATTESTED' and
            comp.get('source_commit')==s['bclone_commit'] and
            comp.get('bclone.zip_sha256')==pa['bclone'] and
            comp.get('newfuture.zip_sha256')==pa['newfuture'])

def verify_q17(doc:dict,s:dict)->bool:
    ids=doc.get('run_ids')
    return (doc.get('campaign')=='SB-Q17' and
            doc.get('status')=='TWO_FRESH_RAW_NEGATIVE_RUNS_VERIFIED_NOT_INDEPENDENT' and
            doc.get('case_count')==10 and isinstance(ids,list) and len(ids)==2 and
            len(set(ids))==2 and all(re.fullmatch('[0-9a-f]{32}',str(k)) for k in ids) and
            bool(HEX40.fullmatch(str(doc.get('source_commit','')))) and doc.get('source_hashes')==s['source_hashes'])

def verify_r1(doc:dict)->bool:
    names=('no_token','positive_capabilities','positive_version','positive_remotes',
           'positive_list','positive_size','wrong_operation','wrong_remote','wrong_path',
           'wrong_process','revocation','expiry')
    return (doc.get('schema')=='skybind-r1-bkx-device-consolidated-v1' and
            doc.get('state')=='PASS_R1_BKX_AND_CHROOTCTL_NARROW_LIVE_ACCEPTANCE_ONLY' and
            doc.get('remote')=='GDDavys' and
            isinstance(doc.get('bkx_test_cases'),dict) and
            set(doc['bkx_test_cases'])==set(names) and all(x=='PASS' for x in doc['bkx_test_cases'].values()) and
            all(doc.get(x) is True for x in ('bkx_five_positive_machine_qualified',
                 'bkx_debug_separate_process_replay_qualified','bkx_live_kernel_peer_attested',
                 'bkx_negative_socket_qualified','chrootctl_nine_security_cases_qualified')))

def verify_m2(doc:dict)->bool:
    expected={
       'live':'PASS_M2_L1_LIVE_READ_BROWSE_REBIND','ui-live':'PASS_M2_L2_LIVE_UI_READONLY_RECOVERY',
       'negative-live':'PASS_M2_L3_READONLY_NEGATIVE_BOUNDARIES',
       'transport-live':'PASS_M2_L3_APP_OWNED_TRANSPORT_RECOVERY',
       'm3-preview-live':'PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
       'm3-execute-live':'PASS_M3_DISPOSABLE_CHECK_COMPLETION',
       'm3-cancel-live':'PASS_M3_DISPOSABLE_OWNED_CANCEL',
       'm3-copy-live':'PASS_M3_DISPOSABLE_COPY_RECONCILED',
       'm2-process-live':'PASS_M2_L3_APP_PROCESS_COLD_LAUNCH'}
    cases=doc.get('cases',{})
    if not (doc.get('schema')=='skybind-m2-m3-fresh-batch-v1' and
        doc.get('state')=='PASS_M2_M3_FRESH_NINE_LANE_AUTOMATED_RETEST_ONLY' and
        type(doc.get('github_run_id')) is int and doc['github_run_id']>0 and
        bool(HEX40.fullmatch(str(doc.get('source_sha','')))) and doc.get('installed_pair_verified') is True and
        doc.get('m2_m3_device_retests_run') is True and isinstance(cases,dict) and set(cases)==set(expected)):
        return False
    if not all(isinstance(cases[k],dict) and cases[k].get('state')==v for k,v in expected.items()):return False
    pre=doc.get('copy_preflight');post=doc.get('copy_integrity')
    return (isinstance(pre,dict) and isinstance(post,dict) and pre.get('source_verified') is True and
            post.get('destination_verified') is True and post.get('sentinel_preserved') is True and
            pre.get('expected_content_sha256')==post.get('expected_content_sha256'))

def product_compatible(root:Path,s:dict,docs:dict)->bool:
    """Do not reuse Android acceptance after changes to shipped product behavior."""
    q16,q17,m2=(docs.get(k,{}) for k in ('q16','q17','m2m3'))
    a=q16.get('run',{}).get('commit');b=q17.get('source_commit');c=m2.get('source_sha')
    if not (isinstance(a,str) and a==b==c and HEX40.fullmatch(a)):
        return False
    if s['commit']==a:return True
    try:
        # Frozen original evidence may be reused across qualification-tooling edits,
        # but never after shipped module, daemon, Android or WebUI changes.
        p=subprocess.run(['git','-C',str(root),'diff','--quiet',a,s['commit'],'--',
             'cmd','internal','module','android','apps','docs/contracts',
             'scripts/dev/runtime','scripts/dev/android'],capture_output=True,timeout=20,check=False)
        return p.returncode==0
    except (OSError,subprocess.TimeoutExpired):return False

def candidate_info(path:Path)->dict:
    need(path.is_file() and not path.is_symlink() and 100 < path.stat().st_size <= 512*1024*1024,
         'PERSONAL_CANDIDATE_UNSAFE')
    need(path.suffix=='.zip' and path.name in ('Skybind-bclone-PERSONAL.zip',
           'Skybind-newfuture-PERSONAL.zip'),'PERSONAL_CANDIDATE_NAME_INVALID')
    sys.path.insert(0,str(ROOT/'scripts/dev/release'))
    import skybind_release
    info=skybind_release.verify_release(path)
    provider='bclone' if path.name.startswith('Skybind-bclone') else 'newfuture'
    need(info.get('runtime_provider')==provider,'CANDIDATE_PROVIDER_MISMATCH')
    return {'path':str(path.resolve()),'sha256':digest(path),'provider':provider,
            'format_verified':True}

def read_approval(root:Path,folder:Path)->dict|None:
    p=folder/'owner-approval.json'
    if not p.exists():return None
    data,_=safe_json(p)
    return data

def assess(root:Path=ROOT, folder:Path=STATE)->dict:
    errs=[];gates={k:{'status':'PENDING_PERSONAL_CHECK','evidence':'NOT_CLAIMED'} for k in GATES}
    try:s=source(root)
    except (Rejected,ValueError,OSError,KeyError,TypeError) as e:
        s=None;errs.append(str(e))
    try:docs,hashes,fail=load_evidence(root,folder)
    except (Rejected,OSError,ValueError) as e:docs={};hashes={};fail=[str(e)]
    errs+=fail
    if s:
        for key,validator,gate in (('q16',lambda d:verify_q16(d,s),'SB-G01'),
                                   ('q17',lambda d:verify_q17(d,s),'SB-G02'),
                                   ('r1',verify_r1,'SB-G06'),('m2m3',verify_m2,'SB-G05')):
            if key in docs:
                if validator(docs[key]):gates[gate]={'status':'PERSONAL_EVIDENCE_PASS','evidence':key}
                else: errs.append('EVIDENCE_CONTENT_INVALID_'+key.upper())
    if s and all(k in docs for k in EVIDENCE_KEYS) and not product_compatible(root,s,docs):
        errs.append('PRODUCT_CHANGED_SINCE_ACCEPTANCE_EVIDENCE')
        for g in ('SB-G01','SB-G02','SB-G05','SB-G06'):
            gates[g]={'status':'PENDING_PERSONAL_CHECK','evidence':'PRODUCT_SOURCE_DRIFT'}
    approved=None
    try:approved=read_approval(root,folder)
    except (Rejected,OSError,ValueError) as e:errs.append('OWNER_APPROVAL_INVALID:'+str(e))
    owner_valid=False;candidate=None
    if approved:
        try:
            need(approved.get('schema_version')==1 and approved.get('policy')=='SKYBIND_PERSONAL_V1',
                 'OWNER_POLICY_INVALID')
            need(s is not None and approved.get('source_commit')==s['commit'] and
                 approved.get('source_hashes')==s['source_hashes'],'OWNER_SOURCE_DRIFT')
            need(approved.get('evidence_sha256')==hashes and set(hashes)==set(EVIDENCE_KEYS),
                 'OWNER_EVIDENCE_DRIFT')
            need(approved.get('manager') in MANAGERS,'OWNER_MANAGER_INVALID')
            need(approved.get('scope')=='PERSONAL_SINGLE_DEVICE' and
                 approved.get('owner_accepts_untested_configurations') is True and
                 approved.get('ui_reviewed') is True and approved.get('device_reviewed') is True,
                 'OWNER_ACKNOWLEDGEMENTS_MISSING')
            cp=Path(approved['candidate']['path'])
            candidate=candidate_info(cp)
            need(candidate['sha256']==approved['candidate']['sha256'] and
                 candidate['provider']==approved['candidate']['provider'],'OWNER_CANDIDATE_DRIFT')
            need(all(gates[k]['status']=='PERSONAL_EVIDENCE_PASS' for k in ('SB-G01','SB-G02','SB-G05','SB-G06')),
                 'OWNER_FIRST_PARTY_EVIDENCE_NOT_READY')
            owner_valid=True
        except (Rejected,ValueError,OSError,KeyError,TypeError) as e:errs.append('OWNER_APPROVAL_REJECTED:'+str(e))
    if owner_valid:
        for gate in ('SB-G03','SB-G04','SB-G07','SB-G08'):
            gates[gate]={'status':'PERSONAL_OWNER_ACCEPTED','evidence':'explicit_owner_scope'}
    # Preserve the meaning of safety evidence. G03/04/07/08 acceptance is a
    # personal choice, not independently verified system behavior.
    approved_status=owner_valid and s is not None and not errs and all(
        v['status'] in ('PERSONAL_EVIDENCE_PASS','PERSONAL_OWNER_ACCEPTED') for v in gates.values())
    return {'schema_version':1,'policy':'SKYBIND_PERSONAL_V1',
            'status':'PERSONAL_RELEASE_APPROVED' if approved_status else 'PERSONAL_RELEASE_PENDING',
            'source_commit':s['commit'] if s else None,
            'source_base_for_historical_receipts':docs.get('q17',{}).get('source_commit'),
            'gate_checks':gates,'evidence_sha256':hashes,
            'candidate':candidate if owner_valid else None,
            'owner_approval':owner_valid,'personal_scope_only':True,
            'independent_certification_claimed':False,
            'untested_managers_not_qualified':True,
            'reasons':sorted(set(errs+(['OWNER_APPROVAL_REQUIRED'] if not owner_valid else [])))}

def write_private(folder:Path,name:str,data:dict)->None:
    need(not folder.is_symlink(),'STATE_DIR_SYMLINK')
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    need(folder.stat().st_mode & 0o077==0,'STATE_DIR_PERMISSIONS_UNSAFE')
    p=folder/name
    need(not p.exists() and not p.is_symlink(),'STATE_FILE_ALREADY_EXISTS:'+name)
    with p.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
    p.chmod(0o600)

def configure(root:Path,folder:Path,paths:dict)->dict:
    state_root(root,folder)
    # Never configure an index from untrusted links or mismatching contents.
    s=source(root)
    docs={};hashes={}
    for key in EVIDENCE_KEYS:
        path=paths[key]
        need(path.is_absolute(),'EVIDENCE_NOT_ABSOLUTE_'+key)
        need(not path.resolve().is_relative_to(root.resolve()),'EVIDENCE_INSIDE_SOURCE_'+key)
        docs[key],hashes[key]=safe_json(path)
    need(verify_q16(docs['q16'],s),'Q16_EVIDENCE_INVALID')
    need(verify_q17(docs['q17'],s),'Q17_EVIDENCE_INVALID')
    need(verify_r1(docs['r1']),'R1_EVIDENCE_INVALID')
    need(verify_m2(docs['m2m3']),'M2M3_EVIDENCE_INVALID')
    need(product_compatible(root,s,docs),'PRODUCT_CHANGED_SINCE_ACCEPTANCE_EVIDENCE')
    index={'schema_version':1,'policy':'SKYBIND_PERSONAL_V1',
           'paths':{k:str(paths[k].resolve()) for k in EVIDENCE_KEYS},'sha256':hashes}
    write_private(folder,'evidence.json',index)
    return {'status':'PERSONAL_EVIDENCE_CONFIGURED','evidence_sha256':hashes}

def approve(root:Path,folder:Path,candidate:Path,manager:str,ui:bool,device:bool,ack:bool)->dict:
    need(ack,'EXPLICIT_PERSONAL_APPROVAL_REQUIRED')
    need(ui and device,'EXPLICIT_UI_AND_DEVICE_REVIEW_REQUIRED')
    baseline=assess(root,folder)
    need(baseline['source_commit'] is not None and all(
        baseline['gate_checks'][k]['status']=='PERSONAL_EVIDENCE_PASS'
        for k in ('SB-G01','SB-G02','SB-G05','SB-G06')),
        'FIRST_PARTY_EVIDENCE_INCOMPLETE')
    need(manager in MANAGERS,'PERSONAL_MANAGER_UNKNOWN')
    info=candidate_info(candidate)
    s=source(root)
    obj={'schema_version':1,'policy':'SKYBIND_PERSONAL_V1',
        'approved_utc':datetime.now(timezone.utc).isoformat(),
        'source_commit':s['commit'],'source_hashes':s['source_hashes'],
        'evidence_sha256':baseline['evidence_sha256'],
        'candidate':info,'scope':'PERSONAL_SINGLE_DEVICE','manager':manager,
        'ui_reviewed':ui,'device_reviewed':device,
        'owner_accepts_untested_configurations':True,
        'owner_statement':'I accept this exact candidate for personal use on my reviewed device; other managers/devices are untested.',
        'third_party_attestation':False}
    write_private(folder,'owner-approval.json',obj)
    return assess(root,folder)

def main(argv=None)->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repository',type=Path,default=ROOT)
    p.add_argument('--state-dir',type=Path,default=STATE)
    sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('check')
    conf=sub.add_parser('configure')
    for k in EVIDENCE_KEYS:conf.add_argument('--'+('m2-m3' if k=='m2m3' else k),type=Path,required=True,dest=k)
    a=sub.add_parser('approve')
    a.add_argument('--candidate',type=Path,required=True)
    a.add_argument('--manager',choices=MANAGERS,required=True)
    a.add_argument('--ui-reviewed',action='store_true')
    a.add_argument('--device-reviewed',action='store_true')
    a.add_argument('--accept-personal-scope',action='store_true')
    o=p.parse_args(argv)
    try:
        if o.action=='check':result=assess(o.repository,o.state_dir)
        elif o.action=='configure':result=configure(o.repository,o.state_dir,{k:getattr(o,k) for k in EVIDENCE_KEYS})
        else:result=approve(o.repository,o.state_dir,o.candidate,o.manager,o.ui_reviewed,
                            o.device_reviewed,o.accept_personal_scope)
        print(json.dumps(result,sort_keys=True,indent=2))
        return 0 if result['status'] in ('PERSONAL_RELEASE_APPROVED','PERSONAL_EVIDENCE_CONFIGURED') else 3
    except (Rejected,OSError,ValueError,TypeError,KeyError,ImportError) as e:
        print(json.dumps({'status':'PERSONAL_RELEASE_BLOCKED','reason':str(e)[:240]},sort_keys=True))
        return 3
if __name__=='__main__':raise SystemExit(main())
