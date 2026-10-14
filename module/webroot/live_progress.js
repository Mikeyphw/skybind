// Phase A2: pure, bounded projection of the authenticated Phase A1 event feed.
// All text in the feed originates from Phase A1's server-side allowlist.
export const OPERATION_ID = /^[a-f0-9]{32}$/;
const TERMINAL = new Set(['job.completed', 'job.failed', 'job.cancelled', 'job.interrupted', 'operation.succeeded', 'operation.failed']);
const PHASES = new Set(['running', 'completed', 'succeeded', 'failed', 'cancelled', 'interrupted']);
export function createLiveFeed() {
  return { cursor: 0, latest: 0, records: [], gap: false, degraded: false, reset: false };
}
function safeNumber(value, fallback = null) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}
export function projectLiveEvent(input) {
  if (!input || !Number.isSafeInteger(input.sequence) || input.sequence < 1 ||
      !OPERATION_ID.test(input.operation_id) ||
      (input.run_id && !OPERATION_ID.test(input.run_id)) ||
      typeof input.type !== 'string' || !/^(job|operation)\.[a-z_]+$/.test(input.type) ||
      typeof input.state !== 'string' || !/^[a-z_]{1,20}$/.test(input.state) ||
      typeof input.phase !== 'string' || !/^[a-z_]{1,30}$/.test(input.phase) ||
      !Number.isSafeInteger(input.unix_millis) || input.unix_millis < 0) return null;
  const p = input.progress;
  return {
    sequence: input.sequence, time: input.unix_millis, id: input.run_id || input.operation_id,
    runId: input.run_id || (input.type.startsWith('job.') ? input.operation_id : ''),
    type: input.type, state: input.state, phase: input.phase,
    bytes: safeNumber(p?.bytes), speed: safeNumber(p?.speed_bytes_per_second),
    eta: safeNumber(p?.eta_seconds), terminal: TERMINAL.has(input.type),
  };
}
export function consumeLivePage(feed, page) {
  if (!page || page.schema_version !== 1 || !Array.isArray(page.events) || page.events.length > 64 ||
      !Number.isSafeInteger(page.next_cursor) || page.next_cursor < 0 ||
      !Number.isSafeInteger(page.latest_cursor) || page.latest_cursor < 0) {
    throw new Error('Invalid Phase A operation-event page');
  }
  if (page.cursor_reset) { feed.records = []; feed.cursor = 0; feed.reset = true; }
  if (page.gap) { feed.records = []; feed.gap = true; }
  let previous = feed.cursor;
  for (const raw of page.events) {
    const event = projectLiveEvent(raw);
    if (!event || event.sequence <= previous) throw new Error('Out-of-order Phase A event');
    previous = event.sequence;
    feed.records.push(event);
  }
  if (page.next_cursor < previous || page.next_cursor > page.latest_cursor) throw new Error('Invalid Phase A event cursor');
  feed.cursor = page.next_cursor;
  feed.latest = page.latest_cursor;
  feed.degraded = Boolean(page.degraded);
  // Keep enough context for the active jobs while never growing without bound.
  if (feed.records.length > 96) feed.records.splice(0, feed.records.length - 96);
  return { more: Boolean(page.has_more), reconcile: Boolean(page.gap || page.cursor_reset || page.degraded), terminal: page.events.some(e => TERMINAL.has(e.type)) };
}
export function latestLiveJobs(feed) {
  const runs = new Map();
  for (const event of feed.records) if (event.runId) runs.set(event.runId, event);
  return [...runs.values()].sort((a,b) => b.sequence-a.sequence);
}
export function formatLiveProgress(event, formatBytes) {
  const parts=[];
  if (event.bytes !== null) parts.push(`${formatBytes(event.bytes)} transferred`);
  if (event.speed !== null && event.speed > 0) parts.push(`${formatBytes(event.speed)}/s`);
  if (event.eta !== null && event.eta > 0 && !event.terminal) parts.push(`ETA ${event.eta}s`);
  return parts.length ? parts.join(' · ') : 'Total size and percentage not available';
}
export function cancellableLiveRun(event, authoritativeStates) {
  return Boolean(event?.runId && OPERATION_ID.test(event.runId) &&
    !event.terminal && event.state === 'running' && event.type !== 'job.cancelling' &&
    authoritativeStates?.get(event.runId) === 'RUNNING');
}
