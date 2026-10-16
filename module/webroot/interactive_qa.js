// V9 interactive evidence capture. Does not start, cancel, or modify user jobs.
// All UI events and backend reads are sanitized before they leave the device.
import { transportName, query, armQaReadOnlyEventsFault, disarmQaReadOnlyEventsFault, qaBridgeCounters } from './bridge.js';

const ID = /^[a-f0-9]{32}$/;
const STORAGE_KEY = 'skybind.qa.v9.owned.before';
const DOC_ID = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2)}`;
const now = () => new Date().toISOString();
const byId = id => document.getElementById(id);
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const sha256 = async text => {
  if (!globalThis.crypto?.subtle) return null;
  const bytes=new TextEncoder().encode(text);
  const hash=await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
};
const ok = response => { if (response?.response?.ok !== true) throw Error('read-only backend response rejected'); return response.response.result; };
const sampleRun = (snapshot, id) => {
  if (!snapshot || !Array.isArray(snapshot.runs)) return null;
  const value = snapshot.runs.find(run => run?.id === id);
  return value ? {state: value.state, bytes: Number.isFinite(value.bytes) ? value.bytes : null} : null;
};
const sampleEvents = (page, id) => {
  if (!page || !Array.isArray(page.events) || !Number.isSafeInteger(page.latest_cursor) ||
      !Number.isSafeInteger(page.next_cursor)) throw Error('invalid event page');
  const ev = page.events.filter(item => item?.run_id === id || item?.operation_id === id);
  return {cursor:page.next_cursor, latest:page.latest_cursor, gap:!!page.gap,
    degraded:!!page.degraded, reset:!!page.cursor_reset,
    progress:ev.filter(e => e.type==='job.progress').length,
    cancelled:ev.some(e => e.type==='job.cancelled'),
    terminal:ev.some(e => ['job.cancelled','job.failed','job.completed','job.interrupted'].includes(e.type)),
    sequences:ev.map(e => e.sequence).filter(Number.isSafeInteger).slice(0,64)};
};
const status = text => { if (byId('apiV9Status')) byId('apiV9Status').textContent=text; };
const validRun = () => {
  const id=(byId('apiV9OwnedRun')?.value||'').trim().toLowerCase();
  if (!ID.test(id)) throw Error('A 32-character test-owned run ID is required');
  return id;
};
const report = {schema_version:1,kind:'SKYBIND_WEBUIX_INTERACTIVE_V9',
  recorded_at_utc:now(),qualification:'IN_PAGE_RAW_UNATTESTED',
  host:'webuix_or_embedded_unverified',
  document_id:DOC_ID,observations:{}, limitations:[
    'In-page DOM evidence is not an independent Android screenshot or accessibility dump',
    'A reload with different document ID alone does not prove the Android app was closed',
    'Job ownership is not established by typing a job ID; requires independent host proof',
    'The bridge fault is synthetic for one read-only query, not a physical KernelSU outage']};

const trusted = {nav:new Set(),preview:false,confirm:false,confirmEvidence:null,cancel:false,cancelPrefix:'',cancelTime:''};
if (typeof document !== 'undefined') {
  document.addEventListener('click',event => {
    if (!event.isTrusted) return;
    const node=event.target?.closest?.('[data-view],#remoteTransferPreview,#remoteTransferStart,.phase-a-live-cancel');
    if (!node) return;
    if (node.dataset?.view && ['remotes','more','jobs','activity'].includes(node.dataset.view)) trusted.nav.add(node.dataset.view);
    if (node.id==='remoteTransferPreview') trusted.preview=true;
    if (node.id==='remoteTransferStart' && !node.disabled) {
      trusted.confirm=true;
      const source=byId('remoteTransferSource')?.value||'';
      const destination=byId('remoteTransferDestination')?.value||'';
      const kind=byId('remoteTransferKind')?.value||'';
      if (source && destination && kind==='copy' &&
          byId('remoteTransferPreviewText')?.textContent?.includes('Single-use proof valid')) {
        // Captured BEFORE the ordinary click handler consumes its one-time proof.
        void Promise.all([sha256(source),sha256(destination)]).then(([a,b]) => {
          trusted.confirmEvidence={trusted_confirm:true,kind:'copy',
            source_endpoint_sha256:a,destination_endpoint_sha256:b};
        }).catch(()=>{});
      }
    }
    if (node.classList.contains('phase-a-live-cancel')) {
      const text=node.closest('.phase-a-live-row')?.querySelector('strong')?.textContent||'';
      const id=(byId('apiV9OwnedRun')?.value||'').trim().toLowerCase();
      if (ID.test(id) && text.includes(id.slice(0,8))) {
        trusted.cancel=true;trusted.cancelPrefix=id.slice(0,8);trusted.cancelTime=now();
      }
    }
  },true);
}
function save() {
  report.recorded_at_utc=now();
  if (byId('apiV9Output')) byId('apiV9Output').value=JSON.stringify(report,null,2);
  const states=Object.values(report.observations).map(x=>x.status);
  status(`${states.filter(x=>x==='PASS').length} in-page PASS / ${states.filter(x=>x==='FAIL').length} FAIL / ${states.filter(x=>x==='BLOCKED').length} BLOCKED. Host verification remains required.`);
}
function record(name,state,detail) {
  report.observations[name]={status:state,...detail};save();
}
const run = async (name, work) => {
  const btn=byId(name);
  if (btn?.disabled) return;
  if (btn) btn.disabled=true;
  try {await work();} catch(error){ status(`BLOCKED: ${String(error?.message||error).slice(0,110)}`); }
  finally {if(btn)btn.disabled=false;save();}
};
export function evaluateNavigation(v) {
  // IDs and actual navigation callbacks plus a preview with an enabled confirmation.
  // No raw label values or paths leave the WebView.
  const structural=!!(v.page&&v.title&&v.preview_control&&v.confirm_control);
  return structural && v.trusted_navigation && v.trusted_preview && v.proof_present &&
         v.confirm_enabled && v.preview_is_readonly_kind
    ? 'PASS' : 'BLOCKED';
}
export function evaluateReconnect(before,after) {
  if (!before || !after || before.doc === after.doc || before.run_id!==after.run_id) return 'BLOCKED';
  if (after.event.gap || after.event.degraded || after.event.reset ||
      after.event.latest < before.event.latest || after.event.cursor < before.event.cursor) return 'BLOCKED';
  if (!before.state || !after.state || !before.event.progress) return 'BLOCKED';
  return 'PASS';
}
export function evaluateCancelled(e) {
  if (!e || !e.trusted_cancel || !e.cancel_event || e.final_state!=='CANCELLED' ||
      !e.independently_owned) return 'BLOCKED';
  return 'PASS';
}
const nav = async () => {
  // Observe the actual Skybind controls, never fabricate an Android screenshot.
  const view=byId('view-remotes');
  const preview=byId('remoteTransferPreview');
  const confirm=byId('remoteTransferStart');
  const source=byId('remoteTransferSource')?.value||'';
  const destination=byId('remoteTransferDestination')?.value||'';
  const v={page:!!view, title:!!byId('remoteTransferHeading'),preview_control:!!preview,
    confirm_control:!!confirm, trusted_navigation:trusted.nav.has('remotes')&&trusted.nav.has('more'),
    trusted_preview:trusted.preview, trusted_confirm:trusted.confirm,
    proof_present:!!byId('remoteTransferPreviewText')?.textContent?.includes('Single-use proof valid'),
    confirm_enabled:!!confirm && !confirm.disabled,
    preview_is_readonly_kind:byId('remoteTransferKind')?.value==='check',
    trusted_copy_launch:trusted.confirmEvidence,
    source_endpoint_sha256:source?await sha256(source):null,
    destination_endpoint_sha256:destination?await sha256(destination):null,
    captured_without_paths:true};
  // The UI has to have been reached through actual trusted navigation.
  record('navigation_preview',evaluateNavigation(v),v);
};
const beforeReopen=async () => {
  const id=validRun();
  if (transportName()!=='embedded') throw Error('Actual embedded WebUI X bridge is required');
  const snapshot=ok(await query('jobs.status'));
  const event=sampleEvents(ok(await query('operation.events',{cursor:0,limit:64,operation_id:id,wait_ms:0})),id);
  const state=sampleRun(snapshot,id);
  if (!state) throw Error('Run ID is not present in authoritative jobs.status');
  const value={schema_version:1,doc:DOC_ID,run_id:id,state:state.state,event,at:now()};
  try{localStorage.setItem(STORAGE_KEY,JSON.stringify(value));}
  catch(_){throw Error('Reopen checkpoint storage unavailable');}
  record('reconnection','BLOCKED',{stage:'before_reopen',state:state.state,progress_samples:event.progress,
    baseline_cursor:event.cursor,baseline_latest:event.latest,document_id:DOC_ID,
    evidence:'reopen and capture second document required'});
};
const afterReopen=async () => {
  const id=validRun();
  let before;
  try{before=JSON.parse(localStorage.getItem(STORAGE_KEY)||'null');}
  catch(_){throw Error('Reopen checkpoint malformed');}
  if (before?.run_id!==id) throw Error('Reopen session does not match the selected owned ID');
  const snapshot=ok(await query('jobs.status'));
  const state=sampleRun(snapshot,id);
  const event=sampleEvents(ok(await query('operation.events',{cursor:before.event.cursor,limit:64,operation_id:id,wait_ms:0})),id);
  const value={doc:DOC_ID,run_id:id,state:state?.state,event};
  const result=evaluateReconnect(before,value);
  record('reconnection',result,{stage:'post_document_load',distinct_document_id:before.doc!==DOC_ID,
    previous_state:before.state,authoritative_state:state?.state||'missing',
    cursor_monotonic:event.cursor>=before.event.cursor,
    last_sequence_monotonic:event.latest>=before.event.latest,
    baseline_progress_samples:before.event.progress,replay_progress_samples:event.progress,
    gap:event.gap,degraded:event.degraded,reset:event.reset,run_id:id,
    document_identity_only_no_android_close_attestation:true});
};
const cancelled=async () => {
  const id=validRun();
  const snapshot=ok(await query('jobs.status'));
  const state=sampleRun(snapshot,id);
  const event=sampleEvents(ok(await query('operation.events',{cursor:0,limit:64,operation_id:id,wait_ms:0})),id);
  const v={trusted_cancel:trusted.cancel && trusted.cancelPrefix===id.slice(0,8),
    cancel_event:event.cancelled,final_state:state?.state||'missing',independently_owned:false};
  record('owned_cancellation','BLOCKED',{...v,run_id:id,
    note:'only native collector with independent ownership receipt may qualify cancellation; no QA control cancelled a job'});
};
const fault=async () => {
  if (transportName()!=='embedded')throw Error('Read-only fault requires WebUI X embedded transport');
  // Use actual production Jobs navigation and its normal event polling.
  // The click is programmatic and is NOT counted as trusted navigation proof.
  document.querySelector('.nav-item[data-view="jobs"]')?.click();
  for(let i=0;i<20;i++){
    if (!byId('view-jobs')?.hidden && byId('phaseALive-jobs')) break;
    await sleep(250);
  }
  if (byId('view-jobs')?.hidden || !byId('phaseALive-jobs'))
    throw Error('Actual Jobs UI did not become ready');
  let armed=false;
  try {
    const pre=qaBridgeCounters();
    const page=ok(await query('operation.events',{cursor:0,limit:1,wait_ms:0}));
    const cursor=page.latest_cursor;
    if (!armQaReadOnlyEventsFault()) throw Error('Read-only fault already pending or bridge unavailable');
    armed=true;
    let consumed=false, recovered=false;
    const deadline=Date.now()+15000;
    while(Date.now()<deadline) {
      await sleep(600);
      const counters=qaBridgeCounters();
      if (counters.injected_faults===pre.injected_faults+1) consumed=true;
      if (consumed && counters.pending_readonly_fault===0) {
        const visible=byId('phaseALive-jobs')?.textContent||'';
        if (visible.includes('Connected')) {recovered=true;break;}
      }
    }
    const post=qaBridgeCounters();
    const fresh=ok(await query('operation.events',{cursor:0,limit:1,wait_ms:0}));
    const noMutation=post.mutation_dispatches===pre.mutation_dispatches;
    const monotonic=fresh.latest_cursor>=cursor;
    const verdict=consumed&&recovered&&noMutation&&monotonic?'PASS':'BLOCKED';
    record('read_only_bridge_recovery',verdict,{one_shot_fault_consumed:consumed,
      ui_recovered:recovered,mutations_dispatched_during_test:post.mutation_dispatches-pre.mutation_dispatches,
      replay_cursor_monotonic:monotonic,raw_ksu_outage_attested:false,
      mechanism:'synthetic callback failure, restricted to one operation.events query'});
  } finally {
    if (armed) disarmQaReadOnlyEventsFault();
    document.querySelector('.nav-item[data-view="more"]')?.click();
  }
};
if (typeof document!=='undefined') {
  for(const [id,fn] of [
    ['apiV9Navigation',nav],['apiV9Fault',fault],['apiV9Before',beforeReopen],
    ['apiV9After',afterReopen],['apiV9Cancellation',cancelled]]) {
    byId(id)?.addEventListener('click',()=>void run(id,fn));
  }
  byId('apiV9Export')?.addEventListener('click',async () => {
    save();const value=byId('apiV9Output')?.value;
    if (!value) return;
    try {await navigator.clipboard.writeText(value);status('Sanitized V9 receipt copied.');}
    catch(_) {byId('apiV9Output')?.select();status('Clipboard unavailable; select the sanitized receipt manually.');}
  });
}
