#!/usr/bin/env python3
"""Skybind A1-B3 physical Android qualification. No writes unless explicitly opted in.

Run via ./devtoolw api-device-readonly or ./devtoolw api-device-disposable.
Python stdlib; Termux and root (su) required. No direct rclone commands.
Never prints/saves remote paths, proofs, tokens, job names, RPC body or stderr.
"""
from __future__ import annotations
import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import time
from typing import Any

BIN = '/data/adb/modules/skybind/system/bin/skybind'
EXCHANGE = Path('/storage/emulated/0/Download/Skybind-Transfers')
OUTROOT = Path('/storage/emulated/0/Download/Skybind-API-Device-Tests')
ACK = 'I_AUTHORIZE_DISPOSABLE_TEST_DATA'
REMOTE_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_-]{0,62}:[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*$')
HEX_ID = re.compile(r'^[a-f0-9]{32}$')
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED'}

class TestBlocked(RuntimeError): pass
class TestFail(RuntimeError): pass


def validated_base(base: str) -> str:
    if not REMOTE_RE.fullmatch(base) or len(base) > 320:
        raise ValueError('remote base must be an existing non-root remote folder with safe alphanumeric segments')
    return base


def aggregate_counts(results: list[dict]) -> dict[str, int]:
    return {key: sum(r['status'] == key for r in results) for key in ('PASS', 'FAIL', 'BLOCKED')}


def scrubbed_run_summary(run: dict) -> dict:
    # Never serialize Name, Source, Destination, reason, or provider error text.
    keep = ('state','bytes','speed_bytes_per_second','eta_seconds','total_bytes',
            'percent','files_done','files_total','checks_done','checks_total',
            'errors','retry_error','transfer_retries')
    return {k: run[k] for k in keep if k in run and isinstance(run[k], (int, float, bool, type(None), str)) and (k != 'state' or run[k] in TERMINAL | {'RUNNING','QUEUED','CANCELLING'})}


def safe_event(event: dict) -> dict:
    safe = {'type','state','phase','sequence'}
    out = {k:event[k] for k in safe if k in event and isinstance(event[k], (str,int)) and (k != 'sequence' or event[k] >= 0)}
    progress = event.get('progress')
    if isinstance(progress, dict):
        out['progress'] = {k: v for k, v in progress.items() if k in ('bytes', 'total_bytes', 'percent', 'speed_bytes_per_second', 'eta_seconds', 'files_done','files_total','checks_done','checks_total','errors','retry_error','transfer_retries') and isinstance(v, (int,float,bool,type(None)))}
    return out


class DeviceRPC:
    def __init__(self, binary=BIN, su='su'):
        self.binary, self.su = binary, su
    def raw(self, argv: list[str], *, timeout=40) -> tuple[int, str]:
        if any('\x00' in v or '\n' in v or '\r' in v for v in argv):
            raise TestBlocked('unsafe executable argument')
        cmd = ' '.join(shlex.quote(v) for v in [self.binary, *argv])
        try:
            p = subprocess.run([self.su, '-c', cmd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as ex:
            raise TestBlocked('privileged installed Skybind command unavailable') from ex
        if len(p.stdout) > 524288:
            raise TestBlocked('oversized RPC reply')
        return p.returncode, p.stdout.decode('utf-8','replace').strip()
    def installed_binary_hash(self) -> str|None:
        # Identity marker only: does not itself prove source/receipt equivalence.
        try:
            p=subprocess.run([self.su,'-c','/system/bin/sha256sum '+shlex.quote(self.binary)],capture_output=True,timeout=20,check=False)
            if p.returncode: return None
            match=re.match(rb'^([a-f0-9]{64})\s',p.stdout)
            return match.group(1).decode('ascii') if match else None
        except (OSError,subprocess.TimeoutExpired):return None
    def call(self, op: str, classification: str='query', args: dict|None=None, *, expect_ok=True, timeout=40) -> dict:
        if not re.fullmatch(r'[a-z][a-z0-9_.]{1,90}', op) or classification not in ('query','preview','run','cancel'):
            raise TestBlocked('invalid operation request')
        code, payload = self.raw(['rpc', op, classification, json.dumps(args or {}, separators=(',',':'))], timeout=timeout)
        try:
            reply = json.loads(payload)
        except ValueError:
            raise TestFail('installed CLI did not return a JSON RPC envelope')
        if not isinstance(reply, dict) or not isinstance(reply.get('ok'), bool):
            raise TestFail('invalid RPC envelope')
        if expect_ok and (code != 0 or not reply['ok']):
            raise TestFail(f'{op} rejected by installed backend (code={code}; details redacted)')
        if not expect_ok and reply['ok']:
            raise TestFail(f'{op} accepted a prohibited request')
        return reply


class Qualifier:
    def __init__(self, rpc: DeviceRPC, mode: str, base: str|None, out: Path, timeout: int=240):
        self.rpc, self.mode, self.base, self.out, self.timeout = rpc, mode, base, out, timeout
        self.records: list[dict] = []
        self.session = 'qa_'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')+'_'+secrets.token_hex(4)
        self.project_root = Path(__file__).resolve().parents[3]
        self.binary_digest = None
        self.remote_dir: str|None = None
        self.local_dir: Path|None = None
        self.run_ids: list[str] = []
        self.started = dt.datetime.now(dt.timezone.utc).isoformat()
    def case(self, label: str, fn):
        started = time.monotonic()
        print(f'[{len(self.records)+1:02d}] {label} ...', flush=True)
        detail = {}
        try:
            result = fn()
            if isinstance(result, dict): detail = result
            status='PASS'
        except TestBlocked as exc:
            status='BLOCKED'; detail={'note':str(exc)[:150]}
        except (TestFail, AssertionError) as exc:
            status='FAIL'; detail={'note':str(exc)[:150]}
        except Exception:
            status='FAIL'; detail={'note':'unhandled test exception (details suppressed)'}
        self.records.append({'test':label, 'status':status, 'elapsed_ms':int((time.monotonic()-started)*1000), 'evidence':detail})
        print('    '+status,flush=True)
        return status
    def rpc_result(self, name, cls='query', **args):
        x=self.rpc.call(name,cls,args)
        return x.get('result')
    def preflight(self):
        code, version = self.rpc.raw(['version'])
        if code != 0 or not version.startswith('Skybind '):
            # version format might be lowercase; report a blocked mismatch, not arbitrary text
            if code != 0 or 'skybind' not in version.lower():
                raise TestBlocked('installed Skybind binary not available')
        try:
            d = self.rpc.raw(['webui','bridge','--capabilities'])[0]
            if d != 0: raise TestFail('direct embedded backend capability request failed')
        except TestBlocked: raise
        self.binary_digest = self.rpc.installed_binary_hash() if hasattr(self.rpc,'installed_binary_hash') else None
        return {'installed_cli':True,'direct_webui_bridge':True,'installed_binary_sha256':self.binary_digest,'version_known':True}
    def events_contract(self):
        p=self.rpc_result('operation.events', cursor=0, limit=32, wait_ms=0)
        if not isinstance(p,dict) or not isinstance(p.get('events'),list):
            raise TestFail('invalid operation event page')
        seq=[e.get('sequence') for e in p['events']]
        if any(not isinstance(x,int) for x in seq) or seq!=sorted(set(seq)):
            raise TestFail('event cursor order invalid')
        cursor=p.get('next_cursor')
        if not isinstance(cursor,int) or cursor<0: raise TestFail('event cursor missing')
        q=self.rpc_result('operation.events',cursor=cursor,limit=32,wait_ms=0)
        if not isinstance(q,dict) or not isinstance(q.get('events'),list):
            raise TestFail('event cursor replay failed')
        if any(e.get('sequence',0)<=cursor for e in q['events']):
            raise TestFail('event page replayed older sequences')
        return {'events_returned':len(seq),'last_cursor':cursor,'gap_reported':bool(p.get('gap')),'degraded':bool(p.get('degraded'))}
    def running_jobs(self):
        r=self.rpc_result('jobs.status')
        if not isinstance(r,dict):
            raise TestFail('jobs.status result is not an object')
        runs=r.get('runs')
        if runs is None:
            raise TestFail('jobs.status.runs is null or missing; expected [] for empty history')
        if not isinstance(runs,list):
            raise TestFail('jobs.status.runs is not an array')
        active=0
        for item in runs:
            if not isinstance(item,dict):
                raise TestFail('jobs.status.runs contains a non-object entry')
            if item.get('state') in ('QUEUED','RUNNING','CANCELLING'):
                active+=1
            if not isinstance(item.get('id'),str) or not HEX_ID.fullmatch(item['id']):
                raise TestFail('job run identity is invalid')
            if item.get('state') not in TERMINAL | {'QUEUED','RUNNING','CANCELLING'}:
                raise TestFail('job run state is invalid')
            numeric=('bytes','speed_bytes_per_second','eta_seconds','total_bytes',
                     'percent','files_done','files_total','checks_done','checks_total',
                     'errors','transfer_retries')
            for key in numeric:
                if key not in item or item[key] is None:
                    continue
                value=item[key]
                if isinstance(value,bool) or not isinstance(value,(int,float)) or value < 0:
                    raise TestFail('job numeric field invalid: '+key)
            if item.get('percent') is not None:
                if item.get('total_bytes') is None or item['percent']>100:
                    raise TestFail('job percent provided without a valid total')
            if item.get('retry_error') is not None and not isinstance(item['retry_error'],bool):
                raise TestFail('job retry_error is not boolean')
        return {'historical_runs_count':len(runs),'currently_active_count':active,
                'numeric_contract_checked':True}
    def negative(self):
        bad=[('remote.transfer.preview','preview',dict(kind='sync',source='unused:src',destination='unused:dst')),
             ('remote.transfer.start','run',dict(kind='sync',source='unused:src',destination='unused:dst',proof='invalid')),
             ('remote.media.preview','preview',dict(direction='download',remote='unused:folder',local='../other')),
             ('remote.file.move.preview','preview',dict(source='unused:folder/x',destination='different:folder/y')),
             ('remote.mkdir.preview','preview',dict(endpoint='unused:')),
             ('operation.cancel','cancel',dict(id='0'*32))]
        for op,typ,args in bad: self.rpc.call(op,typ,args,expect_ok=False)
        return {'unsafe_operations_rejected':len(bad)}
    def readonly_remote(self):
        if not self.base: raise TestBlocked('no explicit remote folder configured; remote read-only probe not run')
        got=self.rpc_result('remote.list',endpoint=self.base)
        if not isinstance(got,list):raise TestFail('remote.list should return a listing')
        return {'listed_entries':len(got),'remote_base_sha256':hashlib.sha256(self.base.encode()).hexdigest()}
    def mk(self,endpoint):
        p=self.rpc_result('remote.mkdir.preview','preview',endpoint=endpoint)
        if not isinstance(p,dict) or not p.get('proof'):raise TestFail('mkdir proof missing')
        proof=p['proof']
        if self.rpc_result('remote.mkdir.run','run',endpoint=endpoint,proof=proof).get('created') is not True:
            raise TestFail('mkdir did not confirm creation')
        self.rpc.call('remote.mkdir.run','run',{'endpoint':endpoint,'proof':proof},expect_ok=False)
    def start_job(self,preview_op,start_op,payload):
        p=self.rpc_result(preview_op,'preview',**payload)
        if not isinstance(p,dict) or not isinstance(p.get('proof'),str):raise TestFail('job preview missing proof')
        args={**payload,'proof':p['proof']}
        result=self.rpc_result(start_op,'run',**args)
        if not isinstance(result,dict) or not HEX_ID.fullmatch(str(result.get('id',''))):raise TestFail('job run ID missing')
        run_id=result['id']
        self.run_ids.append(run_id)
        self.rpc.call(start_op,'run',args,expect_ok=False)
        return run_id
    def wait_run(self,run_id):
        deadline=time.monotonic()+self.timeout
        last=None
        while time.monotonic()<deadline:
            v=self.rpc_result('jobs.status')
            for r in v.get('runs',[]):
                if isinstance(r,dict) and r.get('id')==run_id: last=r; break
            if last and last.get('state') in TERMINAL:
                if last['state']!='COMPLETED':raise TestFail(f'job ended {last["state"]}')
                return scrubbed_run_summary(last)
            time.sleep(2)
        raise TestBlocked('job still running after bounded observation; do not auto-retry')
    def events_for(self,run_id):
        p=self.rpc_result('operation.events',cursor=0,limit=64,operation_id=run_id,wait_ms=0)
        if not isinstance(p,dict) or not isinstance(p.get('events'),list):raise TestFail('operation event stream unavailable')
        ev=[safe_event(x) for x in p['events'] if isinstance(x,dict)]
        if not ev:raise TestFail('no events for completed job')
        ty=[e.get('type') for e in ev]
        if not any(x in ty for x in ('job.completed','job.failed','job.cancelled')):
            raise TestFail('no terminal event for job')
        for x in ev:
            pr=x.get('progress',{})
            total=pr.get('total_bytes'); pc=pr.get('percent')
            if pc is not None and (total is None or total<0 or not 0<=pc<=100):
                raise TestFail('untruthful progress percentage')
        return {'events':len(ev),'terminal_event':ty[-1], 'progress_samples':sum(e.get('type')=='job.progress' for e in ev),
                'total_reported':any('total_bytes' in e.get('progress',{}) for e in ev),
                'files_reported':any('files_done' in e.get('progress',{}) for e in ev),
                'retry_metrics_reported':any('retry_error' in e.get('progress',{}) for e in ev)}
    def create_workspace(self):
        if not self.base:raise TestBlocked('test base absent')
        self.remote_dir=self.base+'/'+self.session
        self.mk(self.remote_dir)
        for sub in ('upload','copied','download','move'):
            self.mk(self.remote_dir+'/'+sub)
        EXCHANGE.mkdir(parents=True,exist_ok=True)
        if EXCHANGE.is_symlink() or not EXCHANGE.is_dir():
            raise TestFail('exchange folder is symlinked or not a directory')
        local=EXCHANGE/self.session
        if local.exists() or local.is_symlink():raise TestFail('local disposable test location collision')
        (local/'outgoing').mkdir(parents=True,mode=0o755)
        payload=secrets.token_bytes(2*1024*1024)
        (local/'outgoing'/'proof.bin').write_bytes(payload)
        self.local_dir=local
        return {'unique_disposable_paths_created':True,'payload_size':len(payload),'payload_sha256':hashlib.sha256(payload).hexdigest()}
    def media_upload(self):
        payload={'direction':'upload','remote':self.remote_dir+'/upload','local':self.session+'/outgoing'}
        rid=self.start_job('remote.media.preview','remote.media.start',payload)
        result=self.wait_run(rid)
        check=self.rpc_result('remote.stat',endpoint=self.remote_dir+'/upload/proof.bin')
        if not isinstance(check,dict) or check.get('Size')!=2*1024*1024:
            raise TestFail('remote upload size mismatch')
        return {'job':result, 'events':self.events_for(rid),'remote_size_matches':True}
    def media_download(self):
        payload={'direction':'download','remote':self.remote_dir+'/upload','local':self.session+'/download'}
        rid=self.start_job('remote.media.preview','remote.media.start',payload)
        result=self.wait_run(rid)
        f=self.local_dir/'download'/'proof.bin'
        if not f.is_file() or f.is_symlink() or f.read_bytes()!=(self.local_dir/'outgoing'/'proof.bin').read_bytes():
            raise TestFail('download bytes do not match upload')
        return {'job':result, 'events':self.events_for(rid),'sha256_match':True}
    def remote_copy(self):
        payload={'kind':'copy','source':self.remote_dir+'/upload','destination':self.remote_dir+'/copied'}
        rid=self.start_job('remote.transfer.preview','remote.transfer.start',payload)
        result=self.wait_run(rid)
        f=self.rpc_result('remote.stat',endpoint=self.remote_dir+'/copied/proof.bin')
        if not isinstance(f,dict) or f.get('Size')!=2*1024*1024:
            raise TestFail('copied remote file missing')
        return {'job':result,'events':self.events_for(rid),'remote_size_matches':True}
    def remote_check(self):
        payload={'kind':'check','source':self.remote_dir+'/upload','destination':self.remote_dir+'/copied'}
        rid=self.start_job('remote.transfer.preview','remote.transfer.start',payload)
        result=self.wait_run(rid)
        return {'job':result, 'events':self.events_for(rid)}
    def remote_move(self):
        payload={'source':self.remote_dir+'/copied/proof.bin','destination':self.remote_dir+'/copied/renamed.bin'}
        rid=self.start_job('remote.file.move.preview','remote.file.move.start',payload)
        result=self.wait_run(rid)
        final=self.rpc_result('remote.stat',endpoint=payload['destination'])
        if not isinstance(final,dict) or final.get('Size')!=2*1024*1024:
            raise TestFail('renamed file not present')
        self.rpc.call('remote.stat','query',{'endpoint':payload['source']},expect_ok=False)
        return {'job':result,'events':self.events_for(rid),'source_absent':True,'destination_present':True}
    def no_overwrite(self):
        # Modify only the unique disposable local source and copy again. Existing
        # remote object must retain the original bytes. Read back into a distinct
        # unique directory so that cached local data cannot mask an overwrite.
        source=self.local_dir/'outgoing'/'proof.bin'
        old_digest=hashlib.sha256((self.local_dir/'download'/'proof.bin').read_bytes()).hexdigest()
        source.write_bytes(b'different disposable content; overwrite forbidden\n')
        payload={'direction':'upload','remote':self.remote_dir+'/upload','local':self.session+'/outgoing'}
        rid=self.start_job('remote.media.preview','remote.media.start',payload)
        result=self.wait_run(rid)
        sub=self.session+'/verify_unchanged'
        rid2=self.start_job('remote.media.preview','remote.media.start',{'direction':'download','remote':self.remote_dir+'/upload','local':sub})
        result2=self.wait_run(rid2)
        chk=EXCHANGE/sub/'proof.bin'
        if not chk.is_file() or hashlib.sha256(chk.read_bytes()).hexdigest()!=old_digest:
            raise TestFail('destination object was overwritten')
        return {'upload':result,'verify':result2,'no_overwrite_verified':True}
    def reject_move_collision(self):
        # Both files exist exclusively inside this run's disposable test tree.
        # Source proof.bin was already renamed. Upload another file with a new
        # name to provide an existing destination for negative preview.
        self.rpc.call('remote.file.move.preview','preview',{'source':self.remote_dir+'/upload/proof.bin','destination':self.remote_dir+'/copied/renamed.bin'},expect_ok=False)
        return {'existing_destination_rejected':True}
    def cancel_disposable(self):
        # Cancellation is never directed at a pre-existing user job.
        self.mk(self.remote_dir+'/cancel_source')
        self.mk(self.remote_dir+'/cancel_destination')
        (self.local_dir/'cancel_upload').mkdir(mode=0o755)
        datafile=self.local_dir/'cancel_upload'/'cancel.bin'
        with datafile.open('xb') as f:
            for _ in range(8): f.write(secrets.token_bytes(1024*1024))
        source={'direction':'upload','remote':self.remote_dir+'/cancel_source','local':self.session+'/cancel_upload'}
        pre=self.start_job('remote.media.preview','remote.media.start',source)
        self.wait_run(pre)
        payload={'kind':'copy','source':self.remote_dir+'/cancel_source','destination':self.remote_dir+'/cancel_destination'}
        run_id=self.start_job('remote.transfer.preview','remote.transfer.start',payload)
        result=self.rpc_result('jobs.status')
        rec=next((r for r in result.get('runs',[]) if r.get('id')==run_id),None)
        if rec and rec.get('state') in TERMINAL:
            raise TestBlocked('disposable transfer finished before cancellation; not proven')
        try:
            self.rpc.call('operation.cancel','cancel',{'id':run_id})
        except TestFail:
            # A completion may race the cancellation request: inspect state.
            result=self.rpc_result('jobs.status')
            rec=next((r for r in result.get('runs',[]) if r.get('id')==run_id),None)
            if rec and rec.get('state')=='COMPLETED':
                raise TestBlocked('transfer completed before cancellation; race inconclusive')
            raise
        deadline=time.monotonic()+min(60,self.timeout)
        while time.monotonic()<deadline:
            status=self.rpc_result('jobs.status')
            rec=next((r for r in status.get('runs',[]) if r.get('id')==run_id),None)
            if rec and rec.get('state') in TERMINAL:
                if rec['state']=='CANCELLED':
                    return {'cancelled_disposable_job':True,'state':'CANCELLED','run':scrubbed_run_summary(rec)}
                if rec['state']=='COMPLETED':
                    raise TestBlocked('cancellation raced natural completion; inconclusive')
                raise TestFail('cancellation ended in non-cancel terminal state')
            time.sleep(1)
        raise TestBlocked('disposable job cancellation pending at observation deadline')
    def negative_without_workspace(self):
        return self.negative()
    def run_all(self):
        startup=self.case('D00 installed Skybind and direct bridge', self.preflight)
        if startup!='PASS':
            for name in ('A1 event cursor and replay','A1/A3 jobs.status and numeric contract',
                         'B1-B3 unsafe operation rejection','B1 mountless browse configured folder',
                         'A1-B3 disposable operations','Android WebView visual/ksu.exec acceptance',
                         'Reboot and journal recovery'):
                self.case(name,lambda: (_ for _ in ()).throw(TestBlocked('installed backend prerequisite not proven')))
            return self.finish()
        self.case('A1 event cursor and replay', self.events_contract)
        self.case('A1/A3 jobs.status and numeric contract', self.running_jobs)
        self.case('B1-B3 unsafe operation rejection', self.negative_without_workspace)
        self.case('B1 mountless browse configured folder', self.readonly_remote)
        if self.mode=='disposable':
            if not self.base: self.case('DISPOSABLE authorization',lambda: (_ for _ in ()).throw(TestBlocked('SKYBIND_QA_REMOTE_BASE required')))
            elif os.environ.get('SKYBIND_QA_ACK')!=ACK: self.case('DISPOSABLE authorization',lambda: (_ for _ in ()).throw(TestBlocked('explicit SKYBIND_QA_ACK required')))
            else:
                # Do not proceed if browse preflight failed.
                if any(r['status'] != 'PASS' for r in self.records):
                    self.case('DISPOSABLE start guard',lambda: (_ for _ in ()).throw(TestBlocked('required read-only device API probes did not all pass')))
                elif self.case('B3 create unique disposable workspace',self.create_workspace)=='PASS':
                    # Later tests are chained to protect against cascading operations.
                    for name,fn in [('B3 upload and remote stat',self.media_upload),('B3 download and SHA256 integrity',self.media_download),
                                    ('B1 remote-to-remote copy',self.remote_copy),('B1 remote check',self.remote_check),
                                    ('B3 rename one disposable remote file',self.remote_move),
                                    ('B3 no-overwrite verification',self.no_overwrite),
                                    ('B3 destination collision rejected',self.reject_move_collision),
                                    ('B1 owned-job cancellation race',self.cancel_disposable)]:
                        if any(r['status']!='PASS' for r in self.records[-1:]):
                            self.case(name,lambda: (_ for _ in ()).throw(TestBlocked('previous dependent operation did not pass')))
                        else: self.case(name,fn)
        self.case('Android WebView visual/ksu.exec acceptance',lambda: (_ for _ in ()).throw(TestBlocked('needs on-device WebView capture and interaction evidence; CLI RPC is insufficient')))
        self.case('Reboot and journal recovery',lambda: (_ for _ in ()).throw(TestBlocked('requires reboot-specific evidence and offline queue readback; no automatic reboot performed')))
        return self.finish()
    def finish(self):
        status=aggregate_counts(self.records)
        doc={'schema_version':1,'kind':'skybind_api_a1_b3_physical_device_raw',
             'created_at':dt.datetime.now(dt.timezone.utc).isoformat(), 'started_at':self.started,
             'qualification':'RAW_DEVICE_NOT_RELEASE_ATTESTED','mode':self.mode,
             'source_tree': self.source_fingerprint(),
             'module_path_sha256':hashlib.sha256(BIN.encode()).hexdigest(),
             'installed_binary_sha256':self.binary_digest,
             'session_folder_name': self.session if self.remote_dir else None,
             'remote_base_sha256':hashlib.sha256(self.base.encode()).hexdigest() if self.base else None,
             'disposable_session_sha256':hashlib.sha256(self.session.encode()).hexdigest() if self.remote_dir else None,
             'disposable_remote_created':bool(self.remote_dir),
             'disposable_test_files_retained':bool(self.local_dir),
             'tests':self.records,'counts':status,
             'limitations':['WebView device interaction not automated','No installer/build provenance equality proof',
                            'No reboot/queued writeback mutation','No remote cleanup performed',
                            'Live progress samples can be too short on small disposable transfers']}
        self.out.mkdir(parents=True,exist_ok=True)
        dest=self.out/('skybind-api-qualification-'+self.session+'.json')
        fd=os.open(dest,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(doc,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        summary=self.out/('skybind-api-qualification-'+self.session+'.md')
        with open(summary,'x',encoding='utf-8') as f:
            f.write('# Skybind A1–B3 raw device results\n\n')
            f.write(f'Mode: {self.mode} · PASS {status["PASS"]} · FAIL {status["FAIL"]} · BLOCKED {status["BLOCKED"]}\n\n')
            for t in self.records: f.write(f'- {t["status"]} — {t["test"]}\n')
            f.write('\nThis is not WebUI acceptance or a release seal. Disposable remote data has NOT been deleted.\n')
        archive=self.out/('skybind-api-qualification-'+self.session+'.zip')
        import zipfile
        with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(dest,arcname=dest.name);z.write(summary,arcname=summary.name)
        print(f'REPORT: {dest}\nARCHIVE: {archive}\nCOUNTS: {status}',flush=True)
        return 1 if status['FAIL'] else 0  # BLOCKED is recorded as incomplete evidence; not claimed as qualification
    def source_fingerprint(self):
        names=['internal/opevents/events.go','internal/jobs/jobs.go','internal/daemon/wiring.go',
               'internal/provider/remote_manager_b3.go','module/webroot/live_progress.js','module/webroot/remote_b3_ui.js']
        out={}
        for name in names:
            f=self.project_root/name
            if f.is_file():out[name]=hashlib.sha256(f.read_bytes()).hexdigest()
        return out


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['readonly','disposable'],default='readonly')
    p.add_argument('--remote-base',default=os.environ.get('SKYBIND_QA_REMOTE_BASE',''))
    p.add_argument('--output-dir',default=str(OUTROOT))
    p.add_argument('--job-timeout',type=int,default=240)
    a=p.parse_args(argv)
    if not 20<=a.job_timeout<=1200: p.error('job-timeout must be between 20 and 1200')
    try:
        base=validated_base(a.remote_base) if a.remote_base else None
    except ValueError as e:
        p.error(str(e))
    q=Qualifier(DeviceRPC(),a.mode,base,Path(a.output_dir),a.job_timeout)
    return q.run_all()

if __name__=='__main__':
    sys.exit(main())
