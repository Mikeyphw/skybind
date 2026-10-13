import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const text = readFileSync(new URL('../../module/webroot/model.js', import.meta.url),'utf8');
const model = await import('data:text/javascript;base64,'+Buffer.from(text).toString('base64'));
const now=1750000000000;
const make=(x={})=>({performance:{source:'authenticated_rclone_rc_aggregate',state:'available',sampled_at_unix_ms:now,total_speed_bytes_per_second:32.5,transferred_bytes:1024,rc_errors:0,vfs_cache_bytes:2048,vfs_cache_files:2,...x},writeback:{source:'authenticated_vfs_stats',state:'busy',uploads_queued:2,uploads_in_progress:1,errored_files:0}});
let p=model.performanceSample(make(),now);
assert.equal(p.speed,32.5);assert.equal(p.queued,2);assert.equal(p.active,1);assert.equal(p.cacheBytes,2048);
assert.equal(model.performanceSample(make({total_speed_bytes_per_second:null}),now).speed,null);
assert.equal(model.performanceSample(make({total_speed_bytes_per_second:-4}),now).speed,null);
assert.equal(model.performanceSample(make({sampled_at_unix_ms:now-60000}),now).status,'unavailable');
assert.equal(model.performanceSample(make({source:'untrusted'}),now).status,'unavailable');
assert.equal(model.performanceSample({performance:{...make().performance},writeback:{state:'idle',source:'bad'}},now).queued,null);
let hist=[];for(let i=0;i<100;i++){hist=model.boundedPerformanceHistory(hist,{sampledAt:i,speed:i});}
assert.equal(hist.length,60);assert.equal(hist[0].at,40);assert.equal(hist.at(-1).speed,99);
hist=model.boundedPerformanceHistory(hist,{sampledAt:99,speed:101});assert.equal(hist.length,60);assert.equal(hist.at(-1).speed,101);
hist=model.boundedPerformanceHistory(hist,{sampledAt:100,speed:null});assert.equal(hist.length,60);
console.log('M2 WebUI model tests PASS');
