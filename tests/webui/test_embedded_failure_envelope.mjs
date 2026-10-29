import assert from 'node:assert/strict';
import * as bridge from '../../module/webroot/bridge.js';

const calls = [];
let mode = 'typed_failure';
const fail = (id) => ({
  schema_version: 1, request_id: id, ok: false,
  error: { code: 'mount_status_unavailable', category: 'runtime', stage: 'query',
    message: 'mount_status_unavailable', retryable: false }
});
globalThis.ksu = { exec(command, _options, callback) {
  calls.push(command);
  let errno = 0;
  let body;
  if (command.includes(' --capabilities')) {
    body = {schema_version:1,protocol:{min:1,max:1},operations:[]};
  } else {
    const token = command.match(/--request-base64 ([A-Za-z0-9_-]+)/)?.[1];
    assert.ok(token, 'only the fixed typed bridge command is used');
    const request = JSON.parse(Buffer.from(token,'base64url').toString('utf8'));
    assert.equal(request.operation.class, 'query');
    assert.equal(request.operation.name, 'mount.list');
    if (mode === 'typed_failure') {
      errno = 1;
      body = fail(request.request_id);
    } else if (mode === 'mismatched_failure') {
      errno = 1;
      body = fail('different-request-id');
    } else if (mode === 'garbled_failure') {
      errno = 1;
      body = 'invalid-json';
    } else if (mode === 'success') {
      body = {schema_version:1,request_id:request.request_id,ok:true,result:['safegdrive']};
    } else if (mode === 'mismatched_success') {
      body = {schema_version:1,request_id:'wrong-id',ok:true,result:['safegdrive']};
    } else if (mode === 'false_exit_zero') {
      body = fail(request.request_id);
    }
  }
  queueMicrotask(() => globalThis[callback](errno,
    typeof body === 'string' ? body : JSON.stringify(body),
    ''));
}};

assert.equal(await bridge.selectTransport(), 'embedded');
for (const bad of ['typed_failure', 'false_exit_zero']) {
  mode = bad;
  const result = await bridge.query('mount.list');
  assert.equal(result.response.ok, false);
  assert.equal(result.response.error.code, 'mount_status_unavailable');
  assert.equal(result.response.error.category, 'runtime');
}
mode = 'success';
assert.deepEqual((await bridge.query('mount.list')).response.result, ['safegdrive']);
for (const bad of ['mismatched_failure', 'garbled_failure', 'mismatched_success']) {
  mode = bad;
  await assert.rejects(bridge.query('mount.list'), /Embedded backend/);
}
assert.equal(bridge.qaBridgeCounters().mutation_dispatches, 0);
assert.ok(calls.every(c => c.startsWith("'/data/adb/modules/skybind/system/bin/skybind' webui bridge --")));
console.log('PASS_WEBUI_EMBEDDED_FAILURE_ENVELOPE_PRESERVED_WITH_IDENTITY_GATES');
