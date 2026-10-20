#!/usr/bin/env python3
"""Independently updateable BKX/chrootctl R0 source/declaration audit.

This NEVER confers runtime access or claims rclone compatibility. Historical source
hashes serve provenance only; independent consumer updates are checked against
stable capability contracts without pinning a Skybind executable/source build.
"""
from __future__ import annotations
from pathlib import Path
import argparse
import hashlib
import json

ROOT=Path(__file__).resolve().parents[3]
MANIFEST=ROOT/'docs/contracts/rclone-compat/M3_CONSUMER_CONFORMANCE.json'
ABI=ROOT/'docs/contracts/rclone-compat/SKYBIND_CONSUMER_ABI_V1.json'

class ContractError(ValueError): pass

def require(predicate, code):
    if not predicate: raise ContractError(code)

def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_source(source:Path, expected, strict_reference_sha=False):
    """Best-effort historical source layout check; no trusted process claim.

    A consumer refactor may move code. In that case its independently maintained
    ABI declaration can be checked instead; Skybind itself need not be rebuilt.
    """
    out={}
    for rel,item in expected.items():
        path=source/rel
        require(path.is_file() and not path.is_symlink(), 'CONSUMER_SOURCE_UNAVAILABLE:'+rel)
        data=path.read_bytes()
        sha=hashlib.sha256(data).hexdigest()
        require(all(word.encode() in data for word in item['tokens']), 'CONSUMER_SOURCE_CONTRACT_CHANGED:'+rel)
        if strict_reference_sha:
            require(sha==item['sha256'], 'HISTORICAL_SOURCE_SHA_MISMATCH:'+rel)
        out[rel]={'observed_sha256':sha,'reference_sha256':item['sha256'],
                  'matches_reference':sha==item['sha256'],'structural_tokens_seen':True}
    return out

def verify_declaration(file:Path, abi, consumers):
    require(file.is_file() and not file.is_symlink() and file.stat().st_size<32768,
            'CONSUMER_DECLARATION_UNAVAILABLE')
    data=json.loads(file.read_text())
    require(type(data) is dict and data.get('schema')=='skybind-rclone-consumer-request-v1',
            'CONSUMER_DECLARATION_SCHEMA')
    consumer=data.get('consumer')
    require(consumer in ('bkx','chrootctl'), 'UNKNOWN_CONSUMER')
    require(type(data.get('abi_major')) is int and data['abi_major']==abi['abi_major'],
            'CONSUMER_ABI_MAJOR_INCOMPATIBLE')
    require(type(data.get('required_operations')) is list and data['required_operations'] and
            all(type(x) is str for x in data['required_operations']) and
            len(set(data['required_operations']))==len(data['required_operations']),
            'CONSUMER_OPERATIONS_INVALID')
    declared=set(data['required_operations'])
    require(declared.issubset(set(consumers[consumer]['required_commands'])),
            'UNREVIEWED_CONSUMER_COMMAND')
    require(data.get('native_rclone_fallback') is True,
            'NATIVE_RCLONE_MUST_REMAIN_AVAILABLE')
    require(data.get('implicit_credential_export') is False,
            'CREDENTIAL_EXPORT_PROHIBITED')
    # Compare requested features against the published stable ABI; false/absent
    # means a separate adapter/broker milestone must be implemented first.
    supported=set(abi['available_external_capabilities'])
    required_caps=data.get('required_capabilities',[])
    require(type(required_caps) is list and all(type(x) is str for x in required_caps)
            and len(set(required_caps))==len(required_caps), 'CONSUMER_CAPABILITIES_INVALID')
    unsupported=sorted(set(required_caps)-supported)
    return {'consumer':consumer, 'declaration_sha256':fingerprint(file),
            'abi_major':abi['abi_major'], 'requested_capabilities':required_caps,
            'unsupported_capabilities':unsupported,
            'ready_for_runtime_conformance':not unsupported,
            'runtime_qualified':False,'source_build_required':False,
            'status':'BLOCKED_CAPABILITY_NOT_IMPLEMENTED' if unsupported else 'PASS_DECLARATION_ONLY'}

def verify(source:Path|None=None, strict_reference_sha=False,
           declarations:list[Path]|None=None):
    doc=json.loads(MANIFEST.read_text())
    abi=json.loads(ABI.read_text())
    require(doc['schema']=='skybind-m3-consumers-r0-v1' and doc['cfs1_operation_count']==57,
            'BASE_CONTRACT_INVALID')
    require(doc['consumer_access']=='NOT_IMPLEMENTED_NOT_AUTHORIZED',
            'UNEXPECTED_CONSUMER_ACCESS')
    require(abi['schema']=='skybind-rclone-consumer-abi-v1' and abi['abi_major']==1,
            'ABI_CONTRACT_INVALID')
    require(abi['external_transport_status']=='NOT_IMPLEMENTED',
            'UNREVIEWED_EXTERNAL_TRANSPORT')
    require(abi['available_external_capabilities']==[],
            'UNREVIEWED_EXTERNAL_CAPABILITY')
    for client in ('bkx','chrootctl'):
        require(doc[client]['native_rclone_retained'], 'NATIVE_RCLONE_REQUIRED')
        require(all(doc[client]['milestones'][k]=='UNQUALIFIED'
                    for k in ('R1','R2','R3','R4','R5','R6')),
                'EXTERNAL_QUALIFICATION_NOT_ESTABLISHED')
    checked=verify_source(source,doc['chrootctl']['verified_sources'],strict_reference_sha) if source else {}
    declarations_out=[verify_declaration(d,abi,doc) for d in (declarations or [])]
    overall=('BLOCKED_CONSUMER_CAPABILITY' if any(d['unsupported_capabilities']
             for d in declarations_out) else 'PASS_R0_SOURCE_CONTRACT_ONLY')
    return {'status':overall,
            'consumer_abi_major':abi['abi_major'],
            'source_audit':checked,'declarations':declarations_out,
            'bkx_runtime_qualified':False,'chrootctl_runtime_qualified':False,
            'shared_credential_access':False,'external_rclone_compatible':False,
            'source_build_required_for_consumer_update':False,
            'release_qualified':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--chrootctl-source',type=Path)
    p.add_argument('--strict-reference-sha',action='store_true',
                   help='Historical reference comparison only; not an upgrade prerequisite')
    p.add_argument('--consumer-declaration',type=Path,action='append',default=[])
    args=p.parse_args()
    try:
        report=verify(args.chrootctl_source,args.strict_reference_sha,args.consumer_declaration)
        print(json.dumps(report,sort_keys=True))
        if report['status']=='BLOCKED_CONSUMER_CAPABILITY': raise SystemExit(2)
    except (ContractError, OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps({'status':'BLOCKED','reason':str(e)[:160]},sort_keys=True))
        raise SystemExit(2)
