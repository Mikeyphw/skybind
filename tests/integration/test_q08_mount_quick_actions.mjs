import assert from 'node:assert/strict';
import fs from 'node:fs';
const app = fs.readFileSync('module/webroot/app.js', 'utf8');
const html = fs.readFileSync('module/webroot/index.html', 'utf8');
const css = fs.readFileSync('module/webroot/style.css', 'utf8');
const helper = app.match(/function mountQuickState\(row, busy = false\) \{[\s\S]*?\n\}/)?.[0];
assert.ok(helper, 'backend-authoritative mount state helper exists');
const classify = new Function(`${helper}; return mountQuickState;`)();
const row = (observed, health = {}, desired = true) => ({ status:{observed,desired}, health:{state:observed,...health} });
assert.deepEqual([classify(row('RUNNING')).primaryAction,classify(row('RUNNING')).canStop,classify(row('RUNNING')).canRestart], ['stop',true,true]);
assert.deepEqual([classify(row('STOPPED')).primaryAction,classify(row('STOPPED')).canStart,classify(row('STOPPED')).canRestart], ['start',true,false]);
assert.equal(classify(row('STOPPED'),true).canStart,false,'pending RPC disables duplicate Start');
assert.equal(classify(row('RUNNING'),true).canStop,false,'pending RPC disables duplicate Stop');
assert.equal(classify(row('STOPPED', {failure_code:'PERMANENT',retryable:false})).canStart,false);
assert.equal(classify(row('STOPPED',{failure_code:'TEMP',retryable:true})).canStart,true);
assert.equal(classify(row('STARTING')).canStart,false);
assert.equal(classify(row('RETRYING')).canStart,false);
assert.equal(classify({status:{observed:'STOPPED'},health:{state:'RUNNING',process_alive:true}}).running,false,'authoritative observed state wins');
assert.equal(classify({status:{state:'running'},health:{}}).running,true);
assert.equal(classify({status:{},health:{state:'RUNNING',process_alive:true}}).running,true,'legacy fallback');
assert.equal(classify(row('STOPPED',{},true)).canStop,true,'desired-running STOPPED may still be stopped from actions');
assert.equal(classify(row('STOPPED',{},false)).canStop,false);

// Exercise the actual renderMounts function with a small inert DOM, not a clone.
class E {
  constructor(tag='div') { this.tag=tag;this.children=[];this.dataset={};this.attributes={};this.className='';this.textContent='';this.disabled=false; }
  append(...children){this.children.push(...children);}
  setAttribute(n,v){this.attributes[n]=v;}
  querySelector(){return null;}
}
const roots={mountCards:new E(),mountCount:new E()};
const document={createElement:(tag)=>new E(tag),getElementById:(id)=>roots[id]};
const clear=(node)=>{node.children=[];};
const text=(id,value)=>{roots[id].textContent=String(value)};
const paragraph=(txt,cls='')=>{const e=new E('p');e.textContent=txt;e.className=cls;return e};
const label=(txt,cls='')=>{const e=new E('span');e.textContent=txt;e.className=cls;return e};
const button=(txt,fn,cls='')=>{const e=new E('button');e.textContent=txt;e.className=cls;e.click=fn;return e};
const mountRows=(snapshot,statuses,health)=>snapshot.mounts.map(config=>({config,status:statuses.find(e=>e.name===config.name)||{},health:health.find(e=>e.name===config.name)||{}}));
const renderSrc=app.slice(app.indexOf('function renderMounts('),app.indexOf('\nasync function loadMounts()',app.indexOf('function renderMounts(')));
const render=new Function('byId','document','clear','text','paragraph','label','button','mountRows','mountStateCopy','healthClass','encryptionBadgeForEndpoint','requestMountAction','openMountFolder','openEditor','setView','openMountActions','mountPerformancePanel','mountOfflinePanel','state',`${renderSrc};return renderMounts;`)((id)=>roots[id],document,clear,text,paragraph,label,button,mountRows,(r)=>classify(r),()=>'',()=>null,()=>{},()=>{},()=>{},()=>{},()=>{},()=>{},()=>{},{mountToolsOpen:new Set(),perfOpen:new Set(),offlineOpen:new Set()});
const snapshot={mounts:[{name:'safegdrive',remote:'safegdrive:',mountpoint:'/storage/emulated/0/Rclone/SafeGDrive',vfs_profile:'custom',network_mode:'offline-allowed'}]};
function all(e){return [e,...e.children.flatMap(all)];}
render(snapshot,[{name:'safegdrive',observed:'RUNNING',desired:true}],[{name:'safegdrive',state:'RUNNING',reason:'owned_fuse_mount'}]);
let buttons=all(roots.mountCards).filter(e=>e.tag==='button');
assert.ok(buttons.some(b=>b.textContent.includes('Stop mount')&&!b.disabled),'Stop is visible and enabled');
assert.ok(buttons.some(b=>b.textContent.includes('Restart')&&!b.disabled),'Restart is visible and enabled');
assert.ok(buttons.some(b=>b.textContent.includes('Folder')),'Folder action is visible');
assert.ok(buttons.some(b=>b.textContent.includes('Logs')),'Logs action is visible');
assert.ok(buttons.some(b=>b.textContent.includes('Edit')),'Edit action is visible');
assert.equal(roots.mountCount.textContent,'1 active · 1 configured');
render(snapshot,[{name:'safegdrive',observed:'STOPPED',desired:true}],[{name:'safegdrive',state:'STOPPED',reason:'not_running'}]);
buttons=all(roots.mountCards).filter(e=>e.tag==='button');
assert.ok(buttons.some(b=>b.textContent.includes('Start mount')&&!b.disabled),'Start enabled for stopped mount');
assert.ok(buttons.some(b=>b.textContent.includes('Restart')&&b.disabled),'Restart disabled for stopped mount');
assert.equal(roots.mountCount.textContent,'0 active · 1 configured');
assert.ok(!all(roots.mountCards).some(e=>e.className.includes('mount-health-note')),'normal STOPPED is not an error');

for (const id of ['mountConfirmBackdrop','mountConfirmTitle','mountConfirmDetail','mountConfirmCancel','mountConfirmApply','mountFolderBackdrop','mountFolderPath','mountFolderCopy','mountCount']) {
  assert.match(html,new RegExp(`id="${id}"`), `missing mounted control ${id}`);
}
assert.match(app,/const startProof = action === 'start' \? result\(await preview\('mount\.start\.preview'/,'start preview-proof retained');
assert.match(app,/startOperation\(`mount\.\$\{action\}`/,'RPC lifecycle preserved');
assert.match(app,/if \(state\.mountBusyNames\.has\(name\)\) return/,'double-click guard');
assert.match(app,/requestMountAction\('stop',name\)/,'advanced Stop also confirms');
assert.match(app,/requestMountAction\('restart',name\)/,'advanced Restart also confirms');
assert.match(css,/#view-mounts \.mount-quick-primary/,'button layout present');
assert.doesNotMatch(app,/import .*mounts-ui\.js/,'no hidden new asset requiring HTTP allowlist modification');
console.log('SB-Q08 mount-action state, DOM rendering, and safety contract: PASS');
