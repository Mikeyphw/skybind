import { authenticateStandalone, capabilities, cancel, preview, query, reconcile, run, selectTransport, startOperation, transportName, validateCapabilities } from './bridge.js';
import { eligibleNamespaceGroups, validateNamespaceSelection, nativeCachePreview } from './flow.js';
import { DEFAULT_MOUNT, activityPresentation, candidate, consequenceLabel, isDestructivePreview, localMountIssues, mountRows, operationSummary, parseRemoteEndpoint, previewIsUsable, profilePresentation, removeMount, replaceMount, suggestMountDefaults } from './model.js';

const byId = (id) => document.getElementById(id);
const compatibility = byId('compatibility');
const badge = byId('transportBadge');
const state = {
  caps: null, snapshot: null, activeView: 'home', timer: null, editorOriginal: '', editorDelete: false,
  preview: null, previewCandidates: null, rollbackPreview: null, refreshing: false,
  editorDirty: false, editorInitial: '', editorExisting: false, editorValidationTimer: null, editorValidationSeq: 0, editorIssues: [], editorStep: 0, editorInteracted: false,
  editorRemotes: [], editorProfiles: [], editorRecommendation: null, editorProviderStatus: null, editorRemotePath: '', editorManualRemote: false, editorRemoteReachable: null, editorNameTouched: false, editorMountpointTouched: false, editorProfileTouched: false, editorBackendValidated: false, editorTrigger: null, editorSession: 0, previewTimer: null, operationPollToken: 0, mountActionName: '', mountActionReturnFocus: null,
  jobSnapshot: null, jobOriginal: '', jobPreview: null, jobCandidates: null, jobReturnFocus: null, rollbackReturnFocus: null, settingsSnapshot: null, settingsPreview: null, logCursor: 0, logRecords: [], logPaused: false, remote: '', remotePath: '', remoteAction: null, remoteActionReturnFocus: null, remoteDetails: [], cryptPreview: null, cryptTrigger: null, cryptOnCreated: null, cryptPasswordStatus: null, cryptRecovery: null, 
  
};

function text(id, value) { const node = byId(id); if (node) node.textContent = String(value ?? '—'); }
function clear(node) { while (node?.firstChild) node.removeChild(node.firstChild); }
function backendError(envelope) {
  const error = new Error(envelope?.response?.error?.message || envelope?.response?.error?.code || 'Backend request failed');
  error.code = envelope?.response?.error?.code || 'backend_error';
  error.detail = envelope?.response?.error?.detail || '';
  error.category = envelope?.response?.error?.category || '';
  error.stage = envelope?.response?.error?.stage || '';
  error.exitCode = Number(envelope?.response?.error?.exit_code || 0);
  error.severity = envelope?.response?.error?.severity || 'error';
  error.retryable = Boolean(envelope?.response?.error?.retryable);
  error.issues = Array.isArray(envelope?.response?.error?.issues) ? envelope.response.error.issues : [];
  return error;
}
function result(envelope) {
  if (!envelope?.response) throw new Error('Backend envelope is missing a response');
  if (envelope.response.ok !== true) throw backendError(envelope);
  return envelope.response.result ?? {};
}
function countMounts(value) { return Array.isArray(value?.mounts) ? value.mounts.length : 0; }
function showNotice(node, message, kind = '') {
  if (!node) return;
  node.hidden = false; node.className = `notice compact ${kind}`.trim(); node.textContent = String(message);
}
function hideNotice(node) { if (node) { node.hidden = true; node.textContent = ''; } }
function showMountOutcome(message, kind = '', actions = []) {
  const node = byId('mountsNotice'); if (!node) return; clear(node); node.hidden = false; node.className = `notice compact ${kind}`.trim();
  node.append(paragraph(message));
  if (actions.length) { const row = document.createElement('div'); row.className = 'button-row notice-actions'; for (const action of actions) row.append(button(action.label, action.run, action.className || '')); node.append(row); }
}
function backendErrorText(error) {
  const code = error?.code && error.code !== 'backend_error' ? error.code : '';
  const message = String(error?.message || error || 'Operation failed');
  const detail = String(error?.detail || '').trim();
  const stage = String(error?.stage || '').trim();
  const exit = Number(error?.exitCode || 0);
  const context = [stage ? `stage ${stage}` : '', exit ? `exit ${exit}` : ''].filter(Boolean).join(' · ');
  return `${code ? `${code}: ` : ''}${message}${context ? ` (${context})` : ''}${detail && !message.includes(detail) ? ` · ${detail}` : ''}`;
}
function mountConfigByName(name) { return (state.snapshot?.mounts || []).find((item) => item.name === name); }
function openMountForEdit(name) { const cfg = mountConfigByName(name); if (cfg) openEditor(cfg); }
function showLifecycleFailure(name, action, error) {
  const actions = [
    { label: 'Edit mount', run: () => openMountForEdit(name), className: error?.retryable ? '' : 'primary' },
    { label: 'View logs', run: () => void setView('logs') },
    { label: 'View activity', run: () => void setView('activity') },
  ];
  if (error?.retryable) actions.unshift({ label: 'Retry now', run: () => void lifecycleAction(action === 'stop' ? 'start' : action, name), className: 'primary' });
  showMountOutcome(`${name}: ${backendErrorText(error)}`, 'error', actions);
}

function formatTime(value) { if (!value) return '—'; try { return new Date(Number(value)).toLocaleString(); } catch (_) { return '—'; } }
function label(textValue, className = 'state-pill') { const node = document.createElement('span'); node.className = className; node.textContent = String(textValue); return node; }
function paragraph(value, className = '') { const node = document.createElement('p'); if (className) node.className = className; node.textContent = String(value ?? ''); return node; }
function button(title, handler, className = '') { const node = document.createElement('button'); node.type = 'button'; node.textContent = title; if (className) node.className = className; node.addEventListener('click', handler); return node; }

function announceStatus(message) { text('viewStatus', message || ''); }
function setViewBusy(view, busy, message = '') {
  const node = byId(`view-${view}`);
  if (node) node.setAttribute('aria-busy', busy ? 'true' : 'false');
  if (message) announceStatus(message);
}
function setButtonBusy(node, busy, busyLabel = 'Working…') {
  if (!node) return;
  if (busy) { node.dataset.idleLabel = node.textContent; node.textContent = busyLabel; node.disabled = true; node.setAttribute('aria-busy','true'); }
  else { node.textContent = node.dataset.idleLabel || node.textContent; node.removeAttribute('aria-busy'); node.disabled = false; delete node.dataset.idleLabel; }
}

function focusableNodes(root) {
  return [...(root?.querySelectorAll('button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), summary, [tabindex]:not([tabindex="-1"])') || [])].filter((node) => !node.hidden && node.offsetParent !== null);
}
function trapModalTab(event, root) {
  if (event.key !== 'Tab' || !root || root.hidden) return false;
  const nodes = focusableNodes(root); if (!nodes.length) return false;
  const first = nodes[0], last = nodes.at(-1);
  if (!root.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); return true; }
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); return true; }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); return true; }
  return false;
}

function requiredOperations(caps) {
  const names = new Set(caps.operations.map((item) => item?.name));
  // Keep the original UX, but check only the bootstrap-critical API contract.
  // Individual views surface unsupported operations as actionable backend errors.
  const required = ['runtime.status','config.snapshot','mount.status','operation.list','ui.settings'];
  for (const name of required) if (!names.has(name)) throw new Error(`Backend is missing required operation: ${name}`);
}

async function ensureConnected() {
  if (state.caps) return state.caps;
  const transport = await selectTransport();
  badge.textContent = transport === 'embedded' ? 'Embedded manager bridge' : 'Standalone loopback';
  const caps = validateCapabilities(await capabilities());
  requiredOperations(caps); state.caps = caps;
  compatibility.hidden = true;
  compatibility.className = 'notice ok';
  compatibility.textContent = `Compatible backend connected through ${transportName()}. Runtime truth remains backend-owned.`;
  return caps;
}

function homeOperationTitle(name) {
  const value = String(name || '');
  // Runtime lifecycle history belongs to the retired mutable-runtime product line.
  // UX08 owns its historical presentation; Home intentionally excludes runtime.* journal rows.
  if (!value || value.startsWith('runtime.')) return '';
  const known = {
    'mount.start': 'Mount started', 'mount.stop': 'Mount stopped', 'mount.restart': 'Mount restarted', 'mount.reconcile': 'Mounts reconciled',
    'config.apply': 'Mount configuration updated', 'config.rollback': 'Mount configuration restored',
    'job.run': 'Job run', 'jobs.apply': 'Job configuration updated',
    'namespace.apply': 'Android visibility applied', 'namespace.rollback': 'Android visibility restored',
    'cache.clear': 'Mount cache cleared', 'cache.forget': 'Mount cache metadata forgotten',
  };
  if (known[value]) return known[value];
  const words = value.replaceAll('.', ' ').replaceAll('_', ' ').trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : '';
}

function renderHomeMountPreview(statuses) {
  const root = byId('homeMountPreview'); clear(root);
  const rows = Array.isArray(statuses) ? statuses.slice(0, 3) : [];
  if (!rows.length) {
    const empty = document.createElement('div'); empty.className = 'home-empty';
    empty.append(paragraph('No mounts configured yet.', 'home-empty-title'), paragraph('Add a mount when you are ready to connect a remote filesystem.', 'muted'));
    root.append(empty); return;
  }
  for (const status of rows) {
    const row = document.createElement('article'); row.className = 'home-preview-row';
    const copy = document.createElement('div'); copy.className = 'home-preview-copy';
    const title = document.createElement('h3'); title.textContent = status.name || 'Mount';
    const desired = status.desired ? `Desired ${status.desired}` : status.enabled === false ? 'Disabled' : 'Managed by Skybind';
    copy.append(title, paragraph(desired, 'muted'));
    const value = status.state || 'unknown'; row.append(copy, label(value, healthClass(value)));
    root.append(row);
  }
  if ((statuses || []).length > rows.length) root.append(paragraph(`+ ${(statuses || []).length - rows.length} more mount${(statuses || []).length - rows.length === 1 ? '' : 's'}`, 'home-more-note'));
}

function renderHomeActivityPreview(records) {
  const root = byId('homeActivityPreview'); clear(root);
  const rows = [];
  for (const record of records || []) {
    const model = operationSummary(record); const title = homeOperationTitle(model.operation);
    if (!title) continue;
    rows.push({ title, state:model.state, updatedUnixMS:model.updatedUnixMS, message:model.message });
    if (rows.length === 4) break;
  }
  if (!rows.length) {
    const empty = document.createElement('div'); empty.className = 'home-empty';
    empty.append(paragraph('No current-product activity yet.', 'home-empty-title'), paragraph('Lifecycle and job actions will appear here after Skybind records them.', 'muted'));
    root.append(empty); return;
  }
  for (const item of rows) {
    const row = document.createElement('article'); row.className = 'home-activity-row';
    const icon = document.createElement('span'); icon.className = `home-activity-icon ${item.state === 'FAILED' ? 'bad' : item.state === 'RUNNING' ? 'warn' : 'good'}`; icon.textContent = item.state === 'FAILED' ? '!' : item.state === 'RUNNING' ? '•' : '✓'; icon.setAttribute('aria-hidden','true');
    const copy = document.createElement('div'); copy.className = 'home-preview-copy'; const title = document.createElement('h3'); title.textContent = item.title;
    copy.append(title, paragraph(`${formatTime(item.updatedUnixMS)}${item.message ? ` · ${item.message}` : ''}`, 'muted'));
    row.append(icon, copy); root.append(row);
  }
}

function homeNetworkSummary(policies) {
  const observations = (policies || []).map((item) => item?.decision?.observation).filter(Boolean);
  if (!observations.length) return { value:'Not observed', detail:'No active mount policy observation', online:null };
  const online = observations.some((obs) => obs.online === true);
  const classes = [...new Set(observations.map((obs) => String(obs.network_class || '').trim()).filter(Boolean))];
  if (online) return { value:'Online', detail:classes.length ? classes.join(' · ') : 'Network available', online:true };
  const offlineAllowed = (policies || []).filter((item) => item?.network_mode === 'offline-allowed').length;
  return { value:'Offline', detail:offlineAllowed ? `${offlineAllowed} mount polic${offlineAllowed === 1 ? 'y allows' : 'ies allow'} cached/offline use` : 'No online network observed', online:false };
}

async function loadHome() {
  const caps = await ensureConnected();
  const [runtimeEnvelope, providerEnvelope, mountsEnvelope, platformEnvelope, operationsEnvelope, policiesEnvelope] = await Promise.all([
    query('runtime.status'), query('provider.status'), query('mount.status'), query('platform.status'), query('operation.list', { limit: 30 }), query('policy.status'),
  ]);
  const runtime = result(runtimeEnvelope), provider = result(providerEnvelope), mounts = result(mountsEnvelope), platform = result(platformEnvelope), operations = result(operationsEnvelope), policies = result(policiesEnvelope).policies || [];
  const statuses = mounts.mounts || []; const records = operations.operations || [];
  const running = statuses.filter((item) => String(item.state || '').toLowerCase() === 'running').length;
  const seriousStates = new Set(['degraded','auth_error','fuse_error','mount_stale','failed']);
  const unhealthyMounts = statuses.filter((item) => seriousStates.has(String(item.state || '').toLowerCase()));
  const blockedPolicies = policies.filter((item) => item?.decision?.allowed === false);
  const network = homeNetworkSummary(policies);
  const issues = [];
  if (runtime?.operational !== true) issues.push('Bundled runtime is not operational.');
  if (provider?.fuse_helper_ready !== true || provider?.fuse_device_ready !== true) issues.push('FUSE needs attention before mounts can operate normally.');
  if (unhealthyMounts.length) issues.push(`${unhealthyMounts.length} mount${unhealthyMounts.length === 1 ? '' : 's'} report a degraded or failed state.`);
  if (blockedPolicies.length) issues.push(`${blockedPolicies.length} mount polic${blockedPolicies.length === 1 ? 'y is' : 'ies are'} currently blocking lifecycle work.`);

  const healthy = issues.length === 0;
  text('homeHeadline', healthy ? (statuses.length ? 'Everything’s running.' : 'Skybind is ready.') : `${issues.length} thing${issues.length === 1 ? '' : 's'} need attention.`);
  text('homeSummary', healthy ? (statuses.length ? 'Runtime, FUSE and managed mounts are healthy.' : 'The bundled runtime and FUSE stack are ready. Add a mount when you want to start.') : 'Skybind found an actionable condition. Review the summary below before starting new work.');
  const pill = byId('homeHealthPill'); pill.textContent = healthy ? 'Healthy' : 'Needs attention'; pill.className = healthy ? 'state-pill good' : 'state-pill warn';
  const attention = byId('homeAttention'); clear(attention); attention.hidden = healthy;
  if (!healthy) { const list = document.createElement('ul'); list.className = 'home-attention-list'; for (const issue of issues) { const item=document.createElement('li'); item.textContent=issue; list.append(item); } attention.append(list); }

  text('homeRuntimeValue', runtime?.operational === true ? (provider?.rclone_version || 'Operational') : 'Needs attention');
  text('homeRuntimeDetail', `${runtime?.source || 'skybind-bundled-static'} · ${runtime?.mode || 'managed'}`);
  text('homeMountValue', statuses.length ? `${running} running` : 'None yet');
  text('homeMountDetail', `${statuses.length} configured`);
  const fuseReady = provider?.fuse_helper_ready === true && provider?.fuse_device_ready === true;
  text('homeFuseValue', fuseReady ? 'Ready' : 'Needs attention');
  text('homeFuseDetail', fuseReady ? 'Helper and /dev/fuse available' : `${provider?.fuse_helper_ready ? 'Helper ready' : 'Helper unavailable'} · ${provider?.fuse_device_ready ? '/dev/fuse ready' : '/dev/fuse unavailable'}`);
  text('homeNetworkValue', network.value); text('homeNetworkDetail', network.detail);

  renderHomeMountPreview(statuses); renderHomeActivityPreview(records);
  const manager = platform?.root_manager || platform?.manager || {};
  compatibility.title = `${manager?.name || manager?.kind || 'Root manager detected'} · ${caps.server?.version || caps.server?.name || 'backend connected'}`;
}

async function openHomeMountEditor() { await setView('mounts'); const trigger=byId('addMountButton'); trigger?.focus(); openEditor(null,trigger); }
async function openHomeJobEditor() { await setView('jobs'); const trigger=byId('addJobButton'); trigger?.focus(); openJob(null,trigger); }

function healthClass(value) {
  if (value === 'RUNNING' || value === 'stopped' || value === 'running') return 'state-pill good';
  if (value === 'STOPPED' || value === 'RETRYING' || value === 'REMOTE_OFFLINE') return 'state-pill warn';
  if (value === 'DEGRADED' || value === 'AUTH_ERROR' || value === 'FUSE_ERROR' || value === 'MOUNT_STALE') return 'state-pill bad';
  return 'state-pill';
}

