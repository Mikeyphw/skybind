// Phase B2: unmounted remote-to-remote copy/check UI state; proofs never persist.
const VALID_REMOTE = /^[A-Za-z0-9._-]{1,100}$/;
const VALID_COMPONENT = /^[^\\\x00-\x1f:]+$/;
export const KINDS = Object.freeze(['copy', 'check']);
export function validFolderEndpoint(value) {
  if (typeof value !== 'string' || value.length > 2048) return false;
  const at = value.indexOf(':');
  if (at < 1 || !VALID_REMOTE.test(value.slice(0, at))) return false;
  const path = value.slice(at + 1);
  if (!path || path.startsWith('/') || path.endsWith('/') || path.includes('\\')) return false;
  const parts = path.split('/');
  return parts.length <= 32 && parts.every(p => p && p !== '.' && p !== '..' && VALID_COMPONENT.test(p));
}
export function transferSpec(state) {
  const spec = {kind: state.kind, source: state.source, destination: state.destination};
  if (!KINDS.includes(spec.kind) || !validFolderEndpoint(spec.source) || !validFolderEndpoint(spec.destination) || spec.source === spec.destination) return null;
  const [sr,sp] = [spec.source.slice(0,spec.source.indexOf(':')),spec.source.slice(spec.source.indexOf(':')+1)];
  const [dr,dp] = [spec.destination.slice(0,spec.destination.indexOf(':')),spec.destination.slice(spec.destination.indexOf(':')+1)];
  if (sr===dr && (sp.startsWith(dp+'/') || dp.startsWith(sp+'/'))) return null;
  return spec;
}
const same = (a,b) => a && b && a.kind===b.kind && a.source===b.source && a.destination===b.destination;
export function createTransferDraft() {return {kind:'copy',source:'',destination:'',proof:null,revision:0,busy:false};}
export function changeTransfer(draft,field,value) {
  if (!['kind','source','destination'].includes(field)) throw new Error('Unsupported transfer field');
  if (draft[field] !== value) {draft[field]=value;draft.revision++;draft.proof=null;}
  return draft;
}
export function acceptTransferPreview(draft,revision,spec,result) {
  if (revision !== draft.revision || !same(transferSpec(draft),spec) ||
      !result || typeof result.proof !== 'string' || result.proof.length < 8 || result.proof.length > 1024 ||
      !same(result,spec) || result.expires_seconds !== 120 ||
      result.copies_skip_existing !== (spec.kind === 'copy') || result.read_only !== (spec.kind === 'check')) return false;
  draft.proof = {value:result.proof, spec:{...spec},revision};
  return true;
}
export function readyTransfer(draft) {
  const spec=transferSpec(draft);
  return spec && draft.proof && draft.proof.revision===draft.revision && same(spec,draft.proof.spec) && !draft.busy
    ? {...spec,proof:draft.proof.value} : null;
}
export function redactRunId(run) {return typeof run === 'string' && /^[a-f0-9]{32}$/.test(run) ? run : null;}
