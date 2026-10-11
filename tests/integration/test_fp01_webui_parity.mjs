import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createHash,webcrypto} from 'node:crypto';
const text=fs.readFileSync('module/webroot/parity.js','utf8');
const p=await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64'));
const digest='a'.repeat(64);
const raw=Buffer.from('SKYBIND FIXTURE SUPPORT ZIP BYTES');
const hash=createHash('sha256').update(raw).digest('hex');
const id='a'.repeat(32);
Object.defineProperty(globalThis,'crypto',{configurable:true,value:webcrypto});
const r=p.runtimePresentation({ready:true,provider:'newfuture',reason:'hashes verified',provenance_available:true,provenance_valid:true,runtime_sha256:digest,fuse_helper_sha256:digest});
assert.equal(r.operational,true);assert.equal(r.runtime_provider,'newfuture');assert.equal(r.fuse_helper_ready,true);
assert.equal(r.mode,'static');assert.equal(r.source,'skybind-bundled-static');
assert.match(r.issues[0],/not independently qualified/);
assert.equal(p.runtimePresentation({ready:false,provider:'',reason:'tampered'}).operational,false);
assert.throws(()=>p.runtimePresentation({ready:'yes',provider:'newfuture'}));
const platform=p.platformPresentation({root:true,confirmed:true,module_present:true,manager:'KernelSU',candidates:[]});
assert.equal(platform.root_manager.name,'KernelSU');assert.equal(platform.root_manager.compatible,true);
assert.equal(platform.root_manager.capabilities.embedded_webui,false);
assert.equal(platform.integrity.ok,false);
assert.equal(p.platformPresentation({root:false,confirmed:true,module_present:true,manager:'Magisk'}).root_manager.compatible,false);
assert.throws(()=>p.platformPresentation({manager:'Magisk'}));
const meta=p.bundleMetadata({id,bytes:raw.length,sha256:hash});assert.equal(meta.bundle_id,id);
const encoded=raw.toString('base64');
const verified=await p.supportDownload({id,bytes:raw.length,sha256:hash,content:encoded,encoding:'base64'},id);
assert.equal(verified.data,encoded);assert.equal(verified.filename,`skybind-support-${id}.zip`);
for(const changed of [
 {id:'b'.repeat(32)}, {bytes:raw.length+1}, {sha256:digest}, {encoding:'hex'}, {content:'%NOTBASE64%'}]) {
 await assert.rejects(p.supportDownload({id,bytes:raw.length,sha256:hash,content:encoded,encoding:'base64',...changed},id));
}
await assert.rejects(p.supportDownload({id,bytes:raw.length,sha256:hash,content:encoded,encoding:'base64'},'c'.repeat(32)));
assert.throws(()=>p.bundleMetadata({id:'../bad',bytes:1,sha256:hash}));
const orig=globalThis.crypto;Object.defineProperty(globalThis,'crypto',{configurable:true,value:undefined});
await assert.rejects(p.supportDownload({id,bytes:raw.length,sha256:hash,content:encoded,encoding:'base64'},id),/SHA-256/);
Object.defineProperty(globalThis,'crypto',{configurable:true,value:orig});
const status=p.passwordStatus({configured:true});assert.equal(status.revision,null);
const recovery=p.recoveryPresentation({password_recoverable:false,explanation:'No plaintext recovery'},status);
assert.equal(recovery.password_configured,true);assert.equal(recovery.password_revision,null);
assert.equal(recovery.skybind_managed_remotes,null);assert.equal(recovery.older_password_remotes,null);
assert.throws(()=>p.recoveryPresentation({password_recoverable:true},status));
const app=fs.readFileSync('module/webroot/app.js','utf8');
assert.match(app,/skybind_managed_remotes\?\?'Unknown'/);
assert.doesNotMatch(app,/configured as generation \$\{status\.revision\|\|1\}/);
const bridge=fs.readFileSync('module/webroot/bridge.js','utf8');
for(const name of ['runtime.status','platform.status','doctor.bundle','doctor.bundle.read','provider.crypt.recovery.status']) {
 assert.ok(bridge.includes(`name==='${name}'`),`${name} adapter absent`);
}
console.log('SB-FP01 semantic adapters, tampering/unknown-evidence tests: PASS');
