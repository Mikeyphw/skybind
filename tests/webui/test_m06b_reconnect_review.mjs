import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const app=readFileSync(new URL('../../module/webroot/app.js',import.meta.url),'utf8');
test('M6B reconnect review is opt-in and separate from confirmed upload',()=>{
 for(const operation of ['offline.write.review','offline.write.reconcile','offline.write.auto-review'])
   assert.ok(app.includes(operation),`missing ${operation}`);
 assert.ok(app.includes('No uploads will be started'));
 assert.ok(app.includes('Enable automatic reconnect review'));
 assert.ok(app.includes('Disable automatic review'));
 assert.ok(app.includes('metadata-only'));
 assert.ok(app.includes('CONFIRM upload SEPARATE COPY'));
 assert.ok(!app.includes('offline.write.overwrite'));
});
