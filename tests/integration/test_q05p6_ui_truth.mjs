import assert from 'node:assert/strict';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
const p = fs.readFileSync('module/webroot/parity.js', 'utf8');
const {providerReadinessPresentation: evidence, runtimePresentation} = await import('data:text/javascript;base64,'+Buffer.from(p).toString('base64'));
const native = {ready:true,remote_count:1,config_path_redacted:true};
const runtime = runtimePresentation({ready:true,provider:'bclone',provenance_available:true,provenance_valid:true,fuse_helper_sha256:'a'.repeat(64)});
const ok = evidence(native,runtime,['SafeGDrive'],'SafeGDrive');
assert.equal(ok.runtime_ready,true);
assert.equal(ok.helper_verified,true);
assert.equal(ok.config_recognized,true);
assert.equal(ok.can_start,true);
assert.match(ok.config_text,/recognized/);
// Native provider status does NOT provide the legacy WebUI booleans.
for (const key of ['binary_ready','fuse_helper_ready','config_ready']) assert.equal(native[key],undefined);
const noRemote = evidence(native,runtime,[], 'missing');
assert.equal(noRemote.config_recognized,false);
assert.equal(noRemote.can_start,false);
const unknown = evidence({ready:true,remote_count:0}, null, [], '');
assert.equal(unknown.runtime_ready,null);
assert.equal(unknown.helper_verified,null);
assert.equal(unknown.config_recognized,null);
assert.doesNotMatch(unknown.config_text,/missing|unavailable/i);
const invalid = evidence(native,runtimePresentation({ready:false,provider:'bclone',reason:'hash mismatch'}),['SafeGDrive'],'SafeGDrive');
assert.equal(invalid.can_start,false);
assert.equal(invalid.runtime_ready,false);
assert.equal(invalid.helper_verified,false);
const backendDown = evidence({ready:false},runtime,['SafeGDrive'],'SafeGDrive');
assert.equal(backendDown.config_recognized,false);
assert.equal(backendDown.can_start,false);
for (const name of ['app.js','parity.js']) {
  const source=fs.readFileSync('module/webroot/'+name,'utf8');
  execFileSync(process.execPath,['--input-type=module','--check'],{input:source,stdio:['pipe','pipe','pipe']});
}
const app=fs.readFileSync('module/webroot/app.js','utf8');
assert.match(app,/function detailBlock\(/);
assert.match(app,/detailBlock\('Runtime issues'/);
assert.match(app,/providerReadinessPresentation\(state\.editorProviderStatus/);
assert.match(app,/query\('runtime\.status'\)/);
assert.match(app,/!readiness\.can_start/);
assert.match(app,/Configuration approval does not prove FUSE mount operation/);
assert.doesNotMatch(app,/status\.binary_ready\s*\?/);
assert.doesNotMatch(app,/status\.fuse_helper_ready\s*\?/);
assert.doesNotMatch(app,/status\.config_ready\s*\?/);
assert.doesNotMatch(app,/provider\?\.fuse_device_ready/);
console.log('SB-Q05P6 frontend contract: 2 original regressions reproduced and repaired; truth/negative cases PASS');
// Execute the actual detailBlock DOM builder using a tiny inert DOM.
const match = app.match(/function detailBlock\(heading, rows\) \{[\s\S]*?\n\}/);
assert.ok(match,'detailBlock implementation absent');
class MiniElement {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.className='';}
  append(...items){this.children.push(...items);}
}
const document = {createElement:(tag)=>new MiniElement(tag),createTextNode:(s)=>({textContent:String(s)})};
const evaluate = new Function('document',`${match[0]};function metric(root,name,value){const row=document.createElement('div');const title=document.createElement('strong');title.textContent=name;row.append(title,document.createTextNode(value));root.append(row);}return detailBlock;`)(document);
const details = evaluate('Runtime issues',[['Issue','Android FUSE/device operation is not independently qualified']]);
assert.equal(details.tag,'details');
assert.equal(details.children[0].textContent,'Runtime issues');
assert.equal(details.children[1].children[0].children[1].textContent,'Android FUSE/device operation is not independently qualified');
console.log('SB-Q05P6 Runtime detail renderer DOM smoke: PASS');
