#!/usr/bin/env python3
"""SB-Q04P2 immutable selection contract, NOT source authentication or G01 attestation.

The user selected the official NewFuture prebuilt for UNATTESTED test builds.
Its +dirty, unsigned/no custody receipt limitations are never reclassified as trusted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
LOCK = ROOT/'scripts/dev/runtime/source.lock.json'
SELECTION = ROOT/'scripts/dev/runtime/source.selection.json'
NEWFUTURE_SHA='04ebfcc8c21c9583b7d4c723e2e69c1d3bbbd24432f6728ffbc2947e5282aa43'
BCLONE_COMMIT='7b63b1a4cc9d13465721ebbfc96f2f9bd810f600'
GO='1.27.2'
NDK='28.2.13676358'

class Rejected(ValueError):pass

def canonical(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=True)+'\n').encode()

def read_regular(path):
    if path.is_symlink() or not path.is_file():raise Rejected('selection/lock missing, symlink or nonregular file')
    def no_duplicates(items):
        out={}
        for k,v in items:
            if k in out:raise Rejected('duplicate JSON key in selected inputs')
            out[k]=v
        return out
    try:return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=no_duplicates)
    except (OSError,ValueError) as exc:raise Rejected('selection/lock invalid JSON') from exc

def verify(lock_path=LOCK, selection_path=SELECTION):
    lock=read_regular(Path(lock_path));sel=read_regular(Path(selection_path))
    nf=lock.get('newfuture',{});bc=lock.get('bclone',{})
    if lock.get('schema')!=1 or set(lock)!={'schema','newfuture','bclone'}:
        raise Rejected('source lock schema/fields mismatch')
    if nf!={'repository':'NewFuture/rclone-fuse3-magisk','tag':'v1.75.0',
             'asset':'magisk-rclone_arm64-v8a.zip','archive_sha256':NEWFUTURE_SHA}:
        raise Rejected('NewFuture pinned upstream archive identity drift')
    if bc!={'repository':'BenjiThatFoxGuy/bclone','commit':BCLONE_COMMIT,
             'ndk_revision':NDK,'go_version':GO}:
        raise Rejected('bclone revision/compiler pin drift')
    if sel.get('schema_version')!=1 or sel.get('kind')!='SB_Q04P2_OPERATOR_SELECTED_BUILD_INPUTS' or sel.get('status')!='INPUTS_SELECTED_UNATTESTED':
        raise Rejected('invalid selection identity/status')
    if sel.get('source_lock_canonical_sha256')!=hashlib.sha256(canonical(lock)).hexdigest():
        raise Rejected('selection contract does not bind the exact source lock')
    if sel.get('authorization_scope')!='UNATTESTED_CI_BUILDS_ONLY' or sel.get('user_choice')!='USE_OFFICIAL_NEWFUTURE_PREBUILT_NO_SOURCE_REBUILD':
        raise Rejected('selection authorization scope changed')
    n=sel.get('newfuture',{});b=sel.get('bclone',{});t=sel.get('toolchain',{});e=sel.get('evidence_reference',{})
    if (n.get('repository'),n.get('tag'),n.get('asset'),n.get('sha256'),n.get('github_asset_id'))!=(nf['repository'],nf['tag'],nf['asset'],NEWFUTURE_SHA,499099249):
        raise Rejected('prebuilt origin/asset identity changed')
    if (n.get('prebuilt_only'),n.get('rebuild_permitted'),n.get('reported_vcs_modified'),n.get('release_immutable_at_intake'),n.get('binary_custody'))!=(True,False,True,False,'UNATTESTED_PROVENANCE_LIMITATION_ACCEPTED_FOR_TEST_BUILDS_ONLY'):
        raise Rejected('NewFuture provenance limitation or prebuilt-only policy weakened')
    if (b.get('repository'),b.get('commit'),b.get('github_signature'),b.get('source_dependency_review'),b.get('build_strategy'))!=(bc['repository'],BCLONE_COMMIT,'UNSIGNED','PENDING_EXTERNAL_REVIEW','PINNED_SOURCE_INDEPENDENT_LANES'):
        raise Rejected('unsigned bclone identity or review boundary changed')
    if (t.get('go_version'),t.get('ndk_revision'),t.get('android_api'),t.get('download_integrity'),t.get('authenticated_packages'))!=(GO,NDK,21,'TO_BE_RECORDED_BY_REAL_CI',False):
        raise Rejected('toolchain verification incorrectly promoted or changed')
    if (e.get('workflow_run_id'),e.get('class'),e.get('reconciliation'),e.get('evidence_manifest_sha256'))!=(38099529777,'RAW_UNATTESTED','CONSISTENT_UNATTESTED','7fc44a839a5272f346b246f944326e31e340acd08592ea0f3e188ddd48f969eb'):
        raise Rejected('unattested evidence identity changed')
    if (sel.get('independent_attestation'),sel.get('real_builds_executed'),sel.get('android_device_tested'),sel.get('gate_g01'),sel.get('other_gates'),sel.get('final_seal'))!=(False,False,False,'BLOCKED','BLOCKED','NOT_ISSUED'):
        raise Rejected('selection must never assert attestation/gate/seal')
    return {'status':'INPUTS_SELECTED_UNATTESTED','newfuture_prebuilt_sha256':NEWFUTURE_SHA,
            'bclone_commit':BCLONE_COMMIT,'go_version':GO,'ndk_revision':NDK,
            'newfuture_custody':'UNATTESTED','bclone_signature':'UNSIGNED',
            'may_run_raw_ci':True,'independent_attestation':False,'gate_g01':'BLOCKED','final_seal':'NOT_ISSUED'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['verify'])
    p.add_argument('--lock',type=Path,default=LOCK)
    p.add_argument('--selection',type=Path,default=SELECTION)
    a=p.parse_args()
    try:print(json.dumps(verify(a.lock,a.selection),sort_keys=True))
    except (Rejected,OSError,TypeError,KeyError) as e:
        print('SB-Q04P2 BLOCKED: '+str(e),file=sys.stderr)
        return 3
    return 0
if __name__=='__main__':sys.exit(main())
