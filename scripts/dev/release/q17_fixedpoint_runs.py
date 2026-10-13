#!/usr/bin/env python3
"""Q17 executes actual negative tests and retains immutable-ish raw logs per fresh run.

A local Devtool job, not by itself an independently authenticated Devtool receipt.
Never writes sb_g02_source.json or invents a Devtool ID, warning count, gate pass.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import sb_g02
# Exact registered tests: names are not counted as PASS unless -json emits a pass event.
TESTS={
 'unknown_operation':('skybind/cmd/skybind','TestCLIRejectsUntrustedOperation'),
 'wrong_class':('skybind/internal/control','TestClassDriftAndArbitraryRegistrationRejected'),
 'unimplemented_operation':('skybind/internal/control','TestCatalogTruthAndDeterminism'),
 'unknown_json_field':('skybind/internal/protocol','TestBoundsStrictVersion'),
 'proof_replay':('skybind/internal/previewproof','TestOneUseRaceExpiry'),
 'stale_revision':('skybind/internal/mounts/config','TestStaleProofRollback'),
 'atomic_interruption':('skybind/internal/mounts/config','TestInterruptedCommitRevertsCoherently'),
 'cli_daemon_equivalence':('skybind/cmd/skybind','TestFPHotfixCLIHealthAndReconcileSchemas'),
 'long_socket_path':('skybind/internal/daemon','TestOverlongSocketPathFailsBeforeLockCreation'),
 'private_permissions':('skybind/internal/mounts/lifecycle','TestFirstConfigPublicationCreatesPrivateDesiredDirectory'),
}
class Blocked(ValueError):pass

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def git(root:Path,*args)->str:
 p=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True)
 if p.returncode:raise Blocked('git command failed: '+p.stderr[-300:])
 return p.stdout.strip()
def preflight(root:Path)->dict:
 if git(root,'status','--porcelain=v1','--untracked-files=all'):raise Blocked('source worktree must be completely clean')
 hashes={p:sha(root/p) for p in sb_g02.SOURCES}
 if hashes[sb_g02.SOURCES[0]]!=hashes[sb_g02.SOURCES[1]]:raise Blocked('operation catalogs differ')
 return {'commit':git(root,'rev-parse','HEAD'),'tree':git(root,'rev-parse','HEAD^{tree}'),'hashes':hashes}

def run(root:Path,output:Path)->dict:
 baseline=preflight(root)
 if output.is_symlink():raise Blocked('output directory cannot be symlink')
 output.mkdir(parents=True,exist_ok=True)
 identity=uuid.uuid4().hex
 target=output/('q17-run-'+identity)
 target.mkdir(mode=0o700)
 checks={};errors=[]
 for case,(package,test) in TESTS.items():
  argv=['go','test','-json','-count=1','-run','^'+test+'$','./'+package.removeprefix('skybind/')]
  try:
   proc=subprocess.run(argv,cwd=root,capture_output=True,text=True,timeout=180,check=False)
   raw=proc.stdout+('\n=== STDERR ===\n'+proc.stderr if proc.stderr else '')
   events=[]
   for line in proc.stdout.splitlines():
    try:
     e=json.loads(line)
     if e.get('Test')==test:events.append(e)
    except ValueError:pass
   found=any(e.get('Action')=='pass' for e in events)
   fail=any(e.get('Action')=='fail' for e in events)
   passed=proc.returncode==0 and found and not fail
   reason='TEST_PASSED' if passed else 'GO_TEST_FAILED_OR_NO_PASS_EVENT'
  except subprocess.TimeoutExpired as exc:
   raw=str(exc);passed=False;reason='TIMEOUT'
  log=target/(case+'.log');log.write_text(raw)
  checks[case]={'test':test,'package':package,'result':reason,'passed':passed,'log_sha256':sha(log),
                'log':log.name}
  if not passed:errors.append(case)
 ending=preflight(root)
 if ending!=baseline:errors.append('SOURCE_DRIFT_DURING_TEST')
 env_id=os.getenv('DEVTOOL_RUN_ID','')
 # Environment-provided identifiers are informational, never independently authenticated.
 record={'schema_version':1,'campaign':'SB-Q17','receipt_kind':'RAW_LOCAL_DEVTOOL_TEST_EXECUTION',
   'identity':identity,'environment_devtool_run_id':env_id or None,
   'devtool_identity_authenticated':False,
   'source_commit':baseline['commit'],'source_tree':baseline['tree'],
   'source_hashes':baseline['hashes'],'cases':checks,'errors':errors,
   'status':'RAW_TESTS_PASSED_NOT_INDEPENDENT' if not errors else 'RAW_TESTS_FAILED',
   'independent_devtool_fixed_point_proven':False,'gate_evidence_generated':False,'final_seal':'NOT_ISSUED'}
 (target/'receipt.json').write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
 return {'path':str(target),'receipt':record}

def read(root:Path,folder:Path)->dict:
 if folder.is_symlink() or not folder.is_dir():raise Blocked('bad run directory')
 path=folder/'receipt.json'
 if path.is_symlink() or not path.is_file():raise Blocked('missing run receipt')
 record=json.loads(path.read_text())
 if record.get('schema_version')!=1 or record.get('campaign')!='SB-Q17':raise Blocked('invalid receipt')
 for name,(package,test) in TESTS.items():
  info=record.get('cases',{}).get(name)
  if not isinstance(info,dict) or info.get('package')!=package or info.get('test')!=test:
   raise Blocked('incomplete/mismatched negative case '+name)
  log=folder/(name+'.log')
  if log.is_symlink() or not log.is_file() or sha(log)!=info.get('log_sha256'):
   raise Blocked('tampered/missing test log '+name)
  if info.get('passed') is not True or info.get('result')!='TEST_PASSED':raise Blocked('negative case not passing '+name)
 if record.get('errors') or record.get('status')!='RAW_TESTS_PASSED_NOT_INDEPENDENT':
  raise Blocked('failed raw receipt')
 return record

def compare(root:Path,first:Path,second:Path)->dict:
 if first.resolve()==second.resolve():raise Blocked('two distinct fresh runs required')
 a,b=read(root,first),read(root,second)
 if a['identity']==b['identity']:raise Blocked('duplicate run identity')
 baseline=preflight(root)
 if a['source_commit']!=b['source_commit'] or a['source_hashes']!=b['source_hashes'] or a['source_hashes']!=baseline['hashes'] or a['source_commit']!=baseline['commit']:
  raise Blocked('source drift across fresh executions')
 gate=sb_g02.evaluate(root=root,g01_result={'status':'BLOCKED'})
 return {'schema_version':1,'campaign':'SB-Q17','status':'TWO_FRESH_RAW_NEGATIVE_RUNS_VERIFIED_NOT_INDEPENDENT',
   'run_ids':[a['identity'],b['identity']], 'case_count':len(TESTS),
   'source_commit':baseline['commit'],'source_hashes':baseline['hashes'],
   'devtool_run_identity_independently_verified':False,
   'fresh_process_fixed_point_independently_attested':False,
   'warning_count_independently_verified':False,
   'g02_actual':gate['status'],'g02_reasons':gate['reasons'],
   'gate_evidence_generated':False,'final_seal':'NOT_ISSUED'}

def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 r=sub.add_parser('run');r.add_argument('--output-dir',type=Path,default=Path('/storage/emulated/0/Download/skybind-q17-runs'))
 v=sub.add_parser('compare');v.add_argument('--first',type=Path,required=True);v.add_argument('--second',type=Path,required=True)
 v.add_argument('--output-dir',type=Path,default=Path('/storage/emulated/0/Download'))
 for parser in (r,v):parser.add_argument('--repository',type=Path,default=ROOT)
 ns=p.parse_args(argv)
 try:
  if ns.command=='run':
   result=run(ns.repository,ns.output_dir)
   print('SB-Q17',result['receipt']['status'],result['path'])
   return 0 if not result['receipt']['errors'] else 3
  obj=compare(ns.repository,ns.first,ns.second)
  out=ns.output_dir
  if out.is_symlink():raise Blocked('unsafe output dir')
  out.mkdir(parents=True,exist_ok=True)
  path=out/'skybind-q17-summary.json'
  if path.exists() or path.is_symlink():raise Blocked('output already exists')
  path.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
  print('SB-Q17',obj['status'],'G02',obj['g02_actual'])
  return 0
 except (Blocked,OSError,ValueError,KeyError) as exc:
  print('SB-Q17 BLOCKED:',str(exc),file=sys.stderr);return 3
if __name__=='__main__':raise SystemExit(main())
