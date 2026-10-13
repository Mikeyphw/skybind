#!/usr/bin/env python3
"""Q16 original-source two-lane provider-build collector. NO CFS1 gate receipts.

Takes the published SB-Q02 *provider* workflow, not Q14 candidate repackaging.
Authenticated GitHub transport + official pinned bytes are reviewable raw evidence,
not externally audited build custody. Never writes sb_g01_provider_builds.json.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts/dev/runtime'))
sys.path.insert(0,str(ROOT/'scripts/dev/gates'))
import source_build as sb, sb_g01
REPO=re.compile(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z')
SHA=re.compile(r'[a-f0-9]{40}\Z')
PROVIDERS=('newfuture','bclone')
LANES=('A','B')
WORKFLOW='.github/workflows/skybind-provider-reproducibility.yml'

class Blocked(ValueError): pass

def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for part in iter(lambda:f.read(1048576),b''):h.update(part)
 return h.hexdigest()

def cmd(args:list[str],timeout=120)->str:
 p=subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False)
 if p.returncode:raise Blocked('command failed '+args[0]+': '+p.stderr.strip()[-700:])
 return p.stdout

def run_metadata(repo:str, run_id:int)->dict:
 if not REPO.fullmatch(repo) or type(run_id)!=int or run_id<=0:raise Blocked('invalid repo/run identity')
 r=json.loads(cmd(['gh','api',f'repos/{repo}/actions/runs/{run_id}']))
 if (r.get('id')!=run_id or r.get('repository',{}).get('full_name','').lower()!=repo.lower() or
     r.get('conclusion')!='success' or r.get('status')!='completed' or
     str(r.get('path','')).split('@')[0]!=WORKFLOW or
     not SHA.fullmatch(r.get('head_sha',''))):
  raise Blocked('GitHub run identity, workflow or success not authenticated')
 j=json.loads(cmd(['gh','api',f'repos/{repo}/actions/runs/{run_id}/jobs?per_page=100']))
 jobs=j.get('jobs',[])
 # Exactly two distinct successful real build jobs (allow GitHub matrix name prefixes).
 chosen=[]
 for lane in LANES:
  found=[x for x in jobs if x.get('name','').endswith(f'({lane})') and x.get('conclusion')=='success']
  if len(found)!=1:raise Blocked('missing/ambiguous successful provider build lane '+lane)
  chosen.append(found[0]['id'])
 if chosen[0]==chosen[1]:raise Blocked('duplicate GitHub job identities')
 return {'run_id':run_id,'repo':repo,'commit':r['head_sha'],'run_attempt':r.get('run_attempt'),
         'workflow':WORKFLOW,'job_ids':dict(zip(LANES,chosen)),
         'transport':'AUTHENTICATED_GITHUB_API_NOT_EXTERNAL_CUSTODY'}

def safe_dir(path:Path)->None:
 if path.is_symlink() or not path.is_dir():raise Blocked('missing/linked lane directory: '+str(path))
 if any(x.is_symlink() for x in path.rglob('*')):raise Blocked('symlinks in lane evidence')

def inspect(root:Path, lane_root:Path, identity:dict|None=None)->dict:
 sb.load_lock(root/'scripts/dev/runtime/source.lock.json')
 lock=json.loads((root/'scripts/dev/runtime/source.lock.json').read_text())
 packs={}
 for lane in LANES:
  folder=lane_root/f'skybind-provider-lane-{lane}'
  safe_dir(folder)
  build=folder/'bclone_build';package=folder/'packages';upstream=folder/'upstream'
  for d in (build,package,upstream):safe_dir(d)
  evidence=sb.verify(build)
  if evidence['source_commit']!=lock['bclone']['commit']:raise Blocked('bclone source lock drift '+lane)
  asset=upstream/'magisk-rclone_arm64-v8a.zip'
  if not asset.is_file() or asset.is_symlink() or sha(asset)!=lock['newfuture']['archive_sha256']:
   raise Blocked('original NewFuture asset missing or lock hash mismatch '+lane)
  # A git bundle is a source snapshot, not by itself an authenticated GitHub origin.
  bundle=upstream/'bclone-source.bundle'
  if not bundle.is_file() or bundle.is_symlink():raise Blocked('bclone Git object bundle missing '+lane)
  with tempfile.TemporaryDirectory() as t:
   cmd(['git','init','-q',t])
   cmd(['git','-C',t,'fetch','--quiet',str(bundle.resolve(strict=True)),'refs/heads/q16-frozen'],timeout=90)
   actual=cmd(['git','-C',t,'rev-parse','FETCH_HEAD']).strip()
   if actual!=lock['bclone']['commit']:raise Blocked('bclone original Git object mismatch '+lane)
  packs[lane]={'job_id':(identity or {}).get('job_ids',{}).get(lane),
    'official_asset_sha256':sha(asset),'source_bundle_sha256':sha(bundle),
    'provider_packages':{p:sha(package/(p+'.zip')) for p in PROVIDERS},
    'source_build_binary_sha256':evidence['binary_sha256']}
 result=sb.compare(lane_root/'skybind-provider-lane-A'/'bclone_build',
   lane_root/'skybind-provider-lane-B'/'bclone_build',
   lane_root/'skybind-provider-lane-A'/'packages',
   lane_root/'skybind-provider-lane-B'/'packages')
 if result['status']!='BYTE_IDENTICAL_UNATTESTED':raise Blocked('not byte identical')
 if packs['A']['official_asset_sha256']!=packs['B']['official_asset_sha256']:raise Blocked('upstream asset lane mismatch')
 gate=sb_g01.evaluate(root=root)
 return {'schema_version':1,'campaign':'SB-Q16','status':'TWO_REAL_PROVIDER_LANES_VERIFIED_RAW_NOT_INDEPENDENTLY_ATTESTED',
  'run':identity or {'transport':'LOCAL_LANE_BYTES_NOT_GITHUB_AUTHENTICATED'},
  'source_lock_sha256':sha(root/'scripts/dev/runtime/source.lock.json'),
  'lanes':packs,'comparison':result,'g01_actual':gate['status'],
  'g01_reasons':gate['reasons'], 'original_upstream_origin_independently_attested':False,
  'independent_custody':False,'gate_evidence_generated':False,
  'review_required':'Independent authority must authenticate upstream origin and builder custody before G01 evidence can be eligible',
  'final_seal':'NOT_ISSUED'}

def save(output:Path,data:dict)->None:
 output.mkdir(parents=True,exist_ok=True)
 if output.is_symlink():raise Blocked('linked output directory refused')
 for name,b in [('skybind-q16-summary.json',(json.dumps(data,indent=2,sort_keys=True)+'\n').encode()),
                ('skybind-q16-summary.md',('# SB-Q16 — Original provider evidence\n\n'+
                 'Status: **'+data['status']+'**\n\nG01: '+data['g01_actual']+ '\n\n'+
                 'Independent custody: **NOT ATTESTED**; release: **NOT_ISSUED**.\n').encode())]:
  path=output/name
  if path.exists() or path.is_symlink():raise Blocked('refusing report overwrite: '+name)
  with tempfile.NamedTemporaryFile(dir=output,prefix='.q16-',delete=False) as f:
   tmp=Path(f.name);f.write(b);f.flush();os.fsync(f.fileno())
  os.replace(tmp,path)

def main(argv=None)->int:
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--run-id',type=int);p.add_argument('--repo',default='Mikeyphw/skybind')
 p.add_argument('--lanes-dir',type=Path)
 p.add_argument('--output-dir',type=Path,default=Path('/storage/emulated/0/Download'))
 p.add_argument('--repository',type=Path,default=ROOT)
 args=p.parse_args(argv)
 try:
  if bool(args.run_id)==bool(args.lanes_dir):raise Blocked('select exactly one of --run-id or --lanes-dir')
  identity=None
  if args.run_id:
   identity=run_metadata(args.repo,args.run_id)
   dest=args.output_dir/f'skybind-q16-run-{args.run_id}'
   if dest.exists() or dest.is_symlink():raise Blocked('refusing preexisting download location')
   dest.mkdir(parents=True)
   try:cmd(['gh','run','download',str(args.run_id),'--repo',args.repo,'--pattern','skybind-provider-lane-*','--dir',str(dest)],timeout=420)
   except BaseException:
    # Partial evidence intentionally retained for diagnosis, never accepted as verified.
    raise
  else:dest=args.lanes_dir
  result=inspect(args.repository,dest,identity)
  save(args.output_dir,result)
  print('SB-Q16',result['status'],'G01',result['g01_actual'],'NOT_ISSUED')
  return 0
 except (Blocked,sb.Rejected,OSError,ValueError,KeyError,subprocess.TimeoutExpired) as e:
  print('SB-Q16 BLOCKED:',str(e),file=sys.stderr);return 3
if __name__=='__main__':raise SystemExit(main())
