import { test } from 'node:test';
import assert from 'node:assert/strict';
import {safeOfflineRelativePath,offlineSnapshotSummary,activeOfflineTask} from '../../module/webroot/model.js';
test('offline paths reject traversal, escapes and absolute paths',()=>{
  for(const value of ['', '/', '../a','a/../b','a//b','a/./b','a\\b','a:b','a\nb']) assert.equal(safeOfflineRelativePath(value),null);
  assert.equal(safeOfflineRelativePath('Documents/report.pdf'),'Documents/report.pdf');
});
test('offline count and referenced content bytes deduplicate hashes without implying verification',()=>{
  const h='a'.repeat(64), b='b'.repeat(64);
  const data={quota_bytes:8589934592,pins:[{mount:'m1',path:'a',size:4,sha256:h},{mount:'m1',path:'b',size:4,sha256:h},{mount:'m2',path:'c',size:10,sha256:b}]};
  assert.deepEqual(offlineSnapshotSummary(data,'m1'),{pins:data.pins.slice(0,2),count:2,referencedBytes:14,quotaBytes:8589934592});
});
test('active task wins over last completed task',()=>{
  assert.equal(activeOfflineTask([{mount:'a',state:'SUCCEEDED'},{mount:'b',state:'RUNNING',id:'x'}],'a').id,'x');
});
