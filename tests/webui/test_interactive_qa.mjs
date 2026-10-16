import assert from 'node:assert/strict';
import {evaluateNavigation,evaluateReconnect,evaluateCancelled} from '../../module/webroot/interactive_qa.js';
let v={page:true,title:true,preview_control:true,confirm_control:true,
 trusted_navigation:true,trusted_preview:true,proof_present:true,
 confirm_enabled:true,preview_is_readonly_kind:true};
assert.equal(evaluateNavigation(v),'PASS');
assert.equal(evaluateNavigation({...v,trusted_preview:false}),'BLOCKED');
assert.equal(evaluateNavigation({...v,preview_is_readonly_kind:false}),'BLOCKED');
const before={doc:'old',run_id:'a'.repeat(32),state:'RUNNING',event:{latest:8,cursor:7,progress:2}};
const after={doc:'new',run_id:'a'.repeat(32),state:'COMPLETED',event:{latest:9,cursor:8,gap:false,degraded:false,reset:false}};
assert.equal(evaluateReconnect(before,after),'PASS');
assert.equal(evaluateReconnect(before,{...after,doc:'old'}),'BLOCKED');
assert.equal(evaluateReconnect(before,{...after,event:{...after.event,gap:true}}),'BLOCKED');
assert.equal(evaluateCancelled({trusted_cancel:true,cancel_event:true,final_state:'CANCELLED',independently_owned:false}),'BLOCKED');
console.log('V9 interactive QA pure-function tests passed');
