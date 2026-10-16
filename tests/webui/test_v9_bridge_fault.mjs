import assert from 'node:assert/strict';
import {selectTransport,transportName,query,armQaReadOnlyEventsFault,
        disarmQaReadOnlyEventsFault,qaBridgeCounters} from '../../module/webroot/bridge.js';
let nativeQueries=0;
globalThis.ksu={exec(command, options, callbackName) {
  if (command.includes('--capabilities')) {
    globalThis[callbackName](0,JSON.stringify({schema_version:1,protocol:{min:1,max:1},operations:[]}), '');
    return;
  }
  nativeQueries++;
  const match=command.match(/--request-base64 ([A-Za-z0-9_-]+)/);
  assert.ok(match);
  const request=JSON.parse(Buffer.from(match[1],'base64url').toString('utf8'));
  globalThis[callbackName](0,JSON.stringify({schema_version:1,request_id:request.request_id,ok:true,
    result:{latest_cursor:0,next_cursor:0,events:[]}}),'');
}};
assert.equal(await selectTransport(),'embedded');
assert.equal(transportName(),'embedded');
const before=qaBridgeCounters();
assert.equal(armQaReadOnlyEventsFault(),true);
assert.equal(armQaReadOnlyEventsFault(),false);
await assert.rejects(query('operation.events',{cursor:0,limit:1,wait_ms:0}),/QA injected one-shot/);
assert.equal(qaBridgeCounters().pending_readonly_fault,0);
assert.equal(qaBridgeCounters().injected_faults,before.injected_faults+1);
assert.equal(qaBridgeCounters().mutation_dispatches,before.mutation_dispatches);
assert.equal(nativeQueries,0,'one synthetic failure never reaches native');
const next=await query('operation.events',{cursor:0,limit:1,wait_ms:0});
assert.equal(next.response.ok,true);
assert.equal(nativeQueries,1,'the recovery query reaches native exactly once');
assert.equal(armQaReadOnlyEventsFault(),true);
disarmQaReadOnlyEventsFault();
assert.equal(qaBridgeCounters().pending_readonly_fault,0);
await query('operation.events',{cursor:0,limit:1,wait_ms:0});
assert.equal(nativeQueries,2,'disarmed failure cannot leak to a later query');
console.log('V9 read-only fault injection: one shot, restored, no mutating dispatch');
