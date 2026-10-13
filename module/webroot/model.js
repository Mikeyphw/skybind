export const DEFAULT_MOUNT = Object.freeze({
  name: '', enabled: true, remote: '', mountpoint: '', vfs_cache_mode: 'full', vfs_cache_max_size: '',
  vfs_cache_max_age: '', dir_cache_time: '', poll_interval: '', allow_other: true, read_only: false,
  log_level: 'INFO', require_network: false, probe_remote: false, network_mode: 'offline-allowed',
  charging_only: false, min_battery: 0, min_free_cache_space: '', boot_settle: '', network_settle: '',
  vfs_profile: 'custom', cache_high_water: 90, cache_low_water: 75,
});

function number(value, fallback = 0) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function candidate(value = {}) {
  const out = { ...DEFAULT_MOUNT, ...value };
  out.name = String(out.name ?? '').trim();
  out.remote = String(out.remote ?? '').trim();
  out.mountpoint = String(out.mountpoint ?? '').trim();
  out.vfs_cache_mode = String(out.vfs_cache_mode || 'full').trim().toLowerCase();
  out.vfs_profile = String(out.vfs_profile || 'custom').trim().toLowerCase();
  out.log_level = String(out.log_level || 'INFO').trim().toUpperCase();
  out.network_mode = String(out.network_mode || 'offline-allowed').trim().toLowerCase();
  for (const key of ['vfs_cache_max_size','vfs_cache_max_age','dir_cache_time','poll_interval','min_free_cache_space','boot_settle','network_settle']) {
    out[key] = String(out[key] ?? '').trim();
  }
  for (const key of ['enabled','allow_other','read_only','require_network','probe_remote','charging_only']) out[key] = Boolean(out[key]);
  out.min_battery = number(out.min_battery, 0);
  out.cache_high_water = number(out.cache_high_water, 90);
  out.cache_low_water = number(out.cache_low_water, 75);
  delete out.has_args_file;
  return out;
}

export function replaceMount(mounts, originalName, next) {
  const clean = candidate(next);
  const source = Array.isArray(mounts) ? mounts : [];
  const result = source.filter((item) => item?.name !== originalName).map(candidate);
  result.push(clean);
  result.sort((a, b) => a.name.localeCompare(b.name));
  return result;
}

export function removeMount(mounts, name) {
  return (Array.isArray(mounts) ? mounts : []).filter((item) => item?.name !== name).map(candidate);
}

export function mountRows(snapshot, statuses, health) {
  const statusMap = new Map((Array.isArray(statuses) ? statuses : []).map((item) => [item.name, item]));
  const healthMap = new Map((Array.isArray(health) ? health : []).map((item) => [item.name, item]));
  return (snapshot?.mounts || []).map((config) => ({ config, status: statusMap.get(config.name) || {}, health: healthMap.get(config.name) || {} }));
}

export function previewIsUsable(preview, snapshot) {
  return Boolean(preview?.preview_proof && preview?.candidate_digest && Number(preview?.current_revision) === Number(snapshot?.revision));
}

export function isDestructivePreview(preview) {
  return (preview?.changes || []).some((change) => change.kind === 'delete' || (change.reasons || []).includes('mountpoint'));
}

export function operationSummary(record) {
  const events = Array.isArray(record?.events) ? record.events : [];
  const last = events.at(-1) || {};
  return {
    requestId: record?.request_id || '', operation: record?.operation || 'operation', state: record?.state || 'UNKNOWN',
    cancellable: Boolean(record?.cancellable), message: last.message || record?.error?.message || '',
    event: last.event || '', updatedUnixMS: Number(record?.updated_unix_ms || 0), events,
  };
}

export function activityPresentation(record) {
  const model = operationSummary(record);
  const labels = {
    'mount.start': 'Mount started',
    'mount.stop': 'Mount stopped',
    'mount.restart': 'Mount restarted',
    'mount.reconcile': 'Managed mounts reconciled',
    'config.apply': 'Mount configuration applied',
    'config.rollback': 'Mount configuration rolled back',
    'jobs.apply': 'Job configuration applied',
    'job.run': 'Job run',
    'namespace.apply': 'App visibility applied',
    'namespace.rollback': 'App visibility released',
    'namespace.reconcile': 'App visibility reconciled',
    'cache.prune': 'Mount cache pruned',
    'cache.clear': 'Mount cache cleared',
    'cache.forget': 'Mount cache reset',
    'doctor.bundle': 'Support bundle created',
    'ui.settings.apply': 'WebUI settings updated',



  };
  const fallback = String(model.operation || 'operation').replaceAll('.', ' ').replace(/\b\w/g, (m) => m.toUpperCase());
  return {
    ...model,
    title: labels[model.operation] || fallback,
    subtitle: model.message,
  };
}