function mountStateCopy(row) {
  const stateValue = row.health.state || row.status.state || 'unknown';
  const running = Boolean(row.health.process_alive || row.status.state === 'running');
  const desiredRunning = (row.health.desired || row.status.desired) === 'running';
  const terminalFailure = Boolean(row.health.failure_code && row.health.retryable === false);
  const retryableFailure = Boolean(row.health.failure_code && row.health.retryable === true);
  return { stateValue, running, desiredRunning, terminalFailure, retryableFailure };
}

function openMountActions(row, trigger) {
  const sheet = byId('mountActionBackdrop'); if (!sheet) return;
  const status = mountStateCopy(row); state.mountActionName = row.config.name; state.mountActionReturnFocus = trigger || document.activeElement;
  text('mountActionTitle', row.config.name); text('mountActionSubtitle', `${row.config.remote} → ${row.config.mountpoint}`);
  byId('mountActionStart').hidden = status.running; byId('mountActionStart').disabled = status.terminalFailure;
  byId('mountActionStart').querySelector('strong').textContent = status.retryableFailure ? 'Retry start' : status.terminalFailure ? 'Start blocked' : 'Start';
  byId('mountActionStop').hidden = !status.running && !status.desiredRunning;
  byId('mountActionRestart').hidden = !status.running; byId('mountActionRestart').disabled = status.terminalFailure;
  sheet.hidden = false; queueMicrotask(() => byId('mountActionEdit')?.focus());
}
function closeMountActions() { const focus = state.mountActionReturnFocus; byId('mountActionBackdrop').hidden = true; state.mountActionName = ''; state.mountActionReturnFocus = null; if (focus?.focus) queueMicrotask(() => focus.focus()); }
function selectedMountActionConfig() { return mountConfigByName(state.mountActionName); }
async function deleteMountFromActions() { const cfg = selectedMountActionConfig(); const trigger=state.mountActionReturnFocus; closeMountActions(); if (!cfg) return; openEditor(cfg,trigger); state.editorDelete = true; await previewEditor(true); if (state.preview) setEditorStep(3); }

function renderMounts(snapshot, statuses, health) {
  const root = byId('mountCards'); clear(root);
  const rows = mountRows(snapshot, statuses, health);
  if (!rows.length) { root.append(paragraph('No mounts are configured yet. Add a mount when you are ready.', 'notice empty-state')); return; }
  for (const row of rows) {
    const status = mountStateCopy(row);
    const card = document.createElement('article'); card.className = 'mount-card modern-mount-card'; card.dataset.mountName = row.config.name;
    const head = document.createElement('div'); head.className = 'mount-head';
    const titles = document.createElement('div'); titles.className = 'mount-identity';
    const title = document.createElement('h3'); title.textContent = row.config.name;
    const remote = paragraph(row.config.remote || 'No remote configured', 'mount-remote code'); titles.append(title, remote);const security=encryptionBadgeForEndpoint(row.config.remote);if(security)titles.append(security);
    head.append(titles, label(status.stateValue, healthClass(status.stateValue))); card.append(head);

    const destination = document.createElement('div'); destination.className = 'mount-destination';
    const arrow = document.createElement('span'); arrow.setAttribute('aria-hidden','true'); arrow.textContent = '↳';
    const path = document.createElement('code'); path.textContent = row.config.mountpoint || '—'; destination.append(arrow, path); card.append(destination);

    const meta = document.createElement('div'); meta.className = 'mount-meta mount-summary-grid';
    const values = [
      ['Desired', row.health.desired || row.status.desired || '—'],
      ['VFS', row.config.vfs_profile || 'custom'],
      ['Network', row.config.network_mode || 'offline-allowed'],
      ['PID', row.status.pid || row.health.pid || '—'],
    ];
    for (const [name, value] of values) { const cell = document.createElement('div'); const strong = document.createElement('strong'); strong.textContent = name; const span=document.createElement('span'); span.textContent=String(value); cell.append(strong, span); meta.append(cell); }
    card.append(meta);
    if (row.health.failure_code || (row.health.reason && row.health.reason !== '—')) {
      const issue = document.createElement('div'); issue.className = `mount-health-note ${row.health.retryable === false ? 'bad' : 'warn'}`;
      issue.textContent = row.health.reason || row.health.failure_code; card.append(issue);
    }

    const actions = document.createElement('div'); actions.className = 'mount-actions compact-actions';
    const edit = button(status.terminalFailure ? 'Fix mount' : 'Edit mount', () => openEditor(row.config), status.terminalFailure ? 'primary' : '');
    const menu = button('•••', () => openMountActions(row, menu), 'icon-button mount-context-button'); menu.setAttribute('aria-label', `More actions for ${row.config.name}`); menu.setAttribute('aria-haspopup','dialog');
    actions.append(edit, menu); card.append(actions); root.append(card);
  }
}

async function loadMounts() {
  const [snapshotEnvelope, statusesEnvelope, healthEnvelope, remotesEnvelope] = await Promise.all([
    query('config.snapshot'), query('mount.status'), query('mount.health'), query('provider.remotes'),
  ]);
  const snapshot = result(snapshotEnvelope); state.snapshot = snapshot;state.remoteDetails=result(remotesEnvelope).details||[];
  renderMounts(snapshot, result(statusesEnvelope).mounts || [], result(healthEnvelope).health || []);
}

async function lifecycleAction(action, name) {
  const notice = byId('mountsNotice'); hideNotice(notice);
  try {
    const startProof = action === 'start' ? result(await preview('mount.start.preview', { name })).preview_proof : '';
    const handle = startOperation(`mount.${action}`, 'run', action === 'start' ? { name, proof: startProof } : { name });
    showNotice(notice, `${name}: ${action} started. Track progress in Activity.`);
    const envelope = await handle.completion; result(envelope);
    showNotice(notice, `${name}: ${action} completed.`, 'ok');
    await loadMounts();
  } catch (error) { showLifecycleFailure(name, action, error); }
}

async function reconcileAll() {
  const notice = byId('mountsNotice');
  try {
    const handle = startOperation('mount.reconcile', 'reconcile', {});
    showNotice(notice, 'Reconcile started. Track progress in Activity.');
    result(await handle.completion); showNotice(notice, 'Reconcile completed.', 'ok'); await loadMounts();
  } catch (error) { showNotice(notice, String(error?.message || error), 'error'); }
}

function renderActivityGroup(root, records) {
  if (!records.length) return;
  const section = document.createElement('section'); section.className = 'activity-group';
  const heading = document.createElement('div'); heading.className = 'activity-group-heading';
  const h = document.createElement('h3'); h.textContent = 'Recent activity';
  heading.append(h);
  section.append(heading);
  for (const record of records) {
    const model = activityPresentation(record); const card = document.createElement('article'); card.className = 'activity-card';
    const head = document.createElement('div'); head.className = 'activity-card-head';
    const icon = document.createElement('span'); icon.className = `activity-state-icon ${model.state === 'FAILED' ? 'bad' : model.state === 'RUNNING' ? 'warn' : 'good'}`; icon.textContent = model.state === 'FAILED' ? '!' : model.state === 'RUNNING' ? '•' : '✓'; icon.setAttribute('aria-hidden','true');
    const titles = document.createElement('div'); titles.className = 'activity-card-copy'; const title = document.createElement('strong'); title.textContent = model.title;
    titles.append(title, paragraph(`${formatTime(model.updatedUnixMS)}${model.subtitle ? ` · ${model.subtitle}` : ''}`,'muted'));
    head.append(icon,titles,label(model.state, model.state === 'SUCCEEDED' ? 'state-pill good' : model.state === 'RUNNING' ? 'state-pill warn' : model.state === 'FAILED' ? 'state-pill bad' : 'state-pill'));
    card.append(head);
    const details = document.createElement('details'); details.className = 'activity-details'; const summary = document.createElement('summary'); summary.textContent = 'Technical details'; details.append(summary);
    const meta = document.createElement('div'); meta.className = 'activity-detail-grid';
    metric(meta,'Operation',model.operation); metric(meta,'Request',model.requestId || '—'); metric(meta,'State',model.state);
    details.append(meta);
    if (model.events.length) { const list = document.createElement('ol'); list.className='operation-events'; for (const event of model.events.slice(-6)) { const item=document.createElement('li'); item.textContent=`${event.event || 'event'}${event.message ? ` — ${event.message}` : ''}`; list.append(item); } details.append(list); }
    if (model.state === 'RUNNING' && model.cancellable) details.append(button('Cancel safely', () => void cancelOperation(model.requestId), 'danger'));
    card.append(details); section.append(card);
  }
  root.append(section);
}

function renderOperations(records) {
  const root=byId('operationCards');clear(root);
  if (!records.length) root.append(paragraph('No activity yet. Mount, job and configuration actions will appear here.','notice empty-state'));
  else renderActivityGroup(root,records);
}

async function loadOperations() {
  const records = result(await query('operation.list', { limit: 50 })).operations || [];
  renderOperations(records);
}

async function cancelOperation(requestId) {
  try { result(await cancel('operation.cancel', { request_id: requestId })); await loadOperations(); }
  catch (error) { compatibility.className = 'notice error'; compatibility.textContent = `Cancel failed: ${String(error?.message || error)}`; }
}

const fields = ['name','remote','mountpoint','vfs_profile','vfs_cache_mode','vfs_cache_max_size','vfs_cache_max_age','dir_cache_time','poll_interval','log_level','network_mode','min_battery','min_free_cache_space','boot_settle','network_settle','cache_high_water','cache_low_water'];
const checks = ['enabled','allow_other','read_only','probe_remote','charging_only'];
const issueCategoryLabels = { input:'Input', remote:'Remote', destination:'Destination', vfs:'Cache & performance', policy:'Behaviour', provider:'Provider', conflict:'Conflict', runtime:'Runtime', security:'Security', advanced:'Advanced', internal:'Internal' };

function clearPreviewTimer() { if (state.previewTimer) clearInterval(state.previewTimer); state.previewTimer = null; }
function serializeEditor() { try { return JSON.stringify(formValue()); } catch (_) { return ''; } }
function markEditorDirty() { state.editorDirty = serializeEditor() !== state.editorInitial; }
function issueFieldNode(field) { return document.querySelector(`#mountForm label[data-field="${field}"]`); }
function clearFieldIssues() {
  for (const node of document.querySelectorAll('#mountForm label.field-invalid')) node.classList.remove('field-invalid');
  for (const node of document.querySelectorAll('#mountForm .field-feedback')) node.remove();
}
function renderEditorIssues(issues = []) {
  state.editorIssues = Array.isArray(issues) ? issues : [];
  clearFieldIssues();
  const root = byId('editorIssueSummary'); clear(root);
  const visible = state.editorIssues.filter((item) => item?.message);
  const currentMount = byId('field-name')?.value?.trim() || state.editorOriginal || '';
  for (const item of visible) {
    if (!item.field || (item.mount && currentMount && item.mount !== currentMount)) continue;
    const labelNode = issueFieldNode(item.field); if (!labelNode) continue;
    labelNode.classList.toggle('field-invalid', item.severity !== 'warning');
    const note = document.createElement('span'); note.className = 'field-feedback';
    note.textContent = `${item.message}${item.suggestion ? ` · ${item.suggestion}` : ''}`; labelNode.append(note);
  }
  if (!visible.length) { root.hidden = true; renderDestinationStatus([]); return; }
  root.hidden = false;
  const errors = visible.filter((item) => item.severity !== 'warning').length;
  const warnings = visible.length - errors;
  const title = document.createElement('h3'); title.textContent = `${errors ? `${errors} thing${errors === 1 ? '' : 's'} need attention` : 'Configuration looks usable'}${warnings ? ` · ${warnings} warning${warnings === 1 ? '' : 's'}` : ''}`; root.append(title);
  const grouped = new Map();
  for (const item of visible) { const key = item.category || 'input'; if (!grouped.has(key)) grouped.set(key, []); grouped.get(key).push(item); }
  for (const [category, items] of grouped) {
    const block = document.createElement('div'); block.className = 'issue-category';
    const heading = document.createElement('strong'); heading.textContent = issueCategoryLabels[category] || category; block.append(heading);
    const list = document.createElement('ul'); list.className = 'issue-list';
    for (const item of items) {
      const currentMount = byId('field-name')?.value?.trim() || state.editorOriginal || '';
      const focusable = item.field && (!item.mount || !currentMount || item.mount === currentMount);
      const li = document.createElement('li'); const message = document.createElement(focusable ? 'button' : 'span');
      if (focusable) { message.type = 'button'; message.className = 'issue-action'; message.addEventListener('click', () => focusIssueField(item.field)); }
      message.textContent = `${item.mount && item.mount !== currentMount ? `“${item.mount}”: ` : ''}${item.message}`; li.append(message);
      if (item.suggestion) li.append(document.createTextNode(` — ${item.suggestion}`));
      list.append(li);
    }
    block.append(list); root.append(block);
  }
  renderDestinationStatus(visible);
}
function focusIssueField(field) { const node = byId(`field-${field}`); if (node) { const details = node.closest('details'); if (details) details.open = true; node.focus(); node.scrollIntoView({ block:'center', behavior:document.body.classList.contains('reduce-motion')?'auto':'smooth' }); } }
function renderDestinationStatus(issues = state.editorIssues) {
  const root = byId('destinationStatus'); clear(root);
  const currentMount = byId('field-name')?.value?.trim() || state.editorOriginal || '';
  const own = issues.filter((item) => !item.mount || !currentMount || item.mount === currentMount);
  const cfg = formValue();
  const nameIssue = own.find((item) => item.field === 'name' && item.severity !== 'warning');
  const pathIssue = own.find((item) => item.field === 'mountpoint' && item.severity !== 'warning');
  if (cfg.name) root.append(label(nameIssue ? `✕ ${nameIssue.message}` : '✓ Name ready', nameIssue ? 'validation-chip bad' : 'validation-chip good'));
  const absolute = cfg.mountpoint.startsWith('/');
  if (cfg.mountpoint) root.append(label(absolute ? '✓ Absolute path' : '✕ Absolute path required', absolute ? 'validation-chip good' : 'validation-chip bad'));
  if (state.editorBackendValidated && absolute) {
    const protectedIssue = own.find((item) => ['mountpoint_protected','mountpoint_root_forbidden'].includes(item.code));
    const overlapIssue = own.find((item) => item.code === 'mountpoint_overlap');
    root.append(label(protectedIssue ? '✕ Protected location' : '✓ Outside Skybind/provider state', protectedIssue ? 'validation-chip bad' : 'validation-chip good'));
    root.append(label(overlapIssue ? `✕ Overlaps ${overlapIssue.related_mount || 'another mount'}` : '✓ No mount overlap', overlapIssue ? 'validation-chip bad' : 'validation-chip good'));
  } else if (absolute && !pathIssue) {
    root.append(label('… Checking backend location rules','validation-chip'));
  }
}
function invalidatePreview({ validate = true } = {}) {
  state.preview = null; state.previewCandidates = null; state.editorBackendValidated = false; clearPreviewTimer(); byId('previewPanel').hidden = true; byId('applyMountButton').disabled = true; hideNotice(byId('editorError')); byId('operationProgress').hidden = true;
  byId('applyMountButton').textContent = state.editorDelete ? 'Delete mount' : (state.editorExisting ? 'Apply changes' : 'Create mount');
  markEditorDirty();
  if (validate && state.editorInteracted && state.editorStep > 0) scheduleEditorValidation();
}

function formValue() {
  const value = {};
  for (const key of fields) value[key] = byId(`field-${key}`).value;
  for (const key of checks) value[key] = byId(`field-${key}`).checked;
  value.require_network = value.network_mode !== 'offline-allowed';
  return candidate(value);
}

function fillForm(config, existing) {
  const clean = candidate(config);
  for (const key of fields) byId(`field-${key}`).value = clean[key] ?? '';
  for (const key of checks) byId(`field-${key}`).checked = Boolean(clean[key]);
  byId('field-name').readOnly = existing;
  byId('argsFileHint').hidden = !config?.has_args_file;
  const parsed = parseRemoteEndpoint(clean.remote); state.editorRemotePath = parsed.path; byId('mountRemotePath').value = parsed.path ? `/${parsed.path}` : '/';
  byId('mountRemoteEndpoint').textContent = clean.remote || '—';
}

