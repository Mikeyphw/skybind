import { presentActivity, presentJobStatus } from './flow.js';
import { runtimePresentation, platformPresentation, bundleMetadata, supportDownload, passwordStatus, recoveryPresentation, doctorPresentation } from './parity.js';
const SCHEMA_VERSION = 1;
const PROTOCOL_VERSION = 1;
const MAX_TEXT = 1024 * 1024;
const EMBEDDED_BINARY = '/data/adb/modules/skybind/system/bin/skybind';
const CLASS_PATH = Object.freeze({ query: 'query', preview: 'preview', run: 'run', reconcile: 'reconcile', cancel: 'cancel' });
let requestCounter = 0;
let selected = null;

function bounded(value, limit = 4096) {
  const text = String(value ?? '');
  return text.length <= limit ? text : `${text.slice(0, limit)}…`;
}

export function newRequestId() {
  requestCounter += 1;
  return `webui-${Date.now()}-${requestCounter}`;
}

export function requestEnvelope(name, operationClass, args = {}, requestId = newRequestId()) {
  if (!/^[a-z][a-z0-9_.-]{1,127}$/.test(name)) throw new Error('Invalid typed operation name');
  if (!CLASS_PATH[operationClass]) throw new Error('Invalid typed operation class');
  return {
    schema_version: SCHEMA_VERSION,
    request_id: requestId,
    client: { name: 'skybind-webui', version: '0.1.0', protocol: { min: PROTOCOL_VERSION, max: PROTOCOL_VERSION } },
    operation: { name, class: operationClass, args },
  };
}

function base64url(value) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function csrf() {
  const part = document.cookie.split(';').map((item) => item.trim()).find((item) => item.startsWith('skybind_csrf='));
  return part ? decodeURIComponent(part.slice('skybind_csrf='.length)) : '';
}

function embeddedAvailable() {
  return Boolean(globalThis.ksu && typeof globalThis.ksu.exec === 'function');
}

async function embeddedExec(encoded, timeoutMs = 30000) {
  if (!embeddedAvailable()) throw new Error('Embedded manager bridge is unavailable');
  if (!/^[A-Za-z0-9_-]+$/.test(encoded)) throw new Error('Embedded request encoding is invalid');
  const callback = `skybind_${Date.now()}_${Math.floor(Math.random() * 1000000)}`;
  const command = `'${EMBEDDED_BINARY}' webui bridge --request-base64 ${encoded}`;
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => { try { delete globalThis[callback]; } catch (_) { globalThis[callback] = undefined; } };
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(new Error('Embedded manager callback timed out'));
    }, timeoutMs);
    globalThis[callback] = (errno, stdout, stderr) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      cleanup();
      const out = bounded(stdout, MAX_TEXT);
      if (Number(errno) !== 0) {
        reject(new Error(bounded(stderr || `Embedded backend exited with status ${errno}`)));
        return;
      }
      try { resolve(JSON.parse(out)); } catch (_) { reject(new Error('Embedded backend returned invalid JSON')); }
    };
    try { globalThis.ksu.exec(command, JSON.stringify({}), callback); }
    catch (error) { clearTimeout(timer); cleanup(); reject(error); }
  });
}

async function embeddedCapabilities(timeoutMs = 10000) {
  if (!embeddedAvailable()) throw new Error('Embedded manager bridge is unavailable');
  const callback = `skybind_caps_${Date.now()}_${Math.floor(Math.random() * 1000000)}`;
  const command = `'${EMBEDDED_BINARY}' webui bridge --capabilities`;
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => { try { delete globalThis[callback]; } catch (_) { globalThis[callback] = undefined; } };
    const timer = setTimeout(() => { if (!settled) { settled = true; cleanup(); reject(new Error('Embedded capability callback timed out')); } }, timeoutMs);
    globalThis[callback] = (errno, stdout, stderr) => {
      if (settled) return;
      settled = true; clearTimeout(timer); cleanup();
      if (Number(errno) !== 0) { reject(new Error(bounded(stderr || `Embedded backend exited with status ${errno}`))); return; }
      try { resolve(JSON.parse(bounded(stdout, MAX_TEXT))); } catch (_) { reject(new Error('Embedded capability response is invalid JSON')); }
    };
    try { globalThis.ksu.exec(command, JSON.stringify({}), callback); }
    catch (error) { clearTimeout(timer); cleanup(); reject(error); }
  });
}

