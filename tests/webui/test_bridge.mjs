// SB-C05 source-level protocol seam test. Not an Android WebView qualification.
import assert from 'node:assert/strict';
const bridge=await import('../../module/webroot/bridge.js');
globalThis.document={cookie:'skybind_csrf=fixture-csrf'};
let captured=[];
globalThis.fetch=async (url,init={})=>{
 captured.push({url,init});
 const reply=(status,data)=>({ok:status>=200&&status<300,status,json:async()=>data});
 if(url==='/api/v1/transport')return reply(200,{schema_version:1,transport:'standalone',typed_backend:true});
 if(url==='/api/v1/capabilities')return reply(200,{schema_version:1,request_id:'webui-caps',ok:true,result:{schema_version:1,protocol:{min:1,max:1},operations:[]}});
 if(url==='/api/v1/query/ui.settings')return reply(200,{schema_version:1,request_id:init.headers['X-Skybind-Request-ID'],ok:true,result:{settings:{}}});
 throw new Error('Unexpected typed route '+url);
};
assert.equal(await bridge.selectTransport(),'standalone');
assert.deepEqual((await bridge.capabilities()).operations,[]);
const res=await bridge.query('ui.settings',{});
assert.deepEqual(res.response.result,{settings:{}});
const call=captured.at(-1);
assert.equal(call.url,'/api/v1/query/ui.settings');
assert.equal(call.init.headers['X-Skybind-CSRF'],'fixture-csrf');
assert.ok(call.init.headers['X-Skybind-Request-ID']);
assert.throws(()=>bridge.requestEnvelope('system.exit','shell',{}));
assert.throws(()=>bridge.requestEnvelope('bad/evil','query',{}));
console.log('SB-C05 typed standalone bridge source contract PASS (not WebView/device evidence)');
