// Explicit, read-only KernelSU acceptance probe. No mutation or user-data export.
// An ordinary CLI call or standalone WebUI never passes the embedded transport gate.
import { transportName, query } from './bridge.js';

const MAX_ROWS = 8;
const safeInt = value => Number.isSafeInteger(value) && value >= 0;
const now = () => new Date().toISOString();

export function classifyReplay(prior, result) {
  if (!result || !safeInt(result.latest_cursor) || !safeInt(result.next_cursor) ||
      !Array.isArray(result.events) || result.events.length > 64) return 'FAIL';
  if (result.degraded) return 'BLOCKED';
  if (prior && result.latest_cursor < prior.latest) return 'FAIL';
  if (prior && prior.latest > 0 && result.cursor_reset) return 'FAIL';
  if (prior && result.gap && !safeInt(result.oldest_cursor)) return 'FAIL';
  if (result.events.some(e => !safeInt(e.sequence))) return 'FAIL';
  for (let i=1;i<result.events.length;i++) if (result.events[i].sequence <= result.events[i-1].sequence) return 'FAIL';
  return 'PASS';
}

function probeUI() {
  const container = document.getElementById('apiQaProbe');
  if (!container) return;
  const start = document.getElementById('apiQaProbeStart');
  const output = document.getElementById('apiQaProbeOutput');
  const copy = document.getElementById('apiQaProbeCopy');
  const status = document.getElementById('apiQaProbeStatus');
  let pending = false;
  start.addEventListener('click', async () => {
    if (pending) return;
    pending = true; start.disabled = true; status.textContent='Observing live embedded bridge…';
    const previous = (() => {try {
      const x=JSON.parse(sessionStorage.getItem('skybind.qa.cursor.v1') || 'null');
      return x && safeInt(x.latest) ? x : null;
    } catch (_) {return null;}})();
    const report = {schema_version:1,kind:'SKYBIND_KSU_WEBVIEW_READONLY_PROBE',
      recorded_at_utc:now(),qualifier:'RAW_UNATTESTED',
      evidence_origin:'in-page WebUI JavaScript (requires actual external device verification)',
      observations:[], remaining:['visual UI navigation and redacted screenshot verification',
        'disposable preview, confirmation, progress and cancellation through actual WebUI',
        'close/reopen WebView and validate retained cursor',
        'transient ksu.exec error injection/recovery and no duplicate mutation']};
    const put=(test,verdict,detail='')=>report.observations.push({test,status:verdict,detail});
    const actual = Boolean(globalThis.ksu && typeof globalThis.ksu.exec === 'function') && transportName()==='embedded';
    if (!actual) {
      put('Actual KernelSU ksu.exec transport','BLOCKED','embedded runtime is not selected');
    } else {
      put('Actual KernelSU ksu.exec transport','PASS','embedded selected with ksu.exec function');
      try {
        const response=await query('operation.events', {cursor:0, limit:32, wait_ms:0});
        if (response?.response?.ok !== true) throw Error('not ok');
        const p=response.response.result;
        const verdict=classifyReplay(previous,p);
        put('Embedded operation.events read and cursor',verdict,'bounded replay and monotonicity checked');
        if (verdict==='PASS') {
          sessionStorage.setItem('skybind.qa.cursor.v1',JSON.stringify({latest:p.latest_cursor,utc:now()}));
        }
      } catch (_) {put('Embedded operation.events read and cursor','FAIL','embedded callback failed or result invalid');}
      try {
        const response=await query('jobs.status');
        // The legacy WebUI adapter intentionally presents jobs, while the
        // device-native bridge returns runs. Never assert the two are identical.
        const value=response?.response?.result;
        const valid=response?.response?.ok===true && value && Array.isArray(value.jobs);
        put('Embedded jobs.status presentation',valid?'PASS':'FAIL','read-only jobs presentation envelope');
      } catch (_) {put('Embedded jobs.status presentation','FAIL','embedded callback failed');}
    }
    for (const item of report.remaining.slice(0,MAX_ROWS)) put(item,'BLOCKED','requires distinct real-device evidence');
    report.counts={PASS:report.observations.filter(x=>x.status==='PASS').length,
      FAIL:report.observations.filter(x=>x.status==='FAIL').length,
      BLOCKED:report.observations.filter(x=>x.status==='BLOCKED').length};
    output.value=JSON.stringify(report,null,2);status.textContent=`Raw probe: ${report.counts.PASS} PASS / ${report.counts.FAIL} FAIL / ${report.counts.BLOCKED} BLOCKED`;
    pending=false;start.disabled=false;
  });
  copy.addEventListener('click', async () => {
    if (!output.value) return;
    try {await navigator.clipboard.writeText(output.value);status.textContent='Sanitized receipt copied; attach it to the device gate report.';}
    catch (_) {output.focus();output.select();status.textContent='Copy is unavailable; selection is ready for manual copy.';}
  });
}
if (typeof document !== 'undefined') probeUI();