function editorHasBlockingIssues(issues = state.editorIssues) { return issues.some((item) => item?.severity !== 'warning'); }
function localEditorIssues() { return localMountIssues(formValue(), state.snapshot?.mounts || [], state.editorOriginal); }
async function validateEditorNow() {
  state.editorBackendValidated = false;
  const local = localEditorIssues(); renderEditorIssues(local);
  if (editorHasBlockingIssues(local)) return { valid:false, issues:local };
  const seq = ++state.editorValidationSeq;
  try {
    const candidates = candidateRegistry(false); const value = result(await query('config.validate', { mounts:candidates }));
    if (seq !== state.editorValidationSeq || byId('editorBackdrop').hidden) return value;
    state.editorBackendValidated = true; renderEditorIssues(value.issues || []); return value;
  } catch (error) {
    if (seq !== state.editorValidationSeq || byId('editorBackdrop').hidden) return { valid:false, issues:[] };
    const issues = error?.issues?.length ? error.issues : [{ code:error?.code||'validation_failed', category:error?.category||'internal', severity:'error', message:String(error?.message||error), detail:error?.detail||'' }];
    renderEditorIssues(issues); return { valid:false, issues };
  }
}
function scheduleEditorValidation() {
  if (state.editorValidationTimer) clearTimeout(state.editorValidationTimer);
  state.editorValidationTimer = setTimeout(() => { state.editorValidationTimer = null; void validateEditorNow(); }, 350);
}

function remoteDetail(name) { return (state.remoteDetails || []).find((item) => item?.name === name) || null; }
function endpointEncryption(endpoint) {
  const parsed = parseRemoteEndpoint(String(endpoint || '').trim());
  if (!parsed.remote) return { kind:'local', label:'Local path' };
  const detail = remoteDetail(parsed.remote);
  if (!detail) return { kind:'unknown', label:'Encryption unknown', remote:parsed.remote };
  return detail.encryption === 'rclone-crypt'
    ? { kind:'crypt', label:'Protected by rclone crypt', remote:parsed.remote, detail }
    : { kind:'plain', label:'Not protected by rclone crypt', remote:parsed.remote, detail };
}
function encryptionBadgeForEndpoint(endpoint) {
  const enc=endpointEncryption(endpoint);
  if(enc.kind==='local')return null;
  if(enc.kind==='crypt')return label('🔒 rclone crypt','security-pill good');
  if(enc.kind==='plain')return label('△ unencrypted remote','security-pill warn');
  return label('? encryption unknown','security-pill');
}
function renderCryptRecoveryStatus(status){
  state.cryptRecovery=status||null;
  const root=byId('cryptRecoveryDetails');if(!root)return;clear(root);
  if(!status){root.append(paragraph('Recovery inventory is unavailable.','muted'));return;}
  const summary=document.createElement('div');summary.className='recovery-summary';
  const values=[['Password generation',status.password_configured?status.password_revision:'Not configured'],['Skybind-managed crypt',status.skybind_managed_remotes||0],['Current generation',status.current_password_remotes||0],['Older generation',status.older_password_remotes||0],['External crypt',status.unmanaged_crypt_remotes||0]];
  for(const [name,value] of values){const cell=document.createElement('div');cell.append(paragraph(name,'muted'),paragraph(String(value),'recovery-value'));summary.append(cell);}root.append(summary);
  const guidance=document.createElement('div');guidance.className='notice compact warn';guidance.append(paragraph('Recovery depends on your rclone configuration and the password generation that created each Skybind-managed crypt remote. Skybind never reveals or regenerates crypt secrets.'),paragraph(status.guidance||'Back up your rclone configuration before changing the Skybind encryption password.','muted'));root.append(guidance);
  if((status.older_password_remotes||0)>0){root.append(paragraph(`${status.older_password_remotes} Skybind-managed encrypted remote(s) were created with an older Skybind password generation. Replacing the Skybind password does not re-key them.`,'notice compact'));}
}
function renderMountEncryptionNotice() {
  const node=byId('mountEncryptionNotice'); if(!node)return; clear(node);
  const endpoint=byId('field-remote')?.value||''; const enc=endpointEncryption(endpoint);
  if(enc.kind==='local'||!endpoint){node.hidden=true;return;}
  node.hidden=false;
  if(enc.kind==='crypt'){node.className='notice compact ok';node.append(paragraph(`🔒 ${enc.remote}: uses rclone crypt. Remote data is encrypted at rest and decrypted through the crypt remote.`));return;}
  node.className='notice compact warn';
  node.append(paragraph(enc.kind==='plain'?`△ ${enc.remote}: is not protected by rclone crypt. Data on this remote may be stored without client-side encryption.`:`? Skybind could not determine encryption for ${enc.remote}:.`));
  if(enc.kind==='plain'){const action=button('Add encryption',()=>void openCryptCreator(endpoint,action,(created)=>selectCreatedCryptForMount(created)));node.append(action);}
}
function renderJobEncryptionNotice(){
  const sourceNode=byId('jobSourceEncryptionNotice');const source=byId('job-source')?.value||'';const sourceEnc=endpointEncryption(source);
  if(sourceNode){clear(sourceNode);if(!source||sourceEnc.kind==='local'){sourceNode.hidden=true;}else{sourceNode.hidden=false;if(sourceEnc.kind==='crypt'){sourceNode.className='notice compact ok';sourceNode.textContent=`🔒 Source ${sourceEnc.remote}: is protected by rclone crypt.`;}else{sourceNode.className='notice compact warn';sourceNode.textContent=sourceEnc.kind==='plain'?`△ Source ${sourceEnc.remote}: is unencrypted at rest. Creating a crypt wrapper later will not encrypt files already stored there.`:`? Encryption status for source ${sourceEnc.remote}: is unknown.`;}}}
  const node=byId('jobEncryptionNotice');if(!node)return;clear(node);const endpoint=byId('job-destination')?.value||'';const enc=endpointEncryption(endpoint);
  if(!endpoint||enc.kind==='local'){node.hidden=true;return;}node.hidden=false;
  if(enc.kind==='crypt'){node.className='notice compact ok';node.textContent=`🔒 Destination ${enc.remote}: is protected by rclone crypt.`;return;}
  node.className='notice compact warn';node.append(paragraph(enc.kind==='plain'?`△ Destination ${enc.remote}: is not protected by rclone crypt. New job data can be stored remotely without client-side encryption.`:`? Encryption status for destination ${enc.remote}: is unknown.`));
  if(enc.kind==='plain'){const action=button('Create encrypted destination',()=>void openCryptCreator(endpoint,action,(created)=>{byId('job-destination').value=`${created.name}:`;invalidateJobPreview();renderJobEncryptionNotice();}));node.append(action);}
}
function renderCryptPasswordStatus(status){
  state.cryptPasswordStatus=status||{configured:false,password2:'unset',authority:'skybind-user-defined'};
  const configured=Boolean(state.cryptPasswordStatus.configured);
  const pill=byId('cryptPasswordStatusPill');if(pill){pill.textContent=configured?'Configured':'Not configured';pill.className=`state-pill ${configured?'good':'warn'}`;}
  text('cryptPasswordStatusText',configured?`Configured as generation ${state.cryptPasswordStatus.revision||1} for future Skybind-created rclone crypt remotes. password2 is unset.`:'Not configured. Skybind refuses automatic crypt creation until you set it.');
  const gate=byId('cryptPasswordGate');if(gate)gate.hidden=configured;
  const fields=byId('cryptOptionsFieldset');if(fields)fields.disabled=!configured;
  const previewButton=byId('previewCryptButton');if(previewButton)previewButton.disabled=!configured;
  if(!configured)byId('createCryptButton') && (byId('createCryptButton').disabled=true);
}
async function refreshCryptPasswordStatus(){const value=result(await query('provider.crypt.password.status'));renderCryptPasswordStatus(value);return value;}
async function setSkybindCryptPassword(inputId,buttonId,noticeId){
  const input=byId(inputId),control=byId(buttonId),notice=byId(noticeId);const password=input?.value||'';
  if(!password){showNotice(notice,'Enter the Skybind encryption password first.','warn');input?.focus();return;}
  if(state.cryptPasswordStatus?.configured&&(state.cryptRecovery?.skybind_managed_remotes||0)>0&&!globalThis.confirm('Replace the Skybind encryption password? Existing encrypted remotes are NOT re-keyed. Back up your rclone configuration and retain the password generation needed to reconstruct older remotes.')){input.value='';return;}
  setButtonBusy(control,true,'Saving…');try{const status=result(await run('provider.crypt.password.set',{password}));if(input)input.value='';renderCryptPasswordStatus(status);hideNotice(notice);showNotice(notice,`Skybind encryption password configured as generation ${status.revision||1}. It applies only to future Skybind-created crypt remotes; password2 remains unset.`,'ok');announceStatus('Skybind encryption password configured.');try{const recovery=result(await query('provider.crypt.recovery.status'));renderCryptRecoveryStatus(recovery);}catch(_){}if(byId('cryptBackdrop')&&!byId('cryptBackdrop').hidden)queueMicrotask(()=>byId('crypt-name')?.focus());}catch(error){if(input)input.value='';showNotice(notice,backendErrorText(error),'error');announceStatus('Skybind encryption password update failed.');}finally{if(input)input.value='';setButtonBusy(control,false);}
}

function endpointFor(remote, path='') { return remote ? `${remote}:${String(path||'').replace(/^\/+|\/+$/g,'')}` : ''; }
function updateRemoteEndpoint({ applyDefaults = true } = {}) {
  const selected = byId('mountRemoteSelect').value;
  if (!state.editorManualRemote && selected) byId('field-remote').value = endpointFor(selected, state.editorRemotePath);
  const endpoint = byId('field-remote').value.trim(); byId('mountRemoteEndpoint').textContent = endpoint || '—';
  const parsed = parseRemoteEndpoint(endpoint);
  const configured = Boolean(parsed.remote && state.editorRemotes.includes(parsed.remote));
  byId('remoteStatusPill').textContent = state.editorRemoteReachable === true ? 'Reachable' : configured ? 'Configured' : parsed.remote ? 'Manual' : 'Not selected';
  byId('remoteStatusPill').className = state.editorRemoteReachable === false ? 'state-pill bad' : (configured || state.editorRemoteReachable === true) ? 'state-pill good' : parsed.remote ? 'state-pill warn' : 'state-pill';
  if (applyDefaults && !state.editorExisting && endpoint) {
    const defaults = suggestMountDefaults(endpoint);
    if (!state.editorNameTouched || !byId('field-name').value) byId('field-name').value = defaults.name;
    if (!state.editorMountpointTouched || !byId('field-mountpoint').value) byId('field-mountpoint').value = defaults.mountpoint;
  }
  renderProviderReadiness();
  renderMountEncryptionNotice();
  invalidatePreview();
}
function renderProviderReadiness() {
  const root = byId('providerReadiness'); if (!root) return; clear(root);
  const status = state.editorProviderStatus;
  if (!status) { root.append(label('… Checking provider','validation-chip')); return; }
  root.append(label(status.binary_ready ? '✓ rclone available' : '✕ rclone unavailable', status.binary_ready ? 'validation-chip good' : 'validation-chip bad'));
  root.append(label(status.fuse_helper_ready ? '✓ FUSE helper ready' : '✕ FUSE helper unavailable', status.fuse_helper_ready ? 'validation-chip good' : 'validation-chip bad'));
  root.append(label(status.config_ready ? '✓ rclone config ready' : '✕ rclone config missing', status.config_ready ? 'validation-chip good' : 'validation-chip bad'));
  const parsed = parseRemoteEndpoint(byId('field-remote')?.value || '');
  if (parsed.remote) {
    const configured = state.editorRemotes.includes(parsed.remote);
    root.append(label(configured ? `✓ ${parsed.remote}: configured` : `! ${parsed.remote}: manual/unlisted`, configured ? 'validation-chip good' : 'validation-chip'));
  }
  if (state.editorRemoteReachable === true) root.append(label('✓ Selected path reachable','validation-chip good'));
  if (state.editorRemoteReachable === false) root.append(label('✕ Selected path not reachable','validation-chip bad'));
}
function renderMountRemoteSelect() {
  const select = byId('mountRemoteSelect'); const current = parseRemoteEndpoint(byId('field-remote').value).remote; clear(select);
  const prompt = document.createElement('option'); prompt.value=''; prompt.textContent='Select a remote…'; select.append(prompt);
  for (const name of state.editorRemotes) { const option=document.createElement('option'); option.value=name; const detail=remoteDetail(name); option.textContent=`${detail?.encryption==='rclone-crypt'?'🔒':'△'} ${name}:`; select.append(option); }
  if (current && state.editorRemotes.includes(current)) select.value=current;
}
async function loadMountEditorData(existing, session = state.editorSession) {
  const settled = await Promise.allSettled([query('provider.remotes'), query('vfs.profiles'), query('provider.status')]);
  if (session !== state.editorSession || byId('editorBackdrop').hidden) return;
  const helperErrors=[];
  try { const remotesData=settled[0].status === 'fulfilled' ? result(settled[0].value) : (()=>{throw settled[0].reason;})(); state.editorRemotes=remotesData.remotes||[];state.remoteDetails=remotesData.details||[]; } catch(error){state.editorRemotes=[];state.remoteDetails=[];helperErrors.push(`remote list: ${String(error?.message||error)}`);}
  try { const profileData=settled[1].status === 'fulfilled' ? result(settled[1].value) : (()=>{throw settled[1].reason;})(); state.editorProfiles=profileData.profiles||[];state.editorRecommendation=profileData.recommendation||null; } catch(error){state.editorProfiles=[];state.editorRecommendation=null;helperErrors.push(`profiles: ${String(error?.message||error)}`);}
  try { state.editorProviderStatus=settled[2].status === 'fulfilled' ? result(settled[2].value) : (()=>{throw settled[2].reason;})(); } catch(error){state.editorProviderStatus=null;helperErrors.push(`provider status: ${String(error?.message||error)}`);}
  renderMountRemoteSelect(); renderProfileCards(); renderProviderReadiness();
  const currentRemote = parseRemoteEndpoint(byId('field-remote').value).remote;
  if (existing && currentRemote && !state.editorRemotes.includes(currentRemote)) setManualRemote(true);
  const current = byId('field-vfs_profile').value;
  if (!existing && !state.editorProfileTouched && (current === 'custom' || !current) && state.editorRecommendation?.profile) { byId('field-vfs_profile').value = state.editorRecommendation.profile; }
  renderProfileCards(); updateProfilePresentation();
  if(helperErrors.length)showNotice(byId('editorError'),`Some setup helpers are unavailable (${helperErrors.join(' · ')}). Available fields remain editable and backend review still decides whether the mount can be applied.`,'error');
}
function renderProfileCards() {
  const root = byId('profileCards'); clear(root); const selected = byId('field-vfs_profile').value || 'custom';
  const profiles = state.editorProfiles.length ? state.editorProfiles : [
    {name:'balanced',description:'General-purpose full VFS caching.'},{name:'streaming',description:'Larger cache for media.'},{name:'offline',description:'Persistent cache for intermittent connectivity.'},{name:'minimal',description:'Small cache footprint.'},{name:'custom',description:'Use explicit VFS values.'},
  ];
  for (const item of profiles) {
    const model = profilePresentation(item.name, profiles, state.editorRecommendation); const card=document.createElement('label'); card.className=`profile-card${selected===item.name?' selected':''}${model.recommended?' recommended':''}`;
    const radio=document.createElement('input'); radio.type='radio'; radio.name='profile-card'; radio.value=item.name; radio.checked=selected===item.name;
    radio.addEventListener('change',()=>{ if(!radio.checked)return; state.editorProfileTouched=true; byId('field-vfs_profile').value=item.name; renderProfileCards(); updateProfilePresentation(); invalidatePreview(); });
    const strong=document.createElement('strong'); strong.textContent=item.name; const desc=paragraph(model.description,''); card.append(radio,strong,desc);
    const opts=model.options||{}; const meta=document.createElement('span'); meta.className='profile-meta'; meta.textContent=[opts.vfs_cache_mode,opts.vfs_cache_max_size].filter(Boolean).join(' · ') || 'Explicit settings'; card.append(meta); root.append(card);
  }
  const rec=state.editorRecommendation; const recNode=byId('profileRecommendation');
  if (rec?.profile) { const resources=[rec.memory_bytes?`${bytes(rec.memory_bytes)} RAM`:'',rec.cache_free_bytes?`${bytes(rec.cache_free_bytes)} cache free`:''].filter(Boolean).join(' · '); recNode.hidden=false; recNode.textContent=`Recommended for this device: ${rec.profile} · ${rec.reason}. ${resources ? `${resources} · ` : ''}cache target ${rec.cache_max_size || 'automatic'}.`; } else recNode.hidden=true;
}
function updateProfilePresentation() {
  const profile=byId('field-vfs_profile').value||'custom'; const model=profilePresentation(profile,state.editorProfiles,state.editorRecommendation); const root=byId('profileEffective'); clear(root); const custom=profile==='custom';
  byId('customVfsDetails').open=custom; byId('customVfsDetails').classList.toggle('profile-managed',!custom);
  for (const node of document.querySelectorAll('#customVfsDetails input, #customVfsDetails select')) node.disabled=!custom;
  if (custom) { root.append(label('Custom values','state-pill')); return; }
  const o=model.options||{};
  const profileFields={vfs_cache_mode:o.vfs_cache_mode||'full',vfs_cache_max_size:o.vfs_cache_max_size||'',vfs_cache_max_age:o.vfs_cache_max_age||'',dir_cache_time:o.dir_cache_time||'',poll_interval:o.poll_interval||''};
  for(const [field,value] of Object.entries(profileFields))byId(`field-${field}`).value=value;
  root.append(label('Profile-managed values','state-pill good'));
  for (const value of [o.vfs_cache_mode && `Cache ${o.vfs_cache_mode}`, o.vfs_cache_max_size && `Max ${o.vfs_cache_max_size}`, o.vfs_cache_max_age && `Age ${o.vfs_cache_max_age}`, o.dir_cache_time && `Dir cache ${o.dir_cache_time}`].filter(Boolean)) root.append(label(value,'state-pill'));
}
function setManualRemote(enabled) {
  state.editorManualRemote=Boolean(enabled); byId('manualRemoteWrap').hidden=!state.editorManualRemote; byId('manualRemoteButton').textContent=state.editorManualRemote?'Use remote browser':'Enter manually';
  if (state.editorManualRemote) byId('field-remote').focus(); else updateRemoteEndpoint({applyDefaults:false});
}
async function browseMountRemote(remote=byId('mountRemoteSelect').value,path=state.editorRemotePath) {
  if (!remote) { showNotice(byId('remoteTestResult'),'Choose a remote first.','error'); return; }
  const panel=byId('mountRemoteBrowser'), root=byId('mountRemoteEntries'); panel.hidden=false; clear(root); byId('mountRemoteBreadcrumb').textContent=`${remote}:${path||''}`; byId('mountRemoteParentButton').disabled=!path;
  try {
    const value=result(await query('provider.browse',{remote,path,limit:180})); state.editorRemotePath=value.path||''; byId('mountRemotePath').value=state.editorRemotePath?`/${state.editorRemotePath}`:'/'; byId('mountRemoteBreadcrumb').textContent=`${remote}:${state.editorRemotePath}`;
    const dirs=(value.entries||[]).filter((entry)=>entry.is_dir); if(!dirs.length) root.append(paragraph('No subfolders here. You can use the current folder.','muted'));
    for(const entry of dirs){const row=document.createElement('div');row.className='remote-folder remote-object-row';const open=button('',()=>void browseMountRemote(remote,entry.path),'remote-object-main');const icon=document.createElement('span');icon.className='remote-object-icon';icon.textContent='📁';const copy=document.createElement('span');copy.className='remote-object-copy';const name=document.createElement('strong');name.className='folder-name';name.textContent=entry.name;const meta=document.createElement('small');meta.textContent='Folder';copy.append(name,meta);open.append(icon,copy);const chev=document.createElement('span');chev.className='remote-object-chevron';chev.setAttribute('aria-hidden','true');chev.textContent='›';open.append(chev);row.append(open);root.append(row);}
    if(value.truncated) root.append(paragraph('Folder list is truncated. Open a narrower folder to continue.','muted'));
  } catch(error) { const issues=error?.issues?.length?error.issues:[{category:'remote',field:'remote',severity:'error',message:String(error?.message||error)}]; renderEditorIssues([...localEditorIssues().filter((x)=>x.field!=='remote'),...issues]); root.append(paragraph(`Browse failed: ${String(error?.message||error)}`,'notice error')); }
}
function chooseCurrentRemoteFolder() { const remote=byId('mountRemoteSelect').value; if(!remote)return; state.editorManualRemote=false; byId('manualRemoteWrap').hidden=true; byId('field-remote').value=endpointFor(remote,state.editorRemotePath); byId('mountRemoteBrowser').hidden=true; updateRemoteEndpoint(); }
async function testMountRemote() {
  const node=byId('remoteTestResult'); const parsed=parseRemoteEndpoint(byId('field-remote').value); hideNotice(node);
  if(!parsed.remote){showNotice(node,'Choose a remote first.','error');return;}
  showNotice(node,`Testing ${parsed.remote}:…`);
  try { result(await query('provider.browse',{remote:parsed.remote,path:parsed.path,limit:1})); state.editorRemoteReachable=true; renderProviderReadiness(); updateRemoteEndpoint({applyDefaults:false}); showNotice(node,`Connection to ${parsed.remote}: is working${parsed.path?` and ${parsed.path} is reachable`:''}.`,'ok'); }
  catch(error){ state.editorRemoteReachable=false; renderProviderReadiness(); updateRemoteEndpoint({applyDefaults:false}); showNotice(node,`${String(error?.message||error)}${error?.detail?` · ${error.detail}`:''}`,'error'); if(error?.issues?.length)renderEditorIssues([...localEditorIssues().filter((x)=>x.field!=='remote'),...error.issues]); }
}

