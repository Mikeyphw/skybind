// B3 proof state is ephemeral. A changed field or stale async response drops it.
import {validFolderEndpoint} from './remote_transfer_ui.js';
const REMOTE=/^[A-Za-z][A-Za-z0-9_-]{0,62}$/;
export function validRemoteObject(value){
 if(typeof value!=='string'||value.length>512)return false;
 const i=value.indexOf(':');if(i<1||!REMOTE.test(value.slice(0,i)))return false;
 const path=value.slice(i+1);if(!path||path.startsWith('/')||path.endsWith('/')||path.includes('\\'))return false;
 return path.split('/').every(c=>c!==''&&c!=='.'&&c!=='..'&&!/[:\x00-\x1f]/.test(c));
}
export function validExchangeSubfolder(value){
 return typeof value==='string'&&value.length>0&&value.length<=384&&!value.startsWith('/')&&
 value.split('/').every(c=>c!==''&&c!=='.'&&c!=='..'&&!/[:\\\x00-\x1f]/.test(c));
}
export function makeB3Draft(kind){return {kind,remote:'',local:'',direction:'upload',endpoint:'',source:'',destination:'',proof:null,revision:0};}
export function updateB3(d,key,value){if(d[key]!==value){d[key]=value;d.revision++;d.proof=null;}return d;}
export function b3Spec(d){
 if(d.kind==='media')return ['upload','download'].includes(d.direction)&&validFolderEndpoint(d.remote)&&validExchangeSubfolder(d.local)?{direction:d.direction,remote:d.remote,local:d.local}:null;
 if(d.kind==='mkdir')return validRemoteObject(d.endpoint)?{endpoint:d.endpoint}:null;
 if(d.kind==='move'){
  if(!validRemoteObject(d.source)||!validRemoteObject(d.destination)||d.source===d.destination)return null;
  if(d.source.split(':')[0]!==d.destination.split(':')[0])return null;
  return {source:d.source,destination:d.destination};
 }
 return null;
}
const equal=(a,b)=>a&&b&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>a[k]===b[k]);
export function acceptB3(d,rev,spec,response){
 if(d.revision!==rev||!equal(b3Spec(d),spec)||!response||typeof response.proof!=='string'||!/^[a-f0-9]{64}$/.test(response.proof)||response.expires_seconds!==120)return false;
 if(!equal(spec,Object.fromEntries(Object.keys(spec).map(k=>[k,response[k]]))))return false;
 if(d.kind==='media'&&response.skip_existing!==true)return false;
 if(d.kind==='mkdir'&&response.creates_folder!==true)return false;
 if(d.kind==='move'&&(!response.file_only||!response.skip_existing||!response.source_deleted_after_success))return false;
 d.proof={revision:rev,spec:{...spec},token:response.proof};return true;
}
export function b3Ready(d){const spec=b3Spec(d);return spec&&d.proof&&d.proof.revision===d.revision&&equal(spec,d.proof.spec)?{...spec,proof:d.proof.token}:null;}