export function consequenceLabel(value) {
  const labels = {
    lifecycle_start: 'start mount', lifecycle_stop: 'stop mount', lifecycle_restart: 'restart mount',
    namespace_requalify: 're-qualify app visibility', namespace_release: 'release Skybind namespace binds',
    cache_preserved: 'preserve cache files', cache_policy_recheck: 're-check VFS/cache policy',
    policy_recheck: 're-check resource policy', configuration_create: 'create configuration',
  };
  return labels[value] || String(value || '').replaceAll('_', ' ');
}

const SIZE_RE = /^[0-9]+(?:\.[0-9]+)?(?:b|k|kb|kib|m|mb|mib|g|gb|gib|t|tb|tib|p|pb|pib)?$/i;
const DURATION_RE = /^(?:0|off|(?:[0-9]+(?:\.[0-9]+)?(?:ns|us|µs|ms|s|m|h))+(?:[0-9]+(?:\.[0-9]+)?(?:ns|us|µs|ms|s|m|h))*|[0-9]+(?:\.[0-9]+)?[dw])$/i;
const NAME_RE = /^[A-Za-z0-9._-]+$/;

function uiIssue(code, category, field, message, detail = '', suggestion = '', severity = 'error', relatedMount = '') {
  return { code, category, field, severity, message, detail, suggestion, related_mount: relatedMount };
}

export function parseRemoteEndpoint(value) {
  const raw = String(value ?? '').trim();
  const index = raw.indexOf(':');
  if (index <= 0) return { raw, remote: '', path: '' };
  return { raw, remote: raw.slice(0, index), path: raw.slice(index + 1).replace(/^\/+|\/+$/g, '') };
}

function titleCase(value) {
  return String(value || '').replace(/[._-]+/g, ' ').replace(/\s+/g, ' ').trim().replace(/\b\w/g, (m) => m.toUpperCase());
}

