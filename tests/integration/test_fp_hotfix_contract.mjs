import assert from 'node:assert/strict';
import fs from 'node:fs';
const source=fs.readFileSync('module/webroot/parity.js','utf8');
const {doctorPresentation}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const names=['runtime','fuse','platform','mounts','namespace','jobs','rc','remotes','storage','webui'];
const report={schema_version:1,qualification:'SOURCE_ONLY_DEVICE_NOT_ATTESTED', checks:names.map(id=>({id,status:'PASS',reason:id+'_checked',remedy:'none'}))};
const view=doctorPresentation(report);
assert.equal(view.overall,'WARN','all-source-pass must not become all-device-green');
assert.equal(view.device_qualified,false);
assert.equal(view.checks.length,11);
assert.equal(view.checks.find(x=>x.code==='runtime.integrity').summary,'Runtime integrity');
assert.equal(view.checks.find(x=>x.code==='qualification.device').status,'WARN');
let mixed=structuredClone(report);mixed.checks[0]={id:'runtime',status:'FAIL',reason:'hash_mismatch',remedy:'reinstall'};
assert.equal(doctorPresentation(mixed).overall,'FAIL');
assert.equal(doctorPresentation(mixed).checks[0].guidance,'reinstall');
for (const broken of [
 {...report,qualification:'DEVICE_QUALIFIED'},
 {...report,schema_version:2},
 {...report,checks:[]},
 {...report,checks:[...report.checks,report.checks[0]]},
 {...report,checks:report.checks.map((c,i)=>i===0?{...c,status:'PASSING'}:c)},
 {...report,checks:report.checks.map((c,i)=>i===0?{...c,id:'untrusted'}:c)},
 ])assert.throws(()=>doctorPresentation(broken));
const bridge=fs.readFileSync('module/webroot/bridge.js','utf8');
assert.match(bridge,/name==='doctor\.report'[^\n]*doctorPresentation/);
const app=fs.readFileSync('module/webroot/app.js','utf8');
assert.match(app,/renderDoctor\(result\(await query\('doctor.report'\)\)\)/);
console.log('FP contract hotfix: CLI schema, Doctor mapping and source-only qualification PASS');

assert.match(app,/Skybind tracks password generation \${generation}/);
assert.match(app,/Tracked generation \${status.revision}/);
assert.doesNotMatch(app,/Password-generation history is not yet tracked/);
