// Explicit, presentation-only adapters for the original WebUI contract.
// Unknown provenance, device qualification and crypt generation data remain UNKNOWN.
export function runtimePresentation(v) {
  if (!v || typeof v.ready !== 'boolean' || typeof v.provider !== 'string') throw new Error('Malformed runtime authority');
  const verified = v.ready === true;
  const issues = verified ? ['Android FUSE/device operation is not independently qualified'] : [String(v.reason || 'Runtime integrity unavailable')];
  return {
    ...v, mode:'static', source:'skybind-bundled-static', canonical:true,
    operational:verified, runtime_provider:v.provider || 'unknown',
    runtime_sha256:v.runtime_sha256 || '', runtime_repository:v.runtime_repository || '',
    provenance_available:Boolean(v.provenance_available), provenance_valid:verified && Boolean(v.provenance_valid),
    fuse_helper_provider:'newfuture', fuse_helper_ready:verified && Boolean(v.fuse_helper_sha256),
    fuse_helper_sha256:v.fuse_helper_sha256 || '', binary:v.binary || '',
    fuse_helper_binary:v.fuse_helper_binary || '', config:v.config || '', issues,
  };
}
export function platformPresentation(v) {
  if (!v || typeof v.manager !== 'string' || typeof v.root !== 'boolean') throw new Error('Malformed platform detection');
  return {
    ...v,
    root_manager:{name:v.manager,kind:v.manager,compatible: Boolean(v.root && v.confirmed && v.module_present),
      // Directory detection does not prove that an embedded bridge works.
      capabilities:{embedded_webui:false}},
    integrity:{ok:false,verified:false,reason:'Platform detection does not attest executable integrity'},
    state:{schema_version:null,reason:'State schema not reported by platform detection'},
  };
}
export function bundleMetadata(v) {
  if (!v || !/^[a-f0-9]{32}$/.test(v.id) || !Number.isSafeInteger(v.bytes) || v.bytes < 0 || !/^[0-9a-f]{64}$/.test(v.sha256)) throw new Error('Malformed support-bundle metadata');
  return {...v,bundle_id:v.id,size:v.bytes};
}
export async function supportDownload(v, requestedID) {
  if (!v || v.id !== requestedID || !/^[a-f0-9]{32}$/.test(v.id) || v.encoding !== 'base64' ||
      !Number.isSafeInteger(v.bytes) || v.bytes < 0 || v.bytes > 128 * 1024 ||
      !/^[0-9a-f]{64}$/.test(v.sha256) || typeof v.content !== 'string') throw new Error('Malformed support-bundle reply');
  if (v.content.length > 176000 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(v.content)) throw new Error('Invalid bundle base64');
  const raw=atob(v.content);
  if (raw.length !== v.bytes) throw new Error('Support-bundle size mismatch');
  if (!globalThis.crypto?.subtle) throw new Error('SHA-256 verification is unavailable in this WebView');
  const bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
  const hash=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  if (hash !== v.sha256) throw new Error('Support-bundle SHA-256 mismatch');
  return { ...v, data:v.content, filename:`skybind-support-${v.id}.zip`,size:v.bytes};
}
export function passwordStatus(v) {
 if (!v || typeof v.configured !== 'boolean') throw new Error('Malformed crypt password status');
 const revision=v.password_revision??v.revision;
 return {...v,revision:Number.isSafeInteger(revision)&&revision>0?revision:null};
}
export function recoveryPresentation(v,status) {
 if (!v || v.password_recoverable !== false) throw new Error('Malformed crypt recovery status');
 const fields=['managed_crypt_remotes','current_password_remotes','older_password_remotes','unmanaged_crypt_remotes'];
 const populated=fields.every(k=>Number.isSafeInteger(v[k])&&v[k]>=0);
 if (populated && v.current_password_remotes+v.older_password_remotes!==v.managed_crypt_remotes) throw new Error('Inconsistent crypt provenance counts');
 return {...v,
  password_configured:Boolean(status?.configured),password_revision:status?.revision??null,
  skybind_managed_remotes:populated?v.managed_crypt_remotes:null,
  current_password_remotes:populated?v.current_password_remotes:null,
  older_password_remotes:populated?v.older_password_remotes:null,
  unmanaged_crypt_remotes:populated?v.unmanaged_crypt_remotes:null,
  guidance:String(v.guidance||v.explanation||'Recovery history is not yet tracked. Keep your passwords and rclone configuration backed up.'),
 };
}