function safeMountLabel() {
  const endpoint = parseRemoteEndpoint(byId('field-remote').value); const raw = endpoint.path.split('/').filter(Boolean).at(-1) || byId('field-name').value || endpoint.remote || 'Mount';
  return String(raw).replace(/[\/:*?"<>|]+/g, ' ').replace(/\s+/g, ' ').trim() || 'Mount';
}
function applyMountpointSuggestion(template) {
  const name = byId('field-name').value.trim() || suggestMountDefaults(byId('field-remote').value).name || 'mount';
  byId('field-mountpoint').value = String(template).replace('{name}', name).replace('{label}', safeMountLabel()); state.editorMountpointTouched = true; invalidatePreview();
}
function updateNetworkPolicyHelp() {
  const mode = byId('field-network_mode').value; const copy = {
    any:'Start may use Wi-Fi or metered mobile data.', wifi:'Start only while Wi-Fi is available.', unmetered:'Start only on an unmetered network.', 'offline-allowed':'Cached content may remain usable while disconnected; remote access resumes when connectivity returns.',
  };
  byId('networkPolicyHelp').textContent = copy[mode] || 'Skybind enforces this policy before lifecycle start.';
}

function setEditorStep(step, { focus = true } = {}) {
  state.editorStep = Math.max(0, Math.min(3, Number(step) || 0));
  for (const panel of document.querySelectorAll('[data-wizard-panel]')) {
    const active = Number(panel.dataset.wizardPanel) === state.editorStep;
    if (panel.id === 'previewPanel') panel.hidden = !active || !state.preview;
    else if (panel.id === 'operationProgress') { if (!active) panel.hidden = true; }
    else panel.hidden = !active;
  }
  for (const item of document.querySelectorAll('[data-wizard-step]')) {
    const index = Number(item.dataset.wizardStep); item.classList.toggle('active', index === state.editorStep); item.classList.toggle('complete', index < state.editorStep);
    if (index === state.editorStep) item.setAttribute('aria-current','step'); else item.removeAttribute('aria-current');
  }
  byId('wizardBackButton').hidden = state.editorStep === 0;
  byId('wizardNextButton').hidden = state.editorStep === 3;
  byId('wizardNextButton').textContent = state.editorStep === 2 ? 'Review mount' : 'Continue';
  byId('applyMountButton').hidden = state.editorStep !== 3;
  byId('deleteMountButton').hidden = true;
  if (focus) {
    const panel = document.querySelector(`[data-wizard-panel="${state.editorStep}"]:not([hidden])`);
    const target = focusableNodes(panel)[0]; if (target?.focus) queueMicrotask(() => target.focus());
  }
}
function wizardBlockingIssues(step, issues = localEditorIssues()) {
  const fields = step === 0 ? new Set(['remote']) : step === 1 ? new Set(['name','mountpoint']) : null;
  return issues.filter((item) => item?.severity !== 'warning' && (!fields || fields.has(item.field)));
}
async function advanceEditorWizard() {
  state.editorInteracted = true; hideNotice(byId('editorError'));
  if (state.editorStep === 0) {
    updateRemoteEndpoint({applyDefaults:false}); const issues = wizardBlockingIssues(0); if (issues.length) { renderEditorIssues(issues); showNotice(byId('editorError'),'Choose a configured remote and folder before continuing.','error'); focusIssueField('remote'); return; }
    renderEditorIssues([]); setEditorStep(1); return;
  }
  if (state.editorStep === 1) {
    const local = wizardBlockingIssues(1); if (local.length) { renderEditorIssues(local); showNotice(byId('editorError'),'Complete the mount name and absolute destination before continuing.','error'); focusIssueField(local[0].field); return; }
    renderEditorIssues([]); setEditorStep(2); return;
  }
  if (state.editorStep === 2) { await previewEditor(false); if (state.preview) setEditorStep(3); return; }
}
function retreatEditorWizard() { if (state.editorStep <= 0) return; if (state.editorStep === 3) invalidatePreview({validate:false}); setEditorStep(state.editorStep - 1); }

function openEditor(config = null, trigger = document.activeElement) {
  if (!state.snapshot) return;
  state.editorTrigger = trigger instanceof HTMLElement ? trigger : null; const session=++state.editorSession;
  const existing=Boolean(config?.name); state.editorExisting=existing; state.editorOriginal=existing?config.name:''; state.editorDelete=false; state.editorManualRemote=false; state.editorRemoteReachable=null; state.editorProviderStatus=null; state.editorNameTouched=false; state.editorMountpointTouched=false; state.editorProfileTouched=false; state.editorBackendValidated=false; state.editorIssues=[]; state.editorStep=0; state.editorInteracted=false;
  fillForm(config||DEFAULT_MOUNT,existing); renderEditorIssues([]); hideNotice(byId('remoteTestResult')); hideNotice(byId('editorError')); byId('mountRemoteBrowser').hidden=true; byId('manualRemoteWrap').hidden=true; byId('mountAdvancedDetails').open=false; renderProviderReadiness();
  text('editorTitle',existing?`Edit ${config.name}`:'Add mount'); text('editorSubtitle',existing?'Move through the focused steps, then review the backend-authoritative change before applying it.':'Choose a source, destination and behavior. Validation appears as you interact, not before.');
  byId('previewMountButton').textContent=existing?'Review changes':'Review mount'; byId('applyMountButton').textContent=existing?'Apply changes':'Create mount'; byId('editorBackdrop').hidden=false;
  state.editorInitial=serializeEditor(); state.editorDirty=false; invalidatePreview({validate:false}); state.editorInitial=serializeEditor(); state.editorDirty=false; updateRemoteEndpoint({applyDefaults:false}); state.editorInitial=serializeEditor(); state.editorDirty=false;
  updateNetworkPolicyHelp(); setEditorStep(0,{focus:false});
  void loadMountEditorData(existing,session).then(()=>{if(session!==state.editorSession||byId('editorBackdrop').hidden)return;if(!state.editorDirty)state.editorInitial=serializeEditor(); renderEditorIssues([]);});
  queueMicrotask(()=>byId('mountRemoteSelect')?.focus());
}

function forceCloseEditor() { const returnFocus=state.editorTrigger; state.editorSession+=1; byId('editorBackdrop').hidden=true; byId('discardBackdrop').hidden=true; state.editorOriginal='';state.editorDelete=false;state.editorExisting=false;state.editorDirty=false;state.editorIssues=[];state.editorProviderStatus=null;state.editorRemoteReachable=null;state.editorTrigger=null;state.editorStep=0;state.editorInteracted=false; if(state.editorValidationTimer)clearTimeout(state.editorValidationTimer);state.editorValidationTimer=null;state.editorValidationSeq+=1;clearPreviewTimer();state.operationPollToken+=1;invalidatePreview({validate:false});renderEditorIssues([]);if(returnFocus?.focus)queueMicrotask(()=>returnFocus.focus()); }
function closeEditor() { markEditorDirty(); if(state.editorDirty && !byId('editorBackdrop').hidden){byId('discardBackdrop').hidden=false;queueMicrotask(()=>byId('keepEditingButton')?.focus());return;} forceCloseEditor(); }

function candidateRegistry(deleteMode = false) {
  if (!state.snapshot) throw new Error('Configuration snapshot is unavailable');
  if (deleteMode) return removeMount(state.snapshot.mounts, state.editorOriginal);
  return replaceMount(state.snapshot.mounts, state.editorOriginal, formValue());
}

function renderReviewCell(root, name, value) { const cell=document.createElement('div');cell.className='review-cell';const strong=document.createElement('strong');strong.textContent=name;const span=document.createElement('span');span.textContent=String(value||'—');cell.append(strong,span);root.append(cell); }
function renderPreviewCountdown() {
  const node=byId('previewCountdown'), help=byId('previewExpiryHelp'); if(!state.preview?.preview_expires_unix_ms){node.textContent='—';if(help)help.textContent='This approval is temporary and does not change configuration until you apply it.';return;}
  const ms=Number(state.preview.preview_expires_unix_ms)-Date.now();
  if(ms<=0){node.textContent='Expired';node.className='state-pill bad';if(help)help.textContent='Your safety approval expired. Nothing was changed; review the current configuration again.';byId('applyMountButton').disabled=true;byId('previewMountButton').textContent='Review again';return;}
  const total=Math.ceil(ms/1000),min=Math.floor(total/60),sec=String(total%60).padStart(2,'0');node.textContent=`Valid ${min}:${sec}`;node.className=total<=20?'state-pill warn':'state-pill good';if(help)help.textContent=total<=20?'This approval expires soon. Apply now or refresh the review.':'This approval is temporary and does not change configuration until you apply it.';
}
function renderPreview(value) {
  const root=byId('previewChanges');clear(root);const review=byId('reviewSummary');clear(review);const safety=byId('reviewSafety');const cfg=formValue();const profile=profilePresentation(cfg.vfs_profile,state.editorProfiles,state.editorRecommendation);const parsed=parseRemoteEndpoint(cfg.remote);
  byId('reviewTitle').textContent=state.editorDelete?`Delete mount “${state.editorOriginal}”?`:(state.editorExisting?`Ready to update “${cfg.name}”`:`Ready to create “${cfg.name}”`);
  if(state.editorDelete){renderReviewCell(review,'Configuration',state.editorOriginal);renderReviewCell(review,'Running mount','Will be stopped if required');renderReviewCell(review,'Cache','Preserved unless a separate cache action is approved');}
  else{renderReviewCell(review,'Source',`${parsed.remote||'—'}:${parsed.path||''}`);renderReviewCell(review,'Mount location',cfg.mountpoint);renderReviewCell(review,'Performance',`${cfg.vfs_profile}${profile.recommended?' · recommended':''}`);renderReviewCell(review,'Auto start',cfg.enabled?'Enabled':'Disabled');renderReviewCell(review,'Android visibility',cfg.allow_other?'Requested':'Owner only');renderReviewCell(review,'Access',cfg.read_only?'Read only':'Read/write');renderReviewCell(review,'Remote check',cfg.probe_remote?'Before start':'Not required');renderReviewCell(review,'Policy',`${cfg.network_mode}${cfg.charging_only?' · charging only':''}${cfg.min_battery?` · battery ≥ ${cfg.min_battery}%`:''}`);}
  const destructive=isDestructivePreview(value); safety.className=`notice compact ${destructive?'error':'ok'}`; safety.textContent=state.editorDelete?'Deletion removes this mount configuration and stops its lifecycle if needed. Skybind cache files are preserved by this action.':destructive?'This review includes a destructive or mount-location-sensitive change. Check the consequences below before applying.':'No destructive actions detected in this configuration review.';
  for(const change of value.changes||[]){const card=document.createElement('div');card.className='change-card';const title=document.createElement('strong');title.textContent=state.editorDelete?'What will happen':`${change.name}: ${change.kind}`;card.append(title);if(change.consequences?.length)card.append(paragraph(change.consequences.map((x)=>`✓ ${consequenceLabel(x)}`).join(' · '),'muted'));if(change.reasons?.length&&!state.editorDelete)card.append(paragraph(`Changed: ${change.reasons.join(', ')}`,'muted'));root.append(card);}
  if(!(value.changes||[]).length)root.append(paragraph('No configuration changes.','muted'));
  text('previewMeta',`Revision ${value.current_revision} · digest ${String(value.candidate_digest||'').slice(0,16)}… · proof expires ${formatTime(value.preview_expires_unix_ms)}${destructive?' · destructive change':''}`);byId('previewPanel').hidden=false;clearPreviewTimer();renderPreviewCountdown();state.previewTimer=setInterval(renderPreviewCountdown,1000);
  byId('applyMountButton').textContent=state.editorDelete?'Delete mount':(state.editorExisting?'Apply changes':'Create mount');
}

async function previewEditor(deleteMode = false) {
  const errorNode=byId('editorError');hideNotice(errorNode);state.editorDelete=deleteMode;state.editorInteracted=true;
  if(!deleteMode){const form=byId('mountForm');if(!form.checkValidity()){form.reportValidity();return;}const validation=await validateEditorNow();if(!validation?.valid||editorHasBlockingIssues(validation.issues||state.editorIssues)){showNotice(errorNode,'Fix the highlighted fields before reviewing this mount.','error');return;}}
  try{const candidates=candidateRegistry(deleteMode);const value=result(await preview('config.preview',{mounts:candidates}));state.preview=value;state.previewCandidates=candidates;renderPreview(value);byId('applyMountButton').disabled=!previewIsUsable(value,state.snapshot)||!(value.changes||[]).length;byId('previewMountButton').textContent=deleteMode?'Refresh delete review':'Refresh review';}
  catch(error){invalidatePreview({validate:false});const issues=error?.issues?.length?error.issues:[];if(issues.length)renderEditorIssues(issues);showNotice(errorNode,`${error?.code?`${error.code}: `:''}${String(error?.message||error)}${error?.detail?` · ${error.detail}`:''}`,'error');}
}

function renderOperationProgress(record, initial=false) {
  const root=byId('operationProgressSteps');clear(root);const steps=[];
  if(initial)steps.push({text:'Backend preview validated',state:'done'},{text:'Publishing configuration revision',state:'current'});
  for(const event of record?.events||[])steps.push({text:event.message||event.event||'Operation event',state:'done'});
  if(record?.state==='RUNNING')steps.push({text:'Waiting for lifecycle actions to finish',state:'current'});
  if(record?.state==='FAILED')steps.push({text:record?.error?.message||'Operation failed',state:'failed'});
  if(record?.state==='SUCCEEDED')steps.push({text:'Configuration and lifecycle actions completed',state:'done'});
  for(const step of steps){const li=document.createElement('li');li.className=step.state;li.textContent=step.text;root.append(li);}
  const pill=byId('operationProgressState');pill.textContent=record?.state||'Running';pill.className=record?.state==='FAILED'?'state-pill bad':record?.state==='SUCCEEDED'?'state-pill good':'state-pill warn';
}
async function monitorOperation(requestId,token){byId('operationProgress').hidden=false;renderOperationProgress(null,true);while(token===state.operationPollToken&&!byId('editorBackdrop').hidden){await new Promise((resolve)=>setTimeout(resolve,500));if(token!==state.operationPollToken)break;try{const record=result(await query('operation.status',{request_id:requestId}));renderOperationProgress(record);if(record.state&&record.state!=='RUNNING')break;}catch(_){/* journal can appear shortly after dispatch */}}}

function editMountByName(name){const cfg=(state.snapshot?.mounts||[]).find((item)=>item?.name===name);if(cfg)openEditor(cfg);else showMountOutcome(`Mount ${name} is not present in the latest configuration snapshot.`,'error');}
async function viewActivity(){await setView('activity');const behavior=document.body.classList.contains('reduce-motion')?'auto':'smooth';byId('operationCards')?.scrollIntoView({block:'start',behavior});}

async function applyEditor() {
  const errorNode=byId('editorError');if(!state.preview||!state.previewCandidates||!previewIsUsable(state.preview,state.snapshot)){showNotice(errorNode,'The review is stale or missing. Review the mount again before applying.','error');return;}
  byId('applyMountButton').disabled=true;const isDelete=state.editorDelete, wasExisting=state.editorExisting, submitted=formValue(), appliedName=submitted.name;byId('operationProgressTitle').textContent=isDelete?'Deleting mount…':(wasExisting?'Applying mount changes…':'Creating mount…');
  try{
    const handle=startOperation('config.apply','run',{expected_revision:state.preview.current_revision,candidate_digest:state.preview.candidate_digest,preview_proof:state.preview.preview_proof,mounts:state.previewCandidates});const token=++state.operationPollToken;void monitorOperation(handle.requestId,token);const envelope=await handle.completion;const applied=result(envelope);state.operationPollToken+=1;
    const failures=applied?.lifecycle_failures||[];forceCloseEditor();await loadMounts();
    if(failures.length){const codes=[...new Set(failures.map((item)=>item.code||'lifecycle_failed'))].join(', ');const first=failures[0]||{};const actions=[{label:'View activity',run:()=>void viewActivity()},{label:'View logs',run:()=>void setView('logs')}];if(!isDelete){if(submitted.enabled&&first.retryable)actions.unshift({label:'Retry start',run:()=>void lifecycleAction('start',appliedName),className:'primary'});actions.splice(submitted.enabled&&first.retryable?1:0,0,{label:'Edit mount',run:()=>editMountByName(appliedName),className:first.retryable?'':'primary'});}const detail=first.detail||first.error||'';showMountOutcome(`Configuration was saved, but ${failures.length} lifecycle action${failures.length===1?'':'s'} need attention (${codes})${detail?` · ${detail}`:''}.`, 'error', actions);}
    else if(isDelete) showMountOutcome('Mount deleted. Cache files were not removed by this configuration action.','ok');
    else showMountOutcome(wasExisting?'Mount changes applied successfully.':'Mount created successfully.','ok',[{label:'View runtime',run:()=>void setView('runtime')},{label:'View mount',run:()=>void setView('mounts'),className:'primary'}]);
  }catch(error){state.operationPollToken+=1;invalidatePreview({validate:false});if(error?.issues?.length)renderEditorIssues(error.issues);const prefix=['stale_revision','preview_required','preview_expired','preview_mismatch'].includes(error?.code)?'The configuration changed or your approval expired. Review again. ':'';showNotice(errorNode,`${prefix}${String(error?.message||error)}${error?.detail?` · ${error.detail}`:''}`,'error');}
}

async function openRollback(trigger = document.activeElement) {
  state.rollbackReturnFocus = trigger instanceof HTMLElement ? trigger : null;
  try {
    const value = result(await preview('config.rollback.preview', {})); state.rollbackPreview = value; const root = byId('rollbackPreview'); clear(root);
    root.append(paragraph(`Current revision ${value.current_revision}. This action requires this fresh one-use preview.`, 'muted'));
    for (const change of value.changes || []) root.append(paragraph(`${change.name}: ${change.kind} · ${(change.consequences || []).map(consequenceLabel).join(', ') || 'configuration change'}`, 'change-card'));
    byId('rollbackBackdrop').hidden = false; queueMicrotask(() => byId('closeRollbackButton')?.focus());
  } catch (error) { showNotice(byId('mountsNotice'), `Rollback unavailable: ${String(error?.message || error)}`, 'error'); }
}
function closeRollback() { const focus=state.rollbackReturnFocus; state.rollbackPreview = null; state.rollbackReturnFocus=null; byId('rollbackBackdrop').hidden = true; if(focus?.focus)queueMicrotask(()=>focus.focus()); }
async function applyRollback() {
  const value = state.rollbackPreview; if (!value?.preview_proof) return;
  try {
    result(await run('config.rollback', { expected_revision: value.current_revision, previous_digest: value.candidate_digest, preview_proof: value.preview_proof }));
    closeRollback(); await loadMounts(); showNotice(byId('mountsNotice'), 'Previous-known-good configuration restored.', 'ok');
  } catch (error) { closeRollback(); showNotice(byId('mountsNotice'), `Rollback failed: ${String(error?.message || error)}. Preview again before retrying.`, 'error'); }
}



function bytes(value) {
  let n = Number(value || 0); if (!Number.isFinite(n)) return '—';
  const units = ['B','KiB','MiB','GiB','TiB']; let i = 0; while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; }
  return `${n >= 10 || i === 0 ? n.toFixed(0) : n.toFixed(1)} ${units[i]}`;
}
function metric(root, name, value) { const cell=document.createElement('div'); const strong=document.createElement('strong'); strong.textContent=name; cell.append(strong,document.createTextNode(String(value ?? '—'))); root.append(cell); }

const jobFields = ['name','type','source','destination','every','network'];
const jobChecks = ['enabled','charging','confirm-sync'];
function normalizeJob(value) { return { name:String(value.name||'').trim(), enabled:Boolean(value.enabled), type:String(value.type||'copy'), source:String(value.source||'').trim(), destination:String(value.destination||'').trim(), every:String(value.every||'1h').trim(), network_mode:String(value.network_mode||'any'), charging_only:Boolean(value.charging_only), min_battery:Number(value.min_battery||0), confirm_destructive:Boolean(value.confirm_destructive) }; }
function invalidateJobPreview(){ state.jobPreview=null; state.jobCandidates=null; byId('applyJobButton').disabled=true; byId('jobPreviewText').textContent=''; hideNotice(byId('jobError')); }
function fillJob(job={},existing=false){ const v=normalizeJob(job); byId('job-name').value=v.name; byId('job-name').readOnly=existing; byId('job-type').value=v.type; byId('job-source').value=v.source; byId('job-destination').value=v.destination; byId('job-every').value=v.every; byId('job-network').value=v.network_mode; byId('job-battery').value=v.min_battery||''; byId('job-enabled').checked=v.enabled; byId('job-charging').checked=v.charging_only; byId('job-confirm-sync').checked=v.confirm_destructive; renderJobEncryptionNotice(); }
function jobFormValue(){ return normalizeJob({ name:byId('job-name').value,type:byId('job-type').value,source:byId('job-source').value,destination:byId('job-destination').value,every:byId('job-every').value,network_mode:byId('job-network').value,min_battery:byId('job-battery').value,enabled:byId('job-enabled').checked,charging_only:byId('job-charging').checked,confirm_destructive:byId('job-confirm-sync').checked }); }
function openJob(job=null,trigger=document.activeElement){ if(!state.jobSnapshot)return; state.jobReturnFocus=trigger instanceof HTMLElement?trigger:null; state.jobOriginal=job?.name||''; fillJob(job||{enabled:true,type:'copy',every:'1h',network_mode:'any'},Boolean(job)); invalidateJobPreview(); byId('deleteJobButton').hidden=!job; text('jobEditorTitle',job?`Edit ${job.name}`:'Add job'); byId('jobBackdrop').hidden=false; queueMicrotask(()=>byId('closeJobButton')?.focus()); }
function closeJob(){ const focus=state.jobReturnFocus; byId('jobBackdrop').hidden=true; state.jobReturnFocus=null; state.jobOriginal=''; invalidateJobPreview(); if(focus?.focus)queueMicrotask(()=>focus.focus()); }
function jobCandidates(deleteMode=false){ const list=[...(state.jobSnapshot?.jobs||[])]; if(deleteMode)return list.filter((j)=>j.name!==state.jobOriginal); const value=jobFormValue(); const index=list.findIndex((j)=>j.name===state.jobOriginal); if(index>=0)list[index]=value;else list.push(value); return list; }
async function previewJob(deleteMode=false){ try{ const candidates=jobCandidates(deleteMode); const value=result(await preview('jobs.preview',{jobs:candidates})); state.jobPreview=value;state.jobCandidates=candidates; byId('jobPreviewText').textContent=`Revision ${value.current_revision} · ${value.destructive_sync_jobs?.length?`destructive sync: ${value.destructive_sync_jobs.join(', ')}`:'no destructive sync jobs'}`;byId('applyJobButton').disabled=!value.preview_proof; }catch(error){invalidateJobPreview();showNotice(byId('jobError'),String(error?.message||error),'error');} }
async function applyJob(){ const v=state.jobPreview;if(!v?.preview_proof)return;try{ result(await run('jobs.apply',{expected_revision:v.current_revision,candidate_digest:v.candidate_digest,preview_proof:v.preview_proof,jobs:state.jobCandidates}));closeJob();await loadJobs();showNotice(byId('jobsNotice'),'Job registry applied from a fresh backend preview.','ok');}catch(error){invalidateJobPreview();showNotice(byId('jobError'),String(error?.message||error),'error');} }
async function runJob(name){ const notice=byId('jobsNotice');try{const pre=result(await preview('job.run.preview',{name}));if(pre?.destructive&&!globalThis.confirm(`Sync job ${name} may delete destination files not present at the source. Execute this job now?`)){showNotice(notice,`${name}: destructive sync not authorized.`,'warn');return;}const launched=result(await run('job.run',{name,proof:pre.preview_proof}));if(launched.state!=='RUNNING'||!launched.id)throw new Error('Backend returned no durable running claim');showNotice(notice,`${name}: run ${launched.id.slice(0,8)} started; outcome pending. Track progress in Jobs or Activity.`,'ok');await loadJobs();}catch(error){showNotice(notice,`${name}: ${String(error?.message||error)}`,'error');}}
function renderJobs(snapshot,status){ const root=byId('jobCards');clear(root);const stateMap=new Map((status||[]).map((j)=>[j.name,j]));if(!(snapshot.jobs||[]).length){root.append(paragraph('No scheduled jobs configured.','notice'));return;}for(const job of snapshot.jobs){const card=document.createElement('article');card.className='job-card';const head=document.createElement('div');head.className='mount-head';const t=document.createElement('div');const h=document.createElement('h3');h.textContent=job.name;t.append(h,paragraph(`${job.type}: ${job.source} → ${job.destination}`,'muted code'));const badges=document.createElement('div');badges.className='security-badge-row';const sourceBadge=encryptionBadgeForEndpoint(job.source),destinationBadge=encryptionBadgeForEndpoint(job.destination);if(sourceBadge){sourceBadge.title='Job source encryption';badges.append(sourceBadge);}if(destinationBadge){destinationBadge.title='Job destination encryption';badges.append(destinationBadge);}if(badges.childElementCount)t.append(badges);const st=stateMap.get(job.name)||{};head.append(t,label(st.last_state|| (job.enabled?'scheduled':'disabled'),st.last_state==='SUCCEEDED'?'state-pill good':st.last_state==='FAILED'?'state-pill bad':'state-pill'));card.append(head);const grid=document.createElement('div');grid.className='runtime-grid';metric(grid,'Every',job.every);metric(grid,'Next run',formatTime(st.next_run_unix_ms));metric(grid,'Runs',st.run_count||0);if(st.last_run_id){metric(grid,'Transferred',bytes(st.bytes));metric(grid,'Speed',`${bytes(st.speed_bytes_per_second)}/s`);metric(grid,'ETA',st.last_state==='RUNNING'?`${st.eta_seconds||0}s`:'—');if(st.reason)card.append(paragraph(st.reason,'muted'));}metric(grid,'Policy',`${job.network_mode||'any'}${job.charging_only?' · charging':''}`);card.append(grid);const actions=document.createElement('div');actions.className='mount-actions';const runButton=button('Run now',()=>void runJob(job.name),'primary');runButton.disabled=st.last_state==='RUNNING';actions.append(runButton,button('Edit',()=>openJob(job)));card.append(actions);root.append(card);}}
async function loadJobs(){ const [snap,status,remotes]=await Promise.all([query('jobs.snapshot'),query('jobs.status'),query('provider.remotes')]);state.jobSnapshot=result(snap);state.remoteDetails=result(remotes).details||[];renderJobs(state.jobSnapshot,result(status).jobs||[]); }

// Explicit, accessible selection. Never silently choose an Android namespace.
function chooseNamespaceGroups(snapshot) {
 const eligible=eligibleNamespaceGroups(snapshot);
 if(!eligible.length)throw new Error('No safely eligible app namespaces; inspect Android visibility first');
 return new Promise(resolve=>{
  const dialog=document.createElement('div');dialog.className='modal-backdrop';dialog.setAttribute('role','dialog');dialog.setAttribute('aria-modal','true');
  const pane=document.createElement('section');pane.className='editor-panel';pane.style.maxWidth='min(92vw,550px)';
  const title=document.createElement('h2');title.textContent='Select app namespaces';title.id='skybind-namespace-title';dialog.setAttribute('aria-labelledby',title.id);pane.append(title,paragraph('Only unprotected, fully inspected app groups are offered. Select each namespace explicitly.','muted'));
  const checks=[];for(const group of eligible){const line=document.createElement('label');line.className='checkbox-row';const input=document.createElement('input');input.type='checkbox';input.value=group.namespace;const desc=document.createElement('span');desc.textContent=`${group.namespace} · ${group.members.map(m=>`UID ${m.uid} (user ${m.android_user})`).join(', ').slice(0,180)}`;line.append(input,desc);pane.append(line);checks.push(input);}
  const actions=document.createElement('div');actions.className='button-row';const cancelButton=button('Cancel',()=>finish(null));const acceptButton=button('Preview selected',()=>{const selected=checks.filter(c=>c.checked).map(c=>c.value);try{finish(validateNamespaceSelection(snapshot,selected));}catch(err){errorNode.textContent=String(err.message||err);}} ,'primary');const errorNode=paragraph('','notice error');errorNode.setAttribute('role','alert');actions.append(cancelButton,acceptButton);pane.append(errorNode,actions);dialog.append(pane);document.body.append(dialog);
  const prior=document.activeElement;const onKey=e=>{if(e.key==='Escape'){e.preventDefault();finish(null);}else trapModalTab(e,dialog);};dialog.addEventListener('keydown',onKey);
  function finish(value){dialog.removeEventListener('keydown',onKey);dialog.remove();prior?.focus?.();resolve(value);}
  cancelButton.focus();
 });
}
async function namespaceAction(name,mode){const notice=byId('runtimeNotice');try{
 if(mode==='apply'){
  const observed=result(await query('namespace.inspect',{name}));
  const selected=await chooseNamespaceGroups(observed);if(!selected)return;
  const plan=result(await preview('namespace.preview',{name,namespaces:selected}));
  if(!plan.proof||JSON.stringify(plan.selected)!==JSON.stringify(selected))throw new Error('Namespace preview changed selection or omitted proof');
  if(!globalThis.confirm(`Apply app visibility to ${selected.length} explicitly selected namespace(s)?`))return;
  result(await run('namespace.apply',{name,namespaces:selected,proof:plan.proof}));
 }else{
  const plan=result(await preview('namespace.rollback.preview',{name}));
  if(!plan.proof)throw new Error('Backend did not issue rollback proof');
  if(!globalThis.confirm(`Release only verified Skybind-owned visibility for ${name}?`))return;
  result(await run('namespace.rollback',{name,proof:plan.proof}));
 }
 showNotice(notice,`${name}: namespace ${mode} completed.`,'ok');await loadRuntime();
 }catch(error){showNotice(notice,`${name}: ${String(error?.message||error)}`,'error');}}
async function cacheAction(name,action){const notice=byId('runtimeNotice');try{
 const native=result(await preview(`cache.${action}.preview`,{name}));const plan=nativeCachePreview(native,name,action);
 if(!globalThis.confirm(`Delete ${plan.delete_files} owned cache file(s) (${bytes(plan.bytes_to_remove)}) for ${name}?`))return;
 result(await run(`cache.${action}`,{name,proof:plan.proof}));
 showNotice(notice,`${name}: cache ${action} completed.`,'ok');await loadRuntime();
 }catch(error){showNotice(notice,`${name}: ${String(error?.message||error)}`,'error');}}
function renderRuntime(snapshot, health, policy, cache, inspections, metrics) {
  const root = byId('runtimeCards'); clear(root);
  const hmap = new Map((health || []).map((v) => [v.name, v]));
  const pmap = new Map((policy || []).map((v) => [v.name, v]));
  const cmap = new Map((cache || []).map((v) => [v.name, v]));
  for (const cfg of snapshot.mounts || []) {
    const h = hmap.get(cfg.name) || {}, pd = pmap.get(cfg.name) || {}, cs = cmap.get(cfg.name) || {}, ns = inspections.get(cfg.name) || {}, rcm = metrics.get(cfg.name) || {};
    const card = document.createElement('article'); card.className = 'runtime-card';
    const head = document.createElement('div'); head.className = 'mount-head'; const hh = document.createElement('h3'); hh.textContent = cfg.name;
    head.append(hh, label(h.state || 'UNKNOWN', healthClass(h.state))); card.append(head);
    if (h.failure_code) {
      const failure = paragraph(`${h.failure_code}${h.retryable ? ' · retryable' : ' · manual intervention required'}`, h.retryable ? 'runtime-cause warn-text' : 'runtime-cause error-text');
      card.append(failure);
    }
    const sourceReady = Boolean(h.process_alive && h.mount_alive && h.owned_mount && ns.source_owned);
    const vis = document.createElement('div'); vis.className = 'visibility-matrix';
    for (const cls of ['service','root','shell','termux','app']) {
      const visible = (ns.achieved_classes || []).includes(cls);
      const textValue = sourceReady ? `${cls}: ${visible ? 'visible' : 'not proven'}` : `${cls}: not applicable`;
      vis.append(label(textValue, sourceReady ? (visible ? 'state-pill good' : 'state-pill warn') : 'state-pill neutral'));
    }
    for (const user of ns.users || []) {
      const detail = sourceReady ? `user ${user.user_id}${user.primary ? ' primary' : ''}: ${user.qualified ? 'qualified' : 'not qualified'} · ${user.visible_namespaces || 0}/${user.app_namespaces || 0} visible` : `user ${user.user_id}${user.primary ? ' primary' : ''}: not applicable`;
      vis.append(label(detail, sourceReady ? (user.qualified ? 'state-pill good' : 'state-pill warn') : 'state-pill neutral'));
    }
    card.append(vis);
    const grid = document.createElement('div'); grid.className = 'runtime-grid';
    metric(grid, 'Readiness', h.readiness?.ready ? 'ready' : h.readiness?.waiting_reason || 'waiting');
    metric(grid, 'Policy', pd.decision?.allowed === false ? pd.decision?.reason || 'blocked' : 'allowed');
    metric(grid, 'Recovery', h.failure_code ? (h.retryable ? `retry ${h.restart_attempts || 0}/${h.restart_budget || 0}` : 'automatic retry blocked') : `${h.restart_attempts || 0}/${h.restart_budget || 0}`);
    metric(grid, 'Network', `${h.readiness?.network_class || 'unknown'} · ${h.readiness?.remote_state || 'not probed'}`);
    metric(grid, 'Cache', `${bytes(cs.bytes)} / ${bytes(cs.max_bytes)}`); metric(grid, 'Open files', rcm.open_files ?? '—'); metric(grid, 'Rate', rcm.available ? `${bytes(rcm.speed_bytes_per_sec)}/s` : 'unavailable'); card.append(grid);
    const actions = document.createElement('div'); actions.className = 'mount-actions';
    const makeVisible = button('Make app-visible', () => void namespaceAction(cfg.name, 'apply'));
    makeVisible.disabled = !sourceReady; makeVisible.title = sourceReady ? '' : 'Requires a live Skybind-owned source mount first';
    const hasAppVisibility = (ns.achieved_classes || []).includes('app');
    const releaseVisible = button('Release app visibility', () => void namespaceAction(cfg.name, 'rollback'));
    releaseVisible.disabled = !hasAppVisibility; releaseVisible.title = hasAppVisibility ? '' : 'No observed app visibility to release';
    actions.append(makeVisible, releaseVisible, button('Clear cache', () => void cacheAction(cfg.name, 'clear')), button('Forget cache', () => void cacheAction(cfg.name, 'forget'), 'danger'));
    card.append(actions); root.append(card);
  }
}

function shortHash(value){const text=String(value||'');return text.length>16?`${text.slice(0,12)}…${text.slice(-4)}`:(text||'—');}
function renderRuntimeStatus(runtime){
  const root=byId('runtimeEngineManager'); if(!root)return; clear(root);
  const card=document.createElement('article'); card.className='runtime-card runtime-status-hero';
  const head=document.createElement('div'); head.className='runtime-provenance-head';
  const title=document.createElement('div'); const eyebrow=paragraph('Bundled runtime','eyebrow'); const h=document.createElement('h3'); h.textContent=runtime.runtime_provider === 'bclone' ? 'bclone' : runtime.runtime_provider === 'newfuture' ? 'NewFuture rclone' : 'Bundled rclone';
  title.append(eyebrow,h,paragraph(runtime.runtime_version || runtime.runtime_build || 'Immutable at module install time','muted'));
  head.append(title,label(runtime.operational?'Operational':'Needs attention',runtime.operational?'state-pill good':'state-pill bad')); card.append(head);
  const grid=document.createElement('div'); grid.className='runtime-provenance-grid';
  metric(grid,'Provider',runtime.runtime_provider||'bundled'); metric(grid,'Repository',runtime.runtime_repository||'—');
  metric(grid,'Architecture','Android arm64'); metric(grid,'Runtime SHA',shortHash(runtime.runtime_sha256));
  metric(grid,'Authority',runtime.canonical?'Skybind bundled static':'non-canonical'); metric(grid,'Provenance',runtime.provenance_available?(runtime.provenance_valid?'verified':'invalid'):'not available'); card.append(grid);
  const fuse=document.createElement('section'); fuse.className='runtime-fuse-card'; const fh=document.createElement('div'); fh.className='mount-head'; const ftitle=document.createElement('div'); const fhead=document.createElement('h4'); fhead.textContent='FUSE helper'; ftitle.append(fhead,paragraph('Provider-independent helper authority is fixed to NewFuture.','muted')); fh.append(ftitle,label(runtime.fuse_helper_ready?'Ready':'Missing',runtime.fuse_helper_ready?'state-pill good':'state-pill bad')); fuse.append(fh);
  const fgrid=document.createElement('div'); fgrid.className='runtime-provenance-grid'; metric(fgrid,'Provider',runtime.fuse_helper_provider==='newfuture'?'NewFuture':runtime.fuse_helper_provider||'NewFuture'); metric(fgrid,'Repository',runtime.fuse_helper_repository||'NewFuture/rclone-fuse3-magisk'); metric(fgrid,'Release',runtime.fuse_helper_release||'—'); metric(fgrid,'Helper SHA',shortHash(runtime.fuse_helper_sha256)); fuse.append(fgrid); card.append(fuse);
  const details=document.createElement('details'); details.className='runtime-technical-details'; const summary=document.createElement('summary'); summary.textContent='Technical paths'; details.append(summary); const dgrid=document.createElement('div'); dgrid.className='runtime-path-list'; metric(dgrid,'Binary',runtime.binary||'—'); metric(dgrid,'FUSE helper',runtime.fuse_helper_binary||'—'); metric(dgrid,'Config',runtime.config||'—'); details.append(dgrid); card.append(details);
  if(runtime.issues?.length) card.append(detailBlock('Runtime issues',runtime.issues.map((issue)=>['Issue',issue])));
  card.append(paragraph('Runtime changes require building and installing a new Skybind module. Live import, activation, rollback and on-device runtime updates are not part of this product line.','runtime-static-note'));
  root.append(card);
}

async function loadRuntime(){const [snapEnvelope,runtimeEnvelope,he,po,ca]=await Promise.all([query('config.snapshot'),query('runtime.status'),query('mount.health'),query('policy.status'),query('cache.status')]);const snap=result(snapEnvelope),runtime=result(runtimeEnvelope);const notice=byId('runtimeNotice');const runtimeMessage=`Runtime authority: ${runtime.mode||'unknown'} · ${runtime.source||'unknown'}${runtime.canonical?' · canonical':''}`;showNotice(notice,runtimeMessage,runtime.operational?'ok':'error');renderRuntimeStatus(runtime);const inspections=new Map(),metrics=new Map();await Promise.all((snap.mounts||[]).map(async(m)=>{try{inspections.set(m.name,result(await query('namespace.inspect',{name:m.name})));}catch(_){inspections.set(m.name,{});}try{metrics.set(m.name,result(await query('rc.metrics',{name:m.name})));}catch(_){metrics.set(m.name,{});}}));renderRuntime(snap,result(he).health||[],result(po).policies||[],result(ca).caches||[],inspections,metrics);}

function logFilterValues() {
  return {
    severity: byId('logSeverityFilter')?.value || '',
    source: byId('logSourceFilter')?.value || '',
    search: (byId('logSearch')?.value || '').trim().toLowerCase(),
  };
}
function updateLogSources(records) {
  const select = byId('logSourceFilter'); if (!select) return;
  const current = select.value; const sources = [...new Set(records.map((r) => r.source || r.category || 'skybind'))].sort();
  while (select.options.length > 1) select.remove(1);
  for (const source of sources) { const option = document.createElement('option'); option.value = source; option.textContent = source; select.append(option); }
  if (sources.includes(current)) select.value = current;
}
function visibleLogRecords() {
  const filters = logFilterValues();
  return state.logRecords.filter((rec) => {
    const source = rec.source || rec.category || 'skybind'; const body = `${rec.message || ''} ${rec.code || ''} ${rec.name || ''} ${source}`.toLowerCase();
    return (!filters.severity || rec.severity === filters.severity) && (!filters.source || source === filters.source) && (!filters.search || body.includes(filters.search));
  }).slice().sort((a, b) => Number(b.time_unix_ms || 0) - Number(a.time_unix_ms || 0));
}
function logRecordLine(rec) {
  const source=rec.source||rec.category||'skybind';
  const message=rec.message||`${rec.category||''} ${rec.name||''} ${rec.state||''} ${rec.code||''}`.trim();
  return `${formatTime(rec.time_unix_ms)} ${rec.severity||'INFO'} ${source} ${message}${rec.code&&rec.message?` [${rec.code}]`:''}`;
}
function renderLogs(records = state.logRecords) {
  state.logRecords = Array.isArray(records) ? records : [];
  updateLogSources(state.logRecords);
  const filtered = visibleLogRecords();
  text('logResultCount', `${filtered.length} record${filtered.length===1?'':'s'}${state.logPaused?' · paused':''}`);
  const root = byId('logCards'); clear(root);
  if (!filtered.length) { const empty=document.createElement('div');empty.className='empty-state';empty.append(paragraph('No matching diagnostic records.','empty-state-title'),paragraph('Change the filters, refresh, or wait for new backend events.','muted'));root.append(empty); return; }
  for (const rec of filtered) {
    const row=document.createElement('article');row.className=`log-row severity-${rec.severity||'INFO'}`;
    const time=document.createElement('time');time.className='log-time';time.textContent=formatTime(rec.time_unix_ms);
    const sev=label(rec.severity||'INFO',`log-severity severity-${rec.severity||'INFO'}`);
    const source=document.createElement('span');source.className='log-source';source.textContent=rec.source||rec.category||'skybind';
    const body=document.createElement('div');body.className='log-body';
    const message=rec.message||`${rec.category||''} ${rec.name||''} ${rec.state||''} ${rec.code||''}`.trim();
    body.append(paragraph(message,'log-message'));
    if(rec.code&&rec.message)body.append(paragraph(rec.code,'log-code'));
    const meta=document.createElement('div');meta.className='log-meta';meta.append(time,sev,source);
    row.append(meta,body);
    if (Number(rec.suppressed || 0) > 0 || (Array.isArray(rec.details)&&rec.details.length)) {
      const details=document.createElement('details');details.className='log-details';const summary=document.createElement('summary');const shown=Array.isArray(rec.details)?rec.details.length:0;summary.textContent=Number(rec.suppressed||0)>0?`Technical detail · ${shown} shown / ${rec.suppressed} suppressed`:'Technical detail';details.append(summary);const pre=document.createElement('pre');pre.textContent=(rec.details||[]).join('\n');details.append(pre);row.append(details);
    }
    root.append(row);
  }
}
async function loadLogs(){const limit=Number(state.settingsSnapshot?.settings?.log_limit||100);const value=result(await query('diagnostics.logs',{limit}));state.logRecords=value.records||[];renderLogs();if(value.records?.length)state.logCursor=Math.max(...value.records.map((r)=>Number(r.time_unix_ms||0)));byId('logFollow').checked=Boolean(state.settingsSnapshot?.settings?.log_follow);}
function setLogPaused(paused){state.logPaused=Boolean(paused);const control=byId('logPauseButton');if(control){control.setAttribute('aria-pressed',String(state.logPaused));control.textContent=state.logPaused?'Resume':'Pause';}renderLogs();scheduleRefresh();announceStatus(state.logPaused?'Log following paused.':'Log following resumed.');}
async function copyVisibleLogs(){const lines=visibleLogRecords().map(logRecordLine).join('\n');if(!lines){showNotice(byId('logsNotice'),'No visible log records to copy.','');return;}try{await navigator.clipboard.writeText(lines);showNotice(byId('logsNotice'),`Copied ${visibleLogRecords().length} visible log records.`,'ok');}catch(error){showNotice(byId('logsNotice'),`Copy unavailable: ${String(error?.message||error)}`,'error');}}
function exportVisibleLogs(){const rows=visibleLogRecords();if(!rows.length){showNotice(byId('logsNotice'),'No visible log records to export.','');return;}const blob=new Blob([rows.map(logRecordLine).join('\n')+'\n'],{type:'text/plain;charset=utf-8'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`skybind-logs-${new Date().toISOString().replaceAll(':','-')}.txt`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);showNotice(byId('logsNotice'),`Exported ${rows.length} visible log records.`,'ok');}
function clearLogView(){state.logRecords=[];state.logCursor=0;renderLogs();showNotice(byId('logsNotice'),'Local log view cleared. Backend log retention was not changed.','ok');}

function renderPlatform(value){const root=byId('platformDetails');clear(root);const mgr=value.root_manager||{};const rows=[['Manager',mgr.name||mgr.kind],['Compatible',mgr.compatible?'yes':'no'],['Embedded WebUI',mgr.capabilities?.embedded_webui?'available':'not claimed'],['Integrity',value.integrity?.ok?'verified':'not verified'],['State schema',value.state?.schema_version??'—'],['Transport',transportName()]];for(const [k,v] of rows){const row=document.createElement('div');row.className='detail-row';row.append(document.createTextNode(k),document.createTextNode(String(v??'—')));root.append(row);}}
function doctorGroup(code){if(code.startsWith('crypt.'))return 'Security & encryption';if(code.startsWith('runtime.')||code.startsWith('provider.'))return 'Runtime';if(code.startsWith('fuse.')||code.startsWith('kernel.'))return 'FUSE';if(code.startsWith('root.')||code.startsWith('state.')||code.startsWith('module.'))return 'System';if(code.startsWith('network')||code.startsWith('storage.'))return 'Network & storage';if(code.startsWith('mounts.')||code.startsWith('namespace.'))return 'Mounts & visibility';if(code.startsWith('jobs.'))return 'Jobs';return 'Other';}
function renderDoctor(report){
  const root=byId('doctorCards');clear(root);const checks=report.checks||[];const actionable=checks.filter((c)=>c.status==='WARN'||c.status==='FAIL').length;
  const summary=byId('doctorSummary');clear(summary);const hero=document.createElement('article');hero.className=`doctor-summary ${report.overall==='FAIL'?'bad':actionable?'warn':'good'}`;const copy=document.createElement('div');const h=document.createElement('h3');h.textContent=report.overall==='FAIL'?'Needs attention':actionable?'Healthy with advisories':'Healthy';copy.append(h,paragraph(actionable?`${actionable} actionable finding${actionable===1?'':'s'}.`:'All required capabilities are available.','muted'));hero.append(copy,label(report.overall||'PASS',report.overall==='FAIL'?'state-pill bad':actionable?'state-pill warn':'state-pill good'));summary.append(hero);
  const groups=new Map();for(const check of checks){const name=doctorGroup(check.code||'');if(!groups.has(name))groups.set(name,[]);groups.get(name).push(check);}
  for(const [name,items] of groups){const section=document.createElement('section');section.className='doctor-group';const heading=document.createElement('h3');heading.textContent=name;section.append(heading);for(const check of items){const card=document.createElement('article');card.className=`doctor-card ${check.status}`;const head=document.createElement('div');head.className='doctor-check-head';const title=document.createElement('strong');title.textContent=check.summary;head.append(label(check.status,check.status==='PASS'?'state-pill good':check.status==='INFO'?'state-pill neutral':check.status==='WARN'?'state-pill warn':'state-pill bad'),title);card.append(head);if(check.detail)card.append(paragraph(check.detail,'muted'));if(check.guidance)card.append(paragraph(`Next: ${check.guidance}`,'doctor-guidance'));section.append(card);}root.append(section);}
}
async function runDoctorUI(){try{renderDoctor(result(await query('doctor.report')));}catch(error){showNotice(byId('doctorNotice')||byId('settingsNotice'),String(error?.message||error),'error');}}
function decodeBase64(data){const binary=atob(data);const bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);return bytes;}
async function buildBundle(){const root=byId('bundleResult');try{const meta=result(await run('doctor.bundle',{}));const payload=result(await query('doctor.bundle.read',{bundle_id:meta.bundle_id}));const blob=new Blob([decodeBase64(payload.data)],{type:'application/zip'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=payload.filename;a.textContent=`Save ${payload.filename}`;const copy=button('Copy checksum',()=>void navigator.clipboard?.writeText(payload.sha256));clear(root);root.hidden=false;root.append(a,document.createTextNode(` · ${bytes(payload.size)} · `),copy);setTimeout(()=>URL.revokeObjectURL(url),60000);}catch(error){showNotice(root,String(error?.message||error),'error');}}

function settingsValue(){return {refresh_seconds:Number(byId('setting-refresh').value),log_limit:Number(byId('setting-log-limit').value),log_max_bytes:Number(byId('setting-log-max').value),log_backups:Number(byId('setting-log-backups').value),webui_idle_seconds:Number(byId('setting-idle').value),default_view:byId('setting-default-view').value,default_mount_view:byId('setting-mount-view').value,log_follow:byId('setting-log-follow').checked,dense_mode:byId('setting-dense').checked,reduced_motion:byId('setting-reduced-motion').checked};}
function applySettingsPresentation(){const s=state.settingsSnapshot?.settings||{};document.body.classList.toggle('dense',Boolean(s.dense_mode||s.default_mount_view==='dense'));document.body.classList.toggle('reduce-motion',Boolean(s.reduced_motion));byId('logFollow').checked=Boolean(s.log_follow);}
function settingsHint(message){text('settingsApplyHint',message||'Preview changes first. Apply stays disabled until Skybind returns a fresh preview proof.');}
function invalidateSettingsPreview(){state.settingsPreview=null;byId('applySettingsButton').disabled=true;byId('settingsPreview').textContent='';settingsHint('Preview changes first. Apply stays disabled until Skybind returns a fresh preview proof.');}
async function previewSettings(){const control=byId('previewSettingsButton');setButtonBusy(control,true,'Previewing…');try{const v=result(await preview('ui.settings.preview',{settings:settingsValue()}));state.settingsPreview=v;byId('applySettingsButton').disabled=!v.preview_proof;byId('settingsPreview').textContent=`Revision ${v.current_revision} · refresh ${v.settings.refresh_seconds}s · logs ${bytes(v.settings.log_max_bytes)} × ${v.settings.log_backups} · idle ${v.settings.webui_idle_seconds}s`;settingsHint(v.preview_proof?'Preview ready. Review the summary, then apply this exact revision.':'Preview did not produce an apply proof.');announceStatus('Settings preview ready.');}catch(error){invalidateSettingsPreview();showNotice(byId('settingsNotice'),String(error?.message||error),'error');announceStatus('Settings preview failed.');}finally{setButtonBusy(control,false);}}
async function applySettings(){const v=state.settingsPreview;if(!v?.preview_proof)return;const control=byId('applySettingsButton');setButtonBusy(control,true,'Applying…');try{state.settingsSnapshot=result(await run('ui.settings.apply',{expected_revision:v.current_revision,candidate_digest:v.candidate_digest,preview_proof:v.preview_proof,settings:v.settings}));state.settingsPreview=null;applySettingsPresentation();showNotice(byId('settingsNotice'),'WebUI settings applied from fresh preview.','ok');byId('settingsPreview').textContent='';settingsHint('Settings are current. Change a preference to create a new preview.');announceStatus('Settings applied.');scheduleRefresh();}catch(error){state.settingsPreview=null;showNotice(byId('settingsNotice'),String(error?.message||error),'error');settingsHint('Apply failed. Preview again before retrying so Skybind can bind a fresh revision.');announceStatus('Settings apply failed.');}finally{setButtonBusy(control,false);control.disabled=true;}}
function fillSettings(s){byId('setting-refresh').value=s.refresh_seconds;byId('setting-log-limit').value=s.log_limit;byId('setting-log-max').value=s.log_max_bytes;byId('setting-log-backups').value=s.log_backups;byId('setting-idle').value=s.webui_idle_seconds;byId('setting-default-view').value=s.default_view;byId('setting-mount-view').value=s.default_mount_view||'cards';byId('setting-log-follow').checked=Boolean(s.log_follow);byId('setting-dense').checked=Boolean(s.dense_mode);byId('setting-reduced-motion').checked=Boolean(s.reduced_motion);}
async function useRemoteForMount(endpoint,trigger=null){if(!state.snapshot){state.snapshot=result(await query('config.snapshot'));}openEditor(null,trigger||document.activeElement);const parsed=parseRemoteEndpoint(endpoint);byId('field-remote').value=endpoint;state.editorRemotePath=parsed.path;byId('mountRemotePath').value=parsed.path?`/${parsed.path}`:'/';state.editorManualRemote=false;state.editorInteracted=true;updateRemoteEndpoint();setEditorStep(1);}
function closeRemoteActions(){const focus=state.remoteActionReturnFocus;byId('remoteActionBackdrop').hidden=true;state.remoteAction=null;state.remoteActionReturnFocus=null;if(focus?.focus)queueMicrotask(()=>focus.focus());}
function openRemoteActions(remote,entry,currentPath,trigger){
  const itemPath=entry?.path||currentPath||''; const objectEndpoint=`${remote}:${itemPath}`; const mountEndpoint=`${remote}:${entry?.is_dir?itemPath:(currentPath||'')}`;
  state.remoteAction={remote,entry,currentPath,objectEndpoint,mountEndpoint};state.remoteActionReturnFocus=trigger||document.activeElement;
  text('remoteActionTitle',entry?.name||`${remote}:`);text('remoteActionPath',objectEndpoint);const encrypted=remoteDetail(remote)?.encryption==='rclone-crypt';byId('remoteProtectCrypt').hidden=encrypted;byId('remoteActionBackdrop').hidden=false;queueMicrotask(()=>byId('remoteUseMount')?.focus());
}
function cryptSpecValue(){return {name:byId('crypt-name').value.trim(),remote:byId('crypt-remote').value.trim(),filename_encryption:byId('crypt-filename-mode').value,directory_name_encryption:byId('crypt-directory-names').checked,filename_encoding:byId('crypt-filename-encoding').value};}
function suggestCryptName(endpoint){const parsed=parseRemoteEndpoint(endpoint);const base=(parsed.remote||'Secure').replace(/[^A-Za-z0-9._-]/g,'')||'Secure';let name=`${base}Crypt`;const used=new Set((state.remoteDetails||[]).map((item)=>item.name));for(let i=2;used.has(name);i++)name=`${base}Crypt${i}`;return name;}
function invalidateCryptPreview(){state.cryptPreview=null;byId('createCryptButton').disabled=true;clear(byId('cryptPreview'));hideNotice(byId('cryptError'));}
async function openCryptCreator(backing='',trigger=document.activeElement,onCreated=null){
  if(!backing&&state.remote)backing=endpointFor(state.remote,state.remotePath);if(!backing){showNotice(byId('remotesNotice'),'Choose a remote or folder before creating encrypted storage.','warn');return;}
  state.cryptTrigger=trigger instanceof HTMLElement?trigger:null;state.cryptOnCreated=onCreated;byId('crypt-name').value=suggestCryptName(backing);byId('crypt-remote').value=backing;byId('crypt-filename-mode').value='standard';byId('crypt-directory-names').checked=true;byId('crypt-filename-encoding').value='base32';invalidateCryptPreview();byId('cryptBackdrop').hidden=false;
  try{const status=await refreshCryptPasswordStatus();queueMicrotask(()=>status.configured?byId('crypt-name')?.focus():byId('crypt-inline-password')?.focus());}catch(error){renderCryptPasswordStatus({configured:false,password2:'unset',authority:'skybind-user-defined'});showNotice(byId('cryptError'),backendErrorText(error),'error');queueMicrotask(()=>byId('crypt-inline-password')?.focus());}
}
function closeCryptCreator(){const focus=state.cryptTrigger;byId('cryptBackdrop').hidden=true;state.cryptTrigger=null;state.cryptOnCreated=null;if(byId('crypt-inline-password'))byId('crypt-inline-password').value='';invalidateCryptPreview();if(focus?.focus)queueMicrotask(()=>focus.focus());}
async function previewCryptCreation(){const control=byId('previewCryptButton');setButtonBusy(control,true,'Reviewing…');try{const value=result(await preview('provider.crypt.preview',{spec:cryptSpecValue()}));state.cryptPreview=value;const node=byId('cryptPreview');clear(node);node.append(paragraph(`Encrypted remote ${value.spec.name}: → ${value.spec.remote}`,'crypt-preview-title'),paragraph(`Filenames: ${value.spec.filename_encryption} · directory names: ${value.spec.directory_name_encryption?'encrypted':'unchanged'} · encoding: ${value.spec.filename_encoding}`,'muted'),paragraph('Uses your configured Skybind encryption password. Skybind does not generate a password, password2 remains unset, and the password is never returned to the WebUI.','muted'));byId('createCryptButton').disabled=!value.preview_proof;announceStatus('Encrypted remote preview ready.');}catch(error){invalidateCryptPreview();showNotice(byId('cryptError'),backendErrorText(error),'error');if(error?.code==='crypt_password_required')renderCryptPasswordStatus({configured:false,password2:'unset',authority:'skybind-user-defined'});announceStatus('Encrypted remote preview failed.');}finally{setButtonBusy(control,false);control.disabled=!state.cryptPasswordStatus?.configured;}}
async function createCryptRemote(){const v=state.cryptPreview;if(!v?.preview_proof)return;const control=byId('createCryptButton');setButtonBusy(control,true,'Creating…');try{const created=result(await run('provider.crypt.create',{spec:v.spec,candidate_digest:v.candidate_digest,preview_proof:v.preview_proof}));const callback=state.cryptOnCreated;const remote=created.remote;closeCryptCreator();await loadRemotes();showNotice(byId('remotesNotice'),`🔒 ${remote.name}: created and verified as an rclone crypt remote using the configured Skybind password.`,'ok');announceStatus('Encrypted remote created.');if(callback)callback(remote);}catch(error){invalidateCryptPreview();showNotice(byId('cryptError'),backendErrorText(error),'error');if(error?.code==='crypt_password_required')renderCryptPasswordStatus({configured:false,password2:'unset',authority:'skybind-user-defined'});announceStatus('Encrypted remote creation failed.');}finally{setButtonBusy(control,false);control.disabled=!state.cryptPreview?.preview_proof;}}
function selectCreatedCryptForMount(remote){state.editorRemotes=[...new Set([...state.editorRemotes,remote.name])];state.remoteDetails=[...(state.remoteDetails||[]).filter((item)=>item.name!==remote.name),remote];renderMountRemoteSelect();byId('mountRemoteSelect').value=remote.name;state.editorRemotePath='';state.editorManualRemote=false;byId('manualRemoteWrap').hidden=true;updateRemoteEndpoint();}

async function copyRemoteActionPath(){const value=state.remoteAction?.objectEndpoint||'';if(!value)return;const notice=byId('remotesNotice');try{if(!navigator.clipboard?.writeText)throw new Error('Clipboard access is unavailable in this browser');await navigator.clipboard.writeText(value);closeRemoteActions();showNotice(notice,'Remote path copied to clipboard.','ok');announceStatus('Remote path copied to clipboard.');}catch(error){showNotice(notice,`Could not copy remote path: ${String(error?.message||error)}`,'error');announceStatus('Remote path copy failed.');}}
async function browseRemote(remote,path=''){
  state.remote=remote;state.remotePath=path;const root=byId('remoteEntries');clear(root);byId('remoteParentButton').disabled=!path;
  try{
    const value=result(await query('provider.browse',{remote,path,limit:150}));state.remotePath=value.path||'';byId('remoteBreadcrumb').textContent=`${remote}:${state.remotePath}`;byId('remoteParentButton').disabled=!state.remotePath;
    const entries=value.entries||[];if(!entries.length)root.append(paragraph('This folder is empty.','notice empty-state'));
    for(const entry of entries){
      const row=document.createElement('div');row.className='remote-entry remote-object-row';
      let main;if(entry.is_dir){main=button('',()=>void browseRemote(remote,entry.path),'remote-object-main');}else{main=document.createElement('div');main.className='remote-object-main static';}
      const icon=document.createElement('span');icon.className='remote-object-icon';icon.textContent=entry.is_dir?'📁':'📄';
      const copy=document.createElement('span');copy.className='remote-object-copy';const name=document.createElement('strong');name.textContent=entry.name;const meta=document.createElement('small');meta.textContent=entry.is_dir?'Folder':(entry.size?bytes(entry.size):'File');copy.append(name,meta);main.append(icon,copy);
      if(entry.is_dir){const chev=document.createElement('span');chev.className='remote-object-chevron';chev.setAttribute('aria-hidden','true');chev.textContent='›';main.append(chev);}
      const menu=button('⋮',()=>openRemoteActions(remote,entry,state.remotePath,menu),'icon-button remote-object-action');menu.setAttribute('aria-label',`Actions for ${entry.name}`);menu.setAttribute('aria-haspopup','dialog');row.append(main,menu);root.append(row);
    }
    if(value.truncated)root.append(paragraph('This listing is truncated. Open a narrower folder to continue.','muted'));
  }catch(error){root.append(paragraph(`Browse failed: ${String(error?.message||error)}`,'notice error'));}
}
async function useRemoteForJob(endpoint,field,trigger=null){if(!state.jobSnapshot){state.jobSnapshot=result(await query('jobs.snapshot'));}openJob(null,trigger||document.activeElement);byId(field==='source'?'job-source':'job-destination').value=endpoint;invalidateJobPreview();renderJobEncryptionNotice();}
async function loadRemotes(){const value=result(await query('provider.remotes'));state.remoteDetails=value.details||[];const root=byId('remoteButtons');clear(root);for(const name of value.remotes||[]){const detail=remoteDetail(name);const encrypted=detail?.encryption==='rclone-crypt';const chip=button(`${encrypted?'🔒':'△'} ${name}:`,()=>void browseRemote(name,''),'remote-choice');if(encrypted){const provenance=detail.managed_by_skybind?` · Skybind generation ${detail.password_revision||'?'}${detail.password_current?' current':' older'}`:' · external crypt';chip.title=`Encrypted via rclone crypt → ${detail.backing_remote||'backing remote'}${provenance}`;if(detail.managed_by_skybind&&!detail.password_current)chip.classList.add('provenance-old');}else chip.title='Not protected by rclone crypt';chip.setAttribute('aria-pressed',String(state.remote===name));root.append(chip);}if(!(value.remotes||[]).length){root.append(paragraph('No configured remotes were returned.','muted'));byId('remoteBreadcrumb').textContent='No remotes configured';}else if(!state.remote){byId('remoteBreadcrumb').textContent='Choose a remote';}}

async function loadSettings(){const [settings,platform,cryptPassword,recovery]=await Promise.all([query('ui.settings'),query('platform.status'),query('provider.crypt.password.status'),query('provider.crypt.recovery.status')]);state.settingsSnapshot=result(settings);fillSettings(state.settingsSnapshot.settings);applySettingsPresentation();renderPlatform(result(platform));renderCryptPasswordStatus(result(cryptPassword));renderCryptRecoveryStatus(result(recovery),[]);}
async function loadDoctor(){await runDoctorUI();}
async function loadRemoteBrowser(){await loadRemotes();}

function stopTimer() { if (state.timer) clearTimeout(state.timer); state.timer = null; }
function refreshDelay(){const configured=Number(state.settingsSnapshot?.settings?.refresh_seconds||5)*1000;if(state.activeView==='runtime'||state.activeView==='jobs')return Math.max(2000,configured);if(state.activeView==='logs'&&state.settingsSnapshot?.settings?.log_follow&&!state.logPaused)return Math.max(2000,configured);if(state.activeView==='mounts')return Math.max(3000,configured);return Math.max(5000,configured);}
async function loadViewData(view,{announce=true}={}){const titles={home:'Home',mounts:'Mounts',jobs:'Jobs',activity:'Activity',more:'More',runtime:'Runtime',remotes:'Remote browser',doctor:'Doctor',logs:'Logs',settings:'Settings'};if(view==='more')return;setViewBusy(view,true,announce?`Loading ${titles[view]||view}…`:'');try{if(view==='mounts')await loadMounts();else if(view==='jobs')await loadJobs();else if(view==='activity')await loadOperations();else if(view==='runtime')await loadRuntime();else if(view==='remotes')await loadRemoteBrowser();else if(view==='doctor')await loadDoctor();else if(view==='logs')await loadLogs();else if(view==='settings')await loadSettings();else if(view==='home')await loadHome();if(announce)announceStatus(`${titles[view]||view} ready.`);}catch(error){if(announce)announceStatus(`${titles[view]||view} failed to load.`);throw error;}finally{setViewBusy(view,false);}}
async function refreshView(view){try{await loadViewData(view,{announce:true});}catch(error){const notices={home:'compatibility',mounts:'mountsNotice',jobs:'jobsNotice',activity:'activityNotice',runtime:'runtimeNotice',remotes:'remotesNotice',doctor:'doctorNotice',logs:'logsNotice',settings:'settingsNotice'};const node=byId(notices[view]||'compatibility');showNotice(node,`Refresh failed: ${String(error?.message||error)}`,'error');}}
function scheduleRefresh() {
  stopTimer(); if (document.visibilityState !== 'visible') return;
  state.timer=setTimeout(async()=>{try{if(state.activeView==='logs'&&(!state.settingsSnapshot?.settings?.log_follow||state.logPaused))return;await loadViewData(state.activeView,{announce:false});}catch(_){}finally{scheduleRefresh();}},refreshDelay());
}
async function setView(view) {
  const names=['home','mounts','jobs','activity','more','runtime','remotes','doctor','logs','settings'];
  const secondary=new Set(['runtime','remotes','doctor','logs','settings']);
  const titles={home:'Home',mounts:'Mounts',jobs:'Jobs',activity:'Activity',more:'More',runtime:'Runtime',remotes:'Remote browser',doctor:'Doctor',logs:'Logs',settings:'Settings'};
  if(!names.includes(view))view='home';state.activeView=view;stopTimer();
  const primary=secondary.has(view)?'more':view;
  for(const name of names)byId(`view-${name}`).hidden=name!==view;
  for(const nav of document.querySelectorAll('.nav-item')){const active=nav.dataset.view===primary;nav.classList.toggle('active',active);if(active)nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');}
  for(const nav of document.querySelectorAll('.nav-secondary,.more-card,.settings-link')){const active=nav.dataset.view===view;nav.classList.toggle('active',active);if(active)nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');}
  text('pageTitle',titles[view]||'Home');
  try{await loadViewData(view,{announce:true});}catch(error){compatibility.hidden=false;compatibility.className='notice error';compatibility.textContent=`Backend unavailable or incompatible: ${String(error?.message||error)}`;}scheduleRefresh();
}
const skybindLogin = byId('skybindLogin');
byId('skybindLoginForm')?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const tokenInput=byId('skybindLoginToken'), submit=byId('skybindLoginButton');
  const notice=byId('skybindLoginError'); notice.hidden=true;
  submit.disabled=true;
  try {
    await authenticateStandalone(tokenInput.value.trim());
    tokenInput.value=''; skybindLogin.hidden=true;
    state.caps=null; await bootstrap();
  } catch(error) {
    tokenInput.value='';notice.textContent=String(error?.message||error);notice.hidden=false;
  } finally {submit.disabled=false;}
});
async function bootstrap(){compatibility.hidden=false;compatibility.className='notice';compatibility.textContent='Checking backend compatibility…';badge.textContent='Connecting…';try{await ensureConnected();state.settingsSnapshot=result(await query('ui.settings'));applySettingsPresentation();await setView(state.settingsSnapshot.settings?.default_view||'home');}catch(error){compatibility.hidden=false;compatibility.className='notice error';compatibility.textContent=`Backend unavailable or incompatible: ${String(error?.message||error)}`;badge.textContent='Unavailable';if(transportName()==='standalone'){skybindLogin.hidden=false;byId('skybindLoginToken')?.focus();}}}
for(const nav of document.querySelectorAll('.nav-item,.nav-secondary,.more-card,.settings-link'))nav.addEventListener('click',()=>void setView(nav.dataset.view));
byId('retryButton')?.addEventListener('click',()=>void refreshView('home'));byId('homeAddMountButton')?.addEventListener('click',()=>void openHomeMountEditor());byId('homeAddJobButton')?.addEventListener('click',()=>void openHomeJobEditor());byId('homeSeeMountsButton')?.addEventListener('click',()=>void setView('mounts'));byId('homeSeeActivityButton')?.addEventListener('click',()=>void setView('activity'));byId('refreshMountsButton')?.addEventListener('click',()=>void refreshView('mounts'));byId('refreshOperationsButton')?.addEventListener('click',()=>void refreshView('activity'));byId('refreshJobsButton')?.addEventListener('click',()=>void refreshView('jobs'));byId('refreshRuntimeButton')?.addEventListener('click',()=>void refreshView('runtime'));byId('refreshLogsButton')?.addEventListener('click',()=>void refreshView('logs'));byId('refreshSettingsButton')?.addEventListener('click',()=>void refreshView('settings'));
byId('reconcileButton')?.addEventListener('click',()=>void reconcileAll());byId('addMountButton')?.addEventListener('click',()=>openEditor());byId('rollbackButton')?.addEventListener('click',()=>void openRollback());byId('closeEditorButton')?.addEventListener('click',closeEditor);byId('closeRollbackButton')?.addEventListener('click',closeRollback);byId('previewMountButton')?.addEventListener('click',()=>void previewEditor(false));byId('wizardBackButton')?.addEventListener('click',retreatEditorWizard);byId('wizardNextButton')?.addEventListener('click',()=>void advanceEditorWizard());byId('deleteMountButton')?.addEventListener('click',()=>void previewEditor(true));byId('applyMountButton')?.addEventListener('click',()=>void applyEditor());byId('applyRollbackButton')?.addEventListener('click',()=>void applyRollback());
byId('closeMountActionsButton')?.addEventListener('click',closeMountActions);byId('mountActionStart')?.addEventListener('click',()=>{const name=state.mountActionName;closeMountActions();if(name)void lifecycleAction('start',name);});byId('mountActionStop')?.addEventListener('click',()=>{const name=state.mountActionName;closeMountActions();if(name)void lifecycleAction('stop',name);});byId('mountActionRestart')?.addEventListener('click',()=>{const name=state.mountActionName;closeMountActions();if(name)void lifecycleAction('restart',name);});byId('mountActionEdit')?.addEventListener('click',()=>{const cfg=selectedMountActionConfig();const trigger=state.mountActionReturnFocus;closeMountActions();if(cfg)openEditor(cfg,trigger);});byId('mountActionActivity')?.addEventListener('click',()=>{closeMountActions();void setView('activity');});byId('mountActionLogs')?.addEventListener('click',()=>{closeMountActions();void setView('logs');});byId('mountActionDelete')?.addEventListener('click',()=>void deleteMountFromActions());
byId('closeRemoteActionsButton')?.addEventListener('click',closeRemoteActions);byId('remoteProtectCrypt')?.addEventListener('click',()=>{const backing=state.remoteAction?.mountEndpoint;const trigger=state.remoteActionReturnFocus;closeRemoteActions();if(backing)void openCryptCreator(backing,trigger);});byId('remoteUseMount')?.addEventListener('click',()=>{const endpoint=state.remoteAction?.mountEndpoint;const trigger=state.remoteActionReturnFocus;closeRemoteActions();if(endpoint)void useRemoteForMount(endpoint,trigger);});byId('remoteUseJobSource')?.addEventListener('click',()=>{const endpoint=state.remoteAction?.objectEndpoint;const trigger=state.remoteActionReturnFocus;closeRemoteActions();if(endpoint)void useRemoteForJob(endpoint,'source',trigger);});byId('remoteUseJobDestination')?.addEventListener('click',()=>{const endpoint=state.remoteAction?.objectEndpoint;const trigger=state.remoteActionReturnFocus;closeRemoteActions();if(endpoint)void useRemoteForJob(endpoint,'destination',trigger);});byId('remoteCopyPath')?.addEventListener('click',()=>void copyRemoteActionPath());byId('remoteParentButton')?.addEventListener('click',()=>{if(!state.remote)return;const parent=state.remotePath.split('/').filter(Boolean).slice(0,-1).join('/');void browseRemote(state.remote,parent);});
byId('addJobButton')?.addEventListener('click',()=>openJob());byId('job-source')?.addEventListener('input',renderJobEncryptionNotice);byId('job-source')?.addEventListener('change',renderJobEncryptionNotice);byId('job-destination')?.addEventListener('input',renderJobEncryptionNotice);byId('job-destination')?.addEventListener('change',renderJobEncryptionNotice);byId('closeJobButton')?.addEventListener('click',closeJob);byId('previewJobButton')?.addEventListener('click',()=>void previewJob(false));byId('deleteJobButton')?.addEventListener('click',()=>void previewJob(true));byId('applyJobButton')?.addEventListener('click',()=>void applyJob());byId('jobForm')?.addEventListener('input',invalidateJobPreview);byId('jobForm')?.addEventListener('change',invalidateJobPreview);
byId('createCryptRemoteButton')?.addEventListener('click',()=>void openCryptCreator());byId('closeCryptButton')?.addEventListener('click',closeCryptCreator);byId('previewCryptButton')?.addEventListener('click',()=>void previewCryptCreation());byId('createCryptButton')?.addEventListener('click',()=>void createCryptRemote());byId('cryptForm')?.addEventListener('input',invalidateCryptPreview);byId('cryptForm')?.addEventListener('change',invalidateCryptPreview);byId('setInlineCryptPasswordButton')?.addEventListener('click',()=>void setSkybindCryptPassword('crypt-inline-password','setInlineCryptPasswordButton','cryptError'));byId('setCryptPasswordButton')?.addEventListener('click',()=>void setSkybindCryptPassword('setting-crypt-password','setCryptPasswordButton','cryptPasswordNotice'));
byId('runDoctorButton')?.addEventListener('click',()=>void refreshView('doctor'));byId('bundleButton')?.addEventListener('click',()=>void buildBundle());byId('refreshRemotesButton')?.addEventListener('click',()=>void refreshView('remotes'));byId('previewSettingsButton')?.addEventListener('click',()=>void previewSettings());byId('applySettingsButton')?.addEventListener('click',()=>void applySettings());byId('settingsForm')?.addEventListener('input',(event)=>{if(event.target?.id!=='setting-crypt-password')invalidateSettingsPreview();});byId('settingsForm')?.addEventListener('change',(event)=>{if(event.target?.id!=='setting-crypt-password')invalidateSettingsPreview();});byId('logFollow')?.addEventListener('change',()=>{if(state.settingsSnapshot?.settings){state.settingsSnapshot.settings.log_follow=byId('logFollow').checked;scheduleRefresh();}});byId('logPauseButton')?.addEventListener('click',()=>setLogPaused(!state.logPaused));byId('logCopyButton')?.addEventListener('click',()=>void copyVisibleLogs());byId('logExportButton')?.addEventListener('click',exportVisibleLogs);byId('logClearButton')?.addEventListener('click',clearLogView);
for(const id of ['logSeverityFilter','logSourceFilter','logSearch'])byId(id)?.addEventListener(id==='logSearch'?'input':'change',()=>renderLogs());
byId('mountForm')?.addEventListener('submit',(event)=>{event.preventDefault();void previewEditor(false);});
byId('mountForm')?.addEventListener('input',(event)=>{state.editorInteracted=true;if(event.target?.id==='field-name')state.editorNameTouched=true;if(event.target?.id==='field-mountpoint')state.editorMountpointTouched=true;if(event.target?.id==='field-remote'){state.editorManualRemote=true;state.editorRemoteReachable=null;const parsed=parseRemoteEndpoint(event.target.value);state.editorRemotePath=parsed.path;byId('mountRemoteEndpoint').textContent=event.target.value||'—';renderProviderReadiness();renderMountEncryptionNotice();}invalidatePreview();});
byId('mountForm')?.addEventListener('change',(event)=>{state.editorInteracted=true;if(event.target?.id==='field-vfs_profile')updateProfilePresentation();if(event.target?.id==='field-network_mode')updateNetworkPolicyHelp();invalidatePreview();});
byId('mountRemoteSelect')?.addEventListener('change',()=>{state.editorInteracted=true;state.editorRemotePath='';state.editorRemoteReachable=null;byId('mountRemotePath').value='/';state.editorManualRemote=false;byId('manualRemoteWrap').hidden=true;updateRemoteEndpoint();});
byId('browseMountRemoteButton')?.addEventListener('click',()=>void browseMountRemote());
byId('testMountRemoteButton')?.addEventListener('click',()=>void testMountRemote());
byId('manualRemoteButton')?.addEventListener('click',()=>setManualRemote(!state.editorManualRemote));
byId('mountRemoteParentButton')?.addEventListener('click',()=>{const remote=byId('mountRemoteSelect').value;const parent=state.editorRemotePath.split('/').filter(Boolean).slice(0,-1).join('/');void browseMountRemote(remote,parent);});
byId('useMountRemoteFolderButton')?.addEventListener('click',chooseCurrentRemoteFolder);
for(const node of document.querySelectorAll('[data-mountpoint-template]'))node.addEventListener('click',()=>applyMountpointSuggestion(node.dataset.mountpointTemplate));
byId('keepEditingButton')?.addEventListener('click',()=>{byId('discardBackdrop').hidden=true;byId('closeEditorButton').focus();});
byId('discardChangesButton')?.addEventListener('click',forceCloseEditor);
byId('editorBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('editorBackdrop'))closeEditor();});byId('discardBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('discardBackdrop')){byId('discardBackdrop').hidden=true;byId('closeEditorButton').focus();}});byId('mountActionBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('mountActionBackdrop'))closeMountActions();});byId('remoteActionBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('remoteActionBackdrop'))closeRemoteActions();});byId('cryptBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('cryptBackdrop'))closeCryptCreator();});});byId('jobBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('jobBackdrop'))closeJob();});byId('rollbackBackdrop')?.addEventListener('click',(event)=>{if(event.target===byId('rollbackBackdrop'))closeRollback();});document.addEventListener('keydown',(event)=>{if(!byId('discardBackdrop').hidden&&trapModalTab(event,byId('discardBackdrop')))return;if(!byId('mountActionBackdrop').hidden&&trapModalTab(event,byId('mountActionBackdrop')))return;if(!byId('remoteActionBackdrop').hidden&&trapModalTab(event,byId('remoteActionBackdrop')))return;if(!byId('cryptBackdrop').hidden&&trapModalTab(event,byId('cryptBackdrop')))return;if(!byId('editorBackdrop').hidden&&trapModalTab(event,byId('editorBackdrop')))return;if(!byId('jobBackdrop').hidden&&trapModalTab(event,byId('jobBackdrop')))return;if(!byId('rollbackBackdrop').hidden&&trapModalTab(event,byId('rollbackBackdrop')))return;if(event.key!=='Escape')return;if(!byId('discardBackdrop').hidden){byId('discardBackdrop').hidden=true;byId('closeEditorButton').focus();return;}if(!byId('mountActionBackdrop').hidden){closeMountActions();return;}if(!byId('remoteActionBackdrop').hidden){closeRemoteActions();return;}if(!byId('cryptBackdrop').hidden){closeCryptCreator();return;}if(!byId('jobBackdrop').hidden){closeJob();return;}if(!byId('editorBackdrop').hidden){closeEditor();return;}if(!byId('rollbackBackdrop').hidden)closeRollback();});document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible')void setView(state.activeView);else stopTimer();});void bootstrap();
