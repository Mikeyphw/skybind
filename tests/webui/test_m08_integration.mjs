import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const root=new URL('../../module/webroot/',import.meta.url);
const app=readFileSync(new URL('app.js',root),'utf8');
const model=await import('data:text/javascript;base64,'+Buffer.from(readFileSync(new URL('model.js',root))).toString('base64'));

test('M8 adaptive WebUI refresh reduces idle authenticated requests without delaying active controls',()=>{
 const delay=model.m8RefreshDelay;
 assert.equal(delay({view:'mounts',configuredSeconds:5,mountAttention:false}),15000);
 assert.equal(delay({view:'mounts',configuredSeconds:5,mountAttention:true}),5000);
 assert.equal(delay({view:'mounts',configuredSeconds:30,mountAttention:false}),30000);
 assert.equal(delay({view:'mounts',configuredSeconds:30,mountAttention:true}),30000);
 assert.equal(delay({view:'logs',configuredSeconds:5,logsFollowing:false}),null);
 assert.equal(delay({view:'logs',configuredSeconds:5,logsFollowing:true}),5000);
 assert.equal(delay({view:'runtime',configuredSeconds:5}),5000);
 assert.equal(delay({view:'more'}),null);
 assert.equal(delay({view:'mounts',configuredSeconds:-1}),15000);
 assert.ok(app.includes('if(delay===null)return;'), 'paused logs must not schedule wakeups');
 assert.ok(app.includes('document.visibilityState !== \'visible\''),'invisible views must not poll');
});

test('M8 metrics sampled for old PID never leak into restarted mount', async()=>{
 const start=app.indexOf('async function pollPerformance(');
 const end=app.indexOf('\nfunction mountPerformancePanel(',start);
 assert.ok(start>0&&end>start);
 const fragment=app.slice(start,end);
 let resolveQuery;
 const response=new Promise(resolve=>{resolveQuery=resolve;});
 const state={perfOpen:new Set(['photos']),activeView:'mounts',perfPending:new Set(),perfEpoch:1,
   perfPid:new Map([['photos',11]]),perfCache:new Map(),perfHistory:new Map()};
 const fakeDocument={visibilityState:'visible'};
 let renderCalls=0;
 const poll=new Function('state','document','query','result','performanceSample','boundedPerformanceHistory','updatePerformancePanel',`${fragment};return pollPerformance;`)(
  state,fakeDocument,()=>response,el=>el,()=>({status:'available',speed:5}),()=>[{speed:5}],()=>{renderCalls++}
 );
 const pending=poll('photos',true,11);
 assert.ok(state.perfPending.has('photos'));
 state.perfPid.set('photos',12);
 resolveQuery({state:'available'});
 await pending;
 assert.equal(state.perfCache.size,0,'stale PID sample must not be published');
 assert.equal(state.perfHistory.size,0,'old transfer rate must not contaminate new graph');
 assert.equal(renderCalls,0,'stale async request must not re-render the new child');
 assert.equal(state.perfPending.size,0,'pending flag must clear after stale request');
});

test('M8 integrated quick controls reuse existing safety mechanisms',()=>{
 for(const v of ['↓ Keep offline','▤ Cache','⋯ Details', 'mount-m8-utilities'])assert.ok(app.includes(v),v);
 assert.ok(app.includes("card.querySelector('.offline-toggle')?.click()"));
 assert.ok(app.includes("card.querySelector('.perf-toggle')?.click()"));
 for(const op of ['rc.metrics','offline.pin','offline.write.upload-copy','backup.preview','backup.restore'])assert.ok(app.includes(op),op);
 assert.ok(app.includes('requestMountAction(mainAction, name, main)'));
 assert.ok(app.includes("requestMountAction('restart', name, restart)"));
 assert.ok(app.includes("Number(pid||0)!==Number(state.perfPid.get(name)||0)"));
 assert.ok(app.includes('refreshRemoteDetailsIfDue'));
 assert.ok(app.includes('state.remoteDetailsUpdatedAt=Date.now()'));
});
