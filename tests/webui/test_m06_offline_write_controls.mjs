import { test } from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const app=readFileSync(new URL('../../module/webroot/app.js',import.meta.url),'utf8');
test('M6 UI has separate-copy semantics with second confirmation and no overwrite shortcut',()=>{
  for(const name of ['offline.write.list','offline.write.draft','offline.write.stage','offline.write.check','offline.write.upload-copy'])
    assert.ok(app.includes(name),`missing ${name}`);
  assert.ok(app.includes("state.offlineConfirm===key"));
  assert.ok(app.includes('acknowledge:true'));
  assert.ok(app.includes('Original cloud files remain untouched'));
  assert.ok(!app.includes("'offline.write.overwrite'"));
});