async function standaloneProbe() {
  const response = await fetch('/api/v1/transport', { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
  if (!response.ok) throw new Error(`Standalone transport probe failed (${response.status})`);
  const value = await response.json();
  if (value?.schema_version !== SCHEMA_VERSION || value?.transport !== 'standalone' || value?.typed_backend !== true) {
    throw new Error('Standalone transport capability mismatch');
  }
  return value;
}

export async function selectTransport() {
  selected = null;
  let embeddedError = null;
  if (embeddedAvailable()) {
    try {
      const caps = unwrapCatalog(await embeddedCapabilities());
      validateCapabilities(caps);
      selected = 'embedded';
      return selected;
    } catch (error) {
      embeddedError = error;
    }
  }
  try {
    await standaloneProbe();
    selected = 'standalone';
    return selected;
  } catch (standaloneError) {
    selected = null;
    if (embeddedError) {
      throw new Error(`Embedded bridge unavailable (${bounded(embeddedError?.message || embeddedError)}); standalone fallback unavailable (${bounded(standaloneError?.message || standaloneError)})`);
    }
    throw standaloneError;
  }
}

export function transportName() { return selected; }

// The Android manager WebView does not reliably hand blob: anchors to a
// DownloadManager. Delegate a fixed, validated export to Skybind's root-only
// support-export entrypoint instead; never interpolate paths or free text.
export async function saveSupportBundleToDownloads(id, sha256) {
  if (selected !== 'embedded' || !embeddedAvailable()) throw new Error('Android manager download bridge is unavailable');
  if (!/^[a-f0-9]{32}$/.test(id) || !/^[a-f0-9]{64}$/.test(sha256)) throw new Error('Invalid support bundle export identity');
  const expected = `/storage/emulated/0/Download/skybind-support-${id}.zip`;
  const command = `'${EMBEDDED_BINARY}' support-export '${id}' '${sha256}'`;
  const callback = `skybind_export_${Date.now()}_${++requestCounter}`;
  return new Promise((resolve, reject) => {
    let finished = false;
    const cleanup = () => { try { delete globalThis[callback]; } catch (_) { globalThis[callback] = undefined; } };
    const timer = setTimeout(() => { if (!finished) { finished = true; cleanup(); reject(new Error('Android Downloads export timed out')); } }, 30000);
    globalThis[callback] = (errno, stdout, stderr) => {
      if (finished) return;
      finished = true; clearTimeout(timer); cleanup();
      if (Number(errno) !== 0) { reject(new Error(bounded(stderr || `Support export failed (${errno})`, 320))); return; }
      if (String(stdout || '').trim() !== expected) { reject(new Error('Support export returned an unexpected destination')); return; }
      resolve(expected);
    };
    try { globalThis.ksu.exec(command, JSON.stringify({}), callback); }
    catch (error) { clearTimeout(timer); cleanup(); reject(error); }
  });
}

// Final SB-C04 returns protocol.Response for both capabilities transports.
function unwrapCatalog(value) {
  if (value?.schema_version === 1 && value?.ok === true && value?.result?.operations) return value.result;
  return value;
}
export function validateCapabilities(value) {
  if (!value || value.schema_version !== SCHEMA_VERSION) throw new Error('Unsupported backend capability schema');
  const minimum = Number(value.protocol?.min ?? 0);
  const maximum = Number(value.protocol?.max ?? 0);
  if (!(minimum <= PROTOCOL_VERSION && maximum >= PROTOCOL_VERSION)) {
    throw new Error(`Backend protocol ${minimum}-${maximum} is incompatible with WebUI protocol ${PROTOCOL_VERSION}`);
  }
  if (!Array.isArray(value.operations)) throw new Error('Backend operation registry is missing');
  return value;
}

export async function capabilities() {
  if (selected === 'standalone') {
    const response = await fetch('/api/v1/capabilities', { credentials: 'same-origin', cache: 'no-store' });
    if (!response.ok) throw new Error(`Capabilities request failed (${response.status})`);
    return unwrapCatalog(await response.json());
  }
  if (selected === 'embedded') return unwrapCatalog(await embeddedCapabilities());
  throw new Error('Transport is not selected');
}

async function sendEnvelope(envelope) {
  if (selected === 'standalone') {
    const token = csrf();
    if (!token) throw new Error('Standalone CSRF token is unavailable');
    const operationClass = envelope.operation.class;
    const route = CLASS_PATH[operationClass];
    const response = await fetch(`/api/v1/${route}/${encodeURIComponent(envelope.operation.name)}`, {
      method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {
        'Content-Type': 'application/json',
        'X-Skybind-CSRF': token,
        'X-Skybind-Request-ID': envelope.request_id,
      },
      body: JSON.stringify(envelope.operation.args ?? {}),
    });
    if (!response.ok) throw new Error(`Typed ${operationClass} failed (${response.status})`);
    return normalizeResponse(await response.json());
  }
  if (selected === 'embedded') {
    return normalizeResponse(await embeddedExec(base64url(envelope)));
  }
  throw new Error('Transport is not selected');
}

function normalizeResponse(value) {
  // Retained app.js consumes a response wrapper; C04 returns the canonical
  // native response directly. Reject malformed native responses explicitly.
  if (!value || value.schema_version !== 1 || typeof value.ok !== 'boolean' || !value.request_id) {
    throw new Error('Malformed typed backend response');
  }
  return { response: value };
}

export async function authenticateStandalone(token) {
  if (selected !== 'standalone') throw new Error('Standalone transport is not selected');
  if (!/^[0-9a-f]{64}$/.test(token)) throw new Error('Invalid one-use authentication token');
  const response = await fetch('/auth/bootstrap', {
    method: 'POST', credentials: 'same-origin', cache: 'no-store',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  if (!response.ok) throw new Error('Token invalid, expired, or previously used');
  return response.json();
}

// The original WebUI's presentation API predates the native Skybind schema.
// This explicit typed adapter translates *known* requests and result shapes.
// It does not expose generic execution, arbitrary paths, or new operations.
let configRevision = 0;
let jobRevision = 0;
function responseFor(id, value) { return { response: { schema_version: 1, request_id:id, ok:true, result:value } }; }
function nativeValue(reply) {
  if (!reply?.response?.ok) throw new Error(reply?.response?.error?.message || reply?.response?.error?.code || 'Typed backend rejected operation');
  return reply.response.result;
}
async function native(name, klass, args={}) {
  return nativeValue(await sendEnvelope(requestEnvelope(name,klass,args)));
}
function seconds(input) {
  if (typeof input === 'number') return Math.max(0,Math.floor(input));
  const str=String(input||'').toLowerCase().trim(); if (!str || str==='off' || str==='0') return 0;
  const pattern=/^(\d+(?:\.\d+)?)(s|m|h|d|w)$/;
  const m=str.match(pattern); if(!m) throw new Error('Unsupported duration; use 30s, 15m, 24h or 7d');
  return Math.floor(Number(m[1])*({s:1,m:60,h:3600,d:86400,w:604800})[m[2]]);
}
function byteCount(input) {
  if(typeof input==='number')return Math.max(0,Math.floor(input));
  const raw=String(input||'').trim();if(!raw)return 0;
  const m=raw.match(/^(\d+(?:\.\d+)?)\s*(b|kb|kib|mb|mib|gb|gib|tb|tib)?$/i);
  if(!m)throw new Error('Unsupported byte size');
  const multi={b:1,kb:1e3,kib:1024,mb:1e6,mib:1048576,gb:1e9,gib:1073741824,tb:1e12,tib:1099511627776};
  return Math.floor(Number(m[1])*(multi[(m[2]||'b').toLowerCase()]));
}
function toNativeMount(m) {
  return {
    name:m.name,enabled:Boolean(m.enabled),remote:m.remote,mountpoint:m.mountpoint,
    vfs_profile:m.vfs_profile||'custom',cache_mode:m.vfs_cache_mode||m.cache_mode||'full',
    cache_max_bytes:byteCount(m.vfs_cache_max_size||m.cache_max_bytes),
    cache_max_age_seconds:seconds(m.vfs_cache_max_age||m.cache_max_age_seconds),
    dir_cache_seconds:seconds(m.dir_cache_time||m.dir_cache_seconds),poll_seconds:seconds(m.poll_interval||m.poll_seconds),
    allow_other:Boolean(m.allow_other),read_only:Boolean(m.read_only),log_level:m.log_level||'INFO',
    network_mode:m.network_mode||'any',charging_only:Boolean(m.charging_only),
    min_battery_percent:Number(m.min_battery??m.min_battery_percent??0),
    min_cache_free_bytes:byteCount(m.min_free_cache_space||m.min_cache_free_bytes),
    boot_settle_seconds:seconds(m.boot_settle||m.boot_settle_seconds),
    network_settle_seconds:seconds(m.network_settle||m.network_settle_seconds),
    cache_high_percent:Number(m.cache_high_water??m.cache_high_percent??90),
    cache_low_percent:Number(m.cache_low_water??m.cache_low_percent??75),
  };
}
function fromNativeMount(m) {return {
 ...m,vfs_cache_mode:m.cache_mode,vfs_cache_max_size:String(m.cache_max_bytes||''),
 vfs_cache_max_age: m.cache_max_age_seconds?`${m.cache_max_age_seconds}s`:'',
 dir_cache_time:m.dir_cache_seconds?`${m.dir_cache_seconds}s`:'',
 poll_interval:m.poll_seconds?`${m.poll_seconds}s`:'',min_battery:m.min_battery_percent,
 min_free_cache_space:String(m.min_cache_free_bytes||''),
 boot_settle:m.boot_settle_seconds?`${m.boot_settle_seconds}s`:'',
 network_settle:m.network_settle_seconds?`${m.network_settle_seconds}s`:'',
 cache_high_water:m.cache_high_percent,cache_low_water:m.cache_low_percent,
 };}
function nativeConfig(mounts,rev){return {schema_version:2,revision:rev,mounts:(mounts||[]).map(toNativeMount)};}
function fromPlan(p){return {current_revision:p.base_revision,candidate_digest:p.candidate_digest,preview_proof:p.proof,preview_expires_unix_ms:Date.now()+90000,changes:(p.effects||[]).map(x=>({name:x.name,kind:x.change,reasons:[],consequences:[]}))};}
function toNativeJob(j) {return {
 name:j.name,kind:j.type||j.kind,source:j.source,destination:j.destination,enabled:Boolean(j.enabled),
 interval_seconds:seconds(j.every||j.interval_seconds),network_mode:j.network_mode||'any',
 charging_only:Boolean(j.charging_only),min_battery_percent:Number(j.min_battery||j.min_battery_percent||0),
 next_unix:Number(j.next_unix||0),last_run_id:j.last_run_id||'',
 };}
function fromNativeJob(j){return {...j,type:j.kind,every:`${j.interval_seconds||3600}s`,min_battery:j.min_battery_percent};}
function nativeJobs(js,rev){return {schema_version:1,revision:rev,jobs:(js||[]).map(toNativeJob)};}
function fromState(s){return { ...s, state:s.observed||s.state||'UNKNOWN',enabled:Boolean(s.desired) };}
async function compatibleSend(envelope) {
 const {name,klass,args}={name:envelope.operation.name,klass:envelope.operation.class,args:envelope.operation.args||{}};
 const id=envelope.request_id;
 // Preserve the original UI result contract while relying on the typed backend authority.
 if(name==='runtime.status')return responseFor(id,runtimePresentation(await native(name,'query')));
 if(name==='platform.status')return responseFor(id,platformPresentation(await native(name,'query')));
 if(name==='doctor.report')return responseFor(id,doctorPresentation(await native(name,'query',{})));
 if(name==='doctor.bundle')return responseFor(id,bundleMetadata(await native(name,'run',{})));
 if(name==='doctor.bundle.read') {
  const requested=args.bundle_id||args.id;
  const v=await native(name,'query',{id:requested});
  return responseFor(id,await supportDownload(v,requested));
 }
 if(name==='provider.crypt.password.status')return responseFor(id,passwordStatus(await native(name,'query')));
 if(name==='provider.crypt.password.set')return responseFor(id,passwordStatus(await native(name,'run',args)));
 if(name==='provider.crypt.recovery.status') {
  const [status,recovery]=await Promise.all([native('provider.crypt.password.status','query'),native(name,'query')]);
  return responseFor(id,recoveryPresentation(recovery,status));
 }
 // Query collections are compositions of the exact native named operations.
 if(name==='mount.status'&&!args.name){
  const names=await native('mount.list','query');
  const rows=await Promise.all((names||[]).map(async n=>fromState(await native('mount.status','query',{name:n}))));
  return responseFor(id,{mounts:rows});
 }
 if(['mount.health','policy.status','cache.status'].includes(name)&&!args.name){
  const names=await native('mount.list','query');
  const rows=await Promise.all((names||[]).map(async n=>{
   try{return {...(await native(name,'query',{name:n})),name:n};}
   catch(error){return {name:n,state:'UNKNOWN',reason:String(error?.message||error),qualified:false};}
  }));
  return responseFor(id,{[name==='mount.health'?'health':name==='policy.status'?'policies':'caches']:rows});
 }
 if(name==='operation.list'){const v=await native('operation.list','query');let status=null;try{status=await native('jobs.status','query');}catch(_){}return responseFor(id,{operations:presentActivity(v||[],status)});}
 if(name==='operation.status') {
  const record=await native(name,'query',{id:args.request_id||args.id});
  let status=null;try{if(record.run_id)status=await native('jobs.status','query');}catch(_){}
  return responseFor(id,presentActivity([record],status)[0]);
 }
 if(name==='operation.cancel')return sendEnvelope({...envelope,operation:{...envelope.operation,args:{id:args.run_id||args.request_id||args.id}}});
 if(name==='config.snapshot'){
  const v=await native(name,'query');configRevision=v.revision;
  return responseFor(id,{...v,mounts:(v.mounts||[]).map(fromNativeMount)});
 }
 if(name==='config.validate'||name==='config.preview'){
  const v=nativeConfig(args.mounts,configRevision);
  const result=await native(name,klass,{candidate:v});
  return responseFor(id,name==='config.validate'?{valid:true,issues:[]}:fromPlan(result));
 }
 if(name==='config.apply'){
  const v=nativeConfig(args.mounts,args.expected_revision);
  const result=await native(name,'run',{candidate:v,proof:args.preview_proof});
  configRevision=result.revision;
  return responseFor(id,{...result,mounts:(result.mounts||[]).map(fromNativeMount),lifecycle_failures:[]});
 }
 if(name==='config.rollback.preview')return responseFor(id,fromPlan(await native(name,'preview',{})));
 if(name==='config.rollback'){
  const v=await native(name,'run',{proof:args.preview_proof});configRevision=v.revision;
  return responseFor(id,{...v,mounts:(v.mounts||[]).map(fromNativeMount)});
 }
 if(name==='mount.start.preview'){
  const p=await native(name,'preview',{name:args.name});return responseFor(id,{...p,preview_proof:p.proof});
 }
 if(name==='jobs.snapshot'){
  const v=await native(name,'query');jobRevision=v.revision;
  return responseFor(id,{...v,jobs:(v.jobs||[]).map(fromNativeJob)});
 }
 if(name==='jobs.status'){
  const v=await native(name,'query');return responseFor(id,{jobs:presentJobStatus(v)});
 }
 if(name==='jobs.preview'){
  const p=await native(name,'preview',{candidate:nativeJobs(args.jobs,jobRevision)});
  return responseFor(id,{current_revision:p.base_revision,preview_proof:p.proof,destructive_sync_jobs:p.includes_destructive_sync?args.jobs.filter(j=>j.type==='sync').map(j=>j.name):[]});
 }
 if(name==='jobs.apply'){
  const v=await native(name,'run',{candidate:nativeJobs(args.jobs,args.expected_revision),proof:args.preview_proof});jobRevision=v.revision;
  return responseFor(id,{...v,jobs:(v.jobs||[]).map(fromNativeJob)});
 }
 if(name==='job.run.preview'){
  const p=await native(name,'preview',{name:args.name});return responseFor(id,{...p,preview_proof:p.proof});
 }
 if(name==='provider.remotes'){
  const remotes=await native(name,'query');
  return responseFor(id,{remotes:(remotes||[]).map(r=>r.name),details:(remotes||[]).map(r=>({...r,encryption:r.encrypted?'rclone-crypt':'plain',managed_by_skybind:Boolean(r.managed_by_skybind),password_revision:r.password_revision||null,password_current:Boolean(r.password_current)}))});
 }
 if(name==='provider.browse'){
  const path=String(args.path||'').replace(/^\/+|\/+$/g,'');
  const results=await native(name,'query',{remote:`${args.remote}:${path}`});
  return responseFor(id,{path,entries:(results||[]).map(e=>({path:e.Path,name:e.Name,size:e.Size,is_dir:Boolean(e.IsDir)})),truncated:false});
 }
 if(name==='provider.crypt.preview'){
  const p=await native(name,'preview',{name:args.spec.name,remote:args.spec.remote,filename_mode:args.spec.filename_encryption,directory_names:args.spec.directory_name_encryption,encoding:args.spec.filename_encoding});
  return responseFor(id,{spec:args.spec,preview_proof:p.proof});
 }
 if(name==='provider.crypt.create'){
  const spec=args.spec;
  const p=await native(name,'run',{spec:{name:spec.name,remote:spec.remote,filename_mode:spec.filename_encryption,directory_names:spec.directory_name_encryption,encoding:spec.filename_encoding},proof:args.preview_proof});
  return responseFor(id,{remote:{name:p.created,encrypted:Boolean(p.encrypted)}});
 }
 return sendEnvelope(envelope);
}

export function startOperation(name, operationClass, args = {}) {
  const envelope = requestEnvelope(name, operationClass, args);
  return { requestId: envelope.request_id, completion: compatibleSend(envelope) };
}

export async function invoke(name, operationClass, args = {}) {
  return startOperation(name, operationClass, args).completion;
}

export async function query(name, args = {}) { return invoke(name, 'query', args); }
export async function preview(name, args = {}) { return invoke(name, 'preview', args); }
export async function run(name, args = {}) { return invoke(name, 'run', args); }
export async function reconcile(name, args = {}) { return invoke(name, 'reconcile', args); }
export async function cancel(name, args = {}) { return invoke(name, 'cancel', args); }