export function suggestMountDefaults(endpoint) {
  const parsed = parseRemoteEndpoint(endpoint);
  const segments = parsed.path.split('/').filter(Boolean);
  const label = titleCase(segments.at(-1) || parsed.remote || 'Mount');
  const source = [parsed.remote, ...segments.slice(-1)].filter(Boolean).join('-').toLowerCase();
  const name = source.replace(/[^a-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'mount';
  return { name, mountpoint: `/storage/emulated/0/Rclone/${label || 'Mount'}` };
}

export function localMountIssues(value, mounts = [], originalName = '') {
  const cfg = candidate(value);
  const issues = [];
  if (!cfg.name || !NAME_RE.test(cfg.name)) issues.push(uiIssue('invalid_mount_name', 'input', 'name', 'Use a valid mount name', 'Only letters, numbers, dot, underscore, and dash are allowed.', 'Example: drive-movies'));
  if (!cfg.remote) issues.push(uiIssue('remote_required', 'remote', 'remote', 'Choose a configured remote', '', 'Use the remote browser or enter remote:path manually.'));
  if (!cfg.mountpoint.startsWith('/')) issues.push(uiIssue('mountpoint_absolute_required', 'destination', 'mountpoint', 'Mount location must be an absolute path', cfg.mountpoint, '/storage/emulated/0/Rclone/<name>'));
  if (cfg.vfs_cache_max_size && !SIZE_RE.test(cfg.vfs_cache_max_size)) issues.push(uiIssue('invalid_cache_size', 'vfs', 'vfs_cache_max_size', 'Cache size is not valid', cfg.vfs_cache_max_size, 'Try 512MiB, 2GiB, or 8GiB.'));
  for (const [field, label] of [['vfs_cache_max_age','Cache maximum age'],['dir_cache_time','Directory cache duration'],['poll_interval','Poll interval'],['boot_settle','Boot settle delay'],['network_settle','Network settle delay']]) {
    const current = String(cfg[field] || '');
    if (current && !DURATION_RE.test(current)) issues.push(uiIssue('invalid_duration', field.includes('settle') ? 'advanced' : 'vfs', field, `${label} is not valid`, current, 'Try 30s, 15m, 24h, or 7d.'));
  }
  if (cfg.min_battery < 0 || cfg.min_battery > 100) issues.push(uiIssue('invalid_min_battery', 'policy', 'min_battery', 'Minimum battery must be between 0 and 100', String(cfg.min_battery), 'Use 0 to disable this threshold.'));
  if (!(cfg.cache_low_water >= 1 && cfg.cache_low_water < cfg.cache_high_water && cfg.cache_high_water <= 100)) issues.push(uiIssue('invalid_cache_watermarks', 'vfs', 'cache_low_water', 'Cache watermarks are inconsistent', `${cfg.cache_low_water}/${cfg.cache_high_water}`, 'Try 75% low-water and 90% high-water.'));
  if (cfg.mountpoint.startsWith('/')) {
    const clean = cfg.mountpoint.replace(/\/+$/g, '');
    for (const other of Array.isArray(mounts) ? mounts : []) {
      if (!other?.mountpoint || other?.name === originalName) continue;
      const theirs = String(other.mountpoint).replace(/\/+$/g, '');
      if (clean === theirs || clean.startsWith(`${theirs}/`) || theirs.startsWith(`${clean}/`)) {
        issues.push(uiIssue('mountpoint_overlap', 'destination', 'mountpoint', `Mount location overlaps “${other.name}”`, `${clean} ↔ ${theirs}`, 'Choose a separate folder.', 'error', other.name));
      }
    }
  }
  return issues;
}

export function profilePresentation(profile, profiles = [], recommendation = null) {
  const item = (Array.isArray(profiles) ? profiles : []).find((entry) => entry?.name === profile) || null;
  const recommended = recommendation?.profile === profile;
  return {
    name: profile,
    description: item?.description || (profile === 'custom' ? 'Use explicit VFS settings.' : ''),
    options: item?.options || {},
    recommended,
  };
}

// M2: normalize the deliberately narrow, authenticated rclone aggregate RC
// counters. Missing counters remain null; never invent upload/download rates.
export function performanceSample(payload, now = Date.now()) {
  const raw = payload?.performance;
  const absent = {status:'unavailable', sampledAt:0, speed:null, bytes:null, errors:null, cacheBytes:null, cacheFiles:null, writeback:'unknown', queued:null, active:null, failed:null};
  if (!raw || raw.source !== 'authenticated_rclone_rc_aggregate' || !['available','partial'].includes(raw.state)) return absent;
  const numeric = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1e15 ? value : null;
  const timestamp = numeric(raw.sampled_at_unix_ms);
  if (timestamp === null || timestamp > now + 30000 || now - timestamp > 30000) return absent;
  const wb = payload?.writeback || {};
  const validWB = ['idle','busy','errored'].includes(wb.state) && wb.source === 'authenticated_vfs_stats';
  return {
    status: raw.state, sampledAt:timestamp,
    speed:numeric(raw.total_speed_bytes_per_second),
    bytes:numeric(raw.transferred_bytes), errors:numeric(raw.rc_errors),
    cacheBytes:numeric(raw.vfs_cache_bytes), cacheFiles:numeric(raw.vfs_cache_files),
    writeback:validWB ? wb.state : 'unknown',
    queued:validWB ? numeric(wb.uploads_queued) : null,
    active:validWB ? numeric(wb.uploads_in_progress) : null,
    failed:validWB ? numeric(wb.errored_files) : null,
  };
}

export function boundedPerformanceHistory(history, sample, max = 60) {
  const previous = Array.isArray(history) ? history : [];
  if (sample?.speed === null || !Number.isFinite(sample?.speed) || !Number.isFinite(sample?.sampledAt)) return previous.slice(-max);
  const next = previous.length && previous[previous.length-1].at === sample.sampledAt ? previous.slice(0,-1) : previous;
  return [...next,{at:sample.sampledAt,speed:sample.speed}].slice(-Math.min(60,Math.max(1,max)));
}

// M3: advisory pressure only. It never authorizes deleting a cached file.
export function cachePressureAdvice(sample, config) {
  const max = Number(config?.cache_max_bytes ?? 0);
  const used = sample?.cacheBytes;
  const high = Number(config?.cache_high_percent ?? 90);
  const low = Number(config?.cache_low_percent ?? 75);
  if (sample?.status === 'unavailable' || typeof used !== 'number' || !Number.isFinite(used) ||
      !Number.isSafeInteger(max) || max <= 0 || !Number.isInteger(high) || !Number.isInteger(low) ||
      high < 1 || high > 100 || low < 0 || low >= high) return {state:'unknown',message:'Cache pressure unavailable; no eviction is assumed.'};
  const percent = Math.max(0,Math.round(100*used/max));
  if(percent>=high) return {state:'high',percent,message:`Cache ${percent}% of configured soft target. rclone manages eviction; pending uploads stay protected.`};
  return {state:'normal',percent,message:`Cache ${percent}% of configured soft target; native VFS eviction only.`};
}
// A display-only, narrowly scoped explanation of effective profile VFS flags.
// Fixed runtime args (remote, mountpoint, credentials, cache directory) are omitted.
export function effectiveVfsOptions(config, profiles=[]) {
  const cfg=candidate(config);
  const selected=(Array.isArray(profiles)?profiles:[]).find(p=>p?.name===cfg.vfs_profile);
  const o=cfg.vfs_profile==='custom' || !selected ? {
    vfs_cache_mode:cfg.vfs_cache_mode, vfs_cache_max_size:cfg.vfs_cache_max_size,
    vfs_cache_max_age:cfg.vfs_cache_max_age,dir_cache_time:cfg.dir_cache_time,poll_interval:cfg.poll_interval
  }:selected.options||{};
  const flags=[['--vfs-cache-mode',o.vfs_cache_mode],['--vfs-cache-max-size',o.vfs_cache_max_size],
    ['--vfs-cache-max-age',o.vfs_cache_max_age],['--dir-cache-time',o.dir_cache_time],
    ['--poll-interval',o.poll_interval],['--vfs-cache-min-free-space',cfg.min_free_cache_space]];
  return {flags:flags.filter(([_,v])=>String(v??'')!=='').map(([k,v])=>`${k} ${String(v)}`),
    readOnly:Boolean(cfg.read_only || selected?.read_only || cfg.vfs_profile==='read-only'),
    profile:cfg.vfs_profile};
}

// Pure, dependency-free M5 presentation helpers. Never interpret a manifest
// record as locally verified unless offline.status confirms the object hash.
export function safeOfflineRelativePath(raw) {
  const path = String(raw ?? '').trim();
  if (!path || path.length > 512 || path.startsWith('/') || /[\\:\x00\r\n\t]/.test(path)) return null;
  if (path.split('/').some(seg => !seg || seg === '.' || seg === '..' || seg.length > 255)) return null;
  return path;
}
export function offlineSnapshotSummary(manifest, mount) {
  const pins = Array.isArray(manifest?.pins) ? manifest.pins.filter(p => p?.mount === mount && typeof p.path === 'string') : [];
  const seen = new Set(); let referencedBytes = 0;
  for (const p of manifest?.pins || []) {
    if (!/^[0-9a-f]{64}$/.test(String(p?.sha256 || '')) || seen.has(p.sha256)) continue;
    seen.add(p.sha256);
    const n = Number(p.size);
    if (Number.isSafeInteger(n) && n >= 0) referencedBytes += n;
  }
  return {pins: pins.slice(0,100), count:pins.length, referencedBytes, quotaBytes: Number(manifest?.quota_bytes) || 0};
}
export function activeOfflineTask(tasks, mount) {
  const entries=Array.isArray(tasks) ? tasks : [];
  return entries.find(t=>t?.state==='RUNNING') || [...entries].reverse().find(t=>t?.mount===mount) || null;
}

// M8: policy-based WebUI polling budget. Mounted FUSE and supervisor run
// independently; lowering idle UI RPC traffic never delays backend recovery.
export function m8RefreshDelay({view, configuredSeconds=5, logsFollowing=false, mountAttention=false}={}) {
  const seconds=Number(configuredSeconds);
  const configured=Number.isFinite(seconds)&&seconds>=1&&seconds<=3600?seconds*1000:5000;
  if (view==='more') return null;
  if (view==='logs') return logsFollowing?Math.max(2000,configured):null;
  if (view==='mounts') return mountAttention?Math.max(3000,configured):Math.max(15000,configured);
  if (view==='jobs'||view==='runtime')return Math.max(2000,configured);
  return Math.max(5000,configured);
}
