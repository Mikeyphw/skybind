import assert from 'node:assert/strict';
import fs from 'node:fs';
const html = fs.readFileSync('module/webroot/index.html', 'utf8');
const bridge = fs.readFileSync('module/webroot/bridge.js', 'utf8');
const app = fs.readFileSync('module/webroot/app.js', 'utf8');
const css = fs.readFileSync('module/webroot/style.css', 'utf8');
assert.ok(html.includes('id="toastRegion"'));
assert.ok(html.includes('Generate &amp; save ZIP') || html.includes('Generate & save ZIP'));
const doctorStart = html.indexOf('id="view-doctor"');
const bundlePosition = html.indexOf('id="bundleResult"', doctorStart);
const doctorCardsPosition = html.indexOf('id="doctorCards"', doctorStart);
assert.ok(doctorStart > 0 && bundlePosition > doctorStart && bundlePosition < doctorCardsPosition, 'bundle response must appear above checks');
assert.match(app,/showToast\('Generating support ZIP…', 'info', 0\)/);
assert.match(app,/saveSupportBundleToDownloads\(payload\.id, payload\.sha256\)/);
assert.match(app,/if \(transportName\(\) === 'embedded'\) await saveBundleAgain\(payload, saveButton\)/);
assert.match(app,/Download requested:/); // Do not falsely assert standalone persistence.
assert.match(css,/body \{ background-image: none; \}/);
assert.match(css,/\.toast-region \{/);
assert.match(css,/\.doctor-card\.FAIL \{ border-left: 3px solid var\(--ui-bad\); \}/);
// Invoke production embedded-export implementation under an inert mock manager.
const fn = bridge.match(/export async function saveSupportBundleToDownloads\(id, sha256\) \{[\s\S]*?\n\}/);
assert.ok(fn,'no rooted export adapter');
const make = new Function('selected','embeddedAvailable','EMBEDDED_BINARY','bounded',
  `let requestCounter=0; ${fn[0].replace('export async function','async function')}\nreturn saveSupportBundleToDownloads;`);
const id = 'a'.repeat(32), hash = 'b'.repeat(64);
const wanted = `/storage/emulated/0/Download/skybind-support-${id}.zip`;
let seen = '';
globalThis.ksu = {exec:(command, _, callback) => {
  seen = command;
  queueMicrotask(()=>globalThis[callback](0, wanted+'\n', ''));
}};
const exported = make('embedded',()=>true,'/data/adb/modules/skybind/system/bin/skybind',String);
assert.equal(await exported(id,hash),wanted);
assert.equal(seen,`'/data/adb/modules/skybind/system/bin/skybind' support-export '${id}' '${hash}'`);
for (const bad of ['../../etc/passwd',"ab'; reboot #",'ABC'.repeat(11)]) {
  await assert.rejects(exported(bad,hash),/Invalid support bundle export identity/);
}
await assert.rejects(exported(id,'a'.repeat(63)),/Invalid support bundle export identity/);
await assert.rejects(make('standalone',()=>true,'skybind',String)(id,hash),/unavailable/);
globalThis.ksu = {exec:(_,__,callback)=>queueMicrotask(()=>globalThis[callback](2,'','Android downloads unavailable'))};
await assert.rejects(exported(id,hash),/Android downloads unavailable/);
globalThis.ksu = {exec:(_,__,callback)=>queueMicrotask(()=>globalThis[callback](0,'/tmp/untrusted.zip',''))};
await assert.rejects(exported(id,hash),/unexpected destination/);
delete globalThis.ksu;
console.log('SB-R03 toast, layout, safe embedded support export and negative tests: PASS');
