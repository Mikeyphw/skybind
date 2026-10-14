// Regression: successfully refreshed Home should dismiss transient stale manager
// backend errors, but not hide active compatibility failures.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const app=fs.readFileSync('module/webroot/app.js','utf8');
const definition=app.match(/function clearTransientBackendNotice\(\) \{[\s\S]*?\n\}/);
assert.ok(definition,'missing transient notice helper');
for(const path of [
  "async function refreshView(view){try{await loadViewData(view,{announce:true});if(view==='home')clearTransientBackendNotice();",
  "await loadViewData(state.activeView,{announce:false});if(state.activeView==='home')clearTransientBackendNotice();",
  "try{await loadViewData(view,{announce:true});if(view==='home')clearTransientBackendNotice();"
])assert.ok(app.includes(path),'missing successful refresh clearing path: '+path);
function trial(message, {error=true,hidden=false,shouldClear=false}={}) {
  const node={hidden,textContent:message,classList:{contains:key=>key==='error'&&error}};
  let clears=0;
  vm.runInNewContext(definition[0]+'\nclearTransientBackendNotice();',{
    compatibility:node,
    hideNotice:x=>{assert.equal(x,node);clears++;node.hidden=true;node.textContent='';}
  });
  assert.equal(clears,shouldClear?1:0,message);
}
trial('Backend request failed: Embedded backend exited with status -1',{shouldClear:true});
trial('Refresh failed: Embedded backend exited with status -1',{shouldClear:true});
trial('Backend unavailable or incompatible: missing API',{shouldClear:false});
trial('Authentication required',{shouldClear:false});
trial('Backend request failed: a', {error:false,shouldClear:false});
trial('Backend request failed: a', {hidden:true,shouldClear:false});
console.log('WebUI transient Home error recovery regression: PASS');
