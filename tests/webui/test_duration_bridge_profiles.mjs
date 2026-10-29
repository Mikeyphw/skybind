import assert from 'node:assert/strict';
import { seconds } from '../../module/webroot/bridge.js';
import { localMountIssues } from '../../module/webroot/model.js';

// Regress the actual native time.Duration.String() profile spellings: emitted
// by vfs.profiles and accepted by the wizard before embedded conversion.
const profiles = [
  ['streaming', '24h0m0s', '10m0s', '1m0s', 86400, 600, 60],
  ['balanced', '12h0m0s', '5m0s', '1m0s', 43200, 300, 60],
  ['documents', '4h0m0s', '2m0s', '1m0s', 14400, 120, 60],
  ['minimal', '1h0m0s', '1m0s', '2m0s', 3600, 60, 120],
  ['read-only', '6h0m0s', '5m0s', '1m0s', 21600, 300, 60],
  ['offline-ready', '168h0m0s', '1h0m0s', '0s', 604800, 3600, 0],
  ['offline', '168h0m0s', '1h0m0s', '0s', 604800, 3600, 0],
];
for (const [profile, age, dir, poll, wantAge, wantDir, wantPoll] of profiles) {
  assert.deepEqual([seconds(age), seconds(dir), seconds(poll)], [wantAge, wantDir, wantPoll], profile);
  const issues = localMountIssues({
    name: `test-${profile}`, remote: 'testremote:path', mountpoint: `/mnt/test-${profile}`,
    vfs_cache_max_age: age, dir_cache_time: dir, poll_interval: poll,
    boot_settle: '10s', network_settle: '5s',
  });
  assert.equal(issues.filter(issue => issue.code === 'invalid_duration').length, 0, profile);
}
// A reported installed preset may retain a different age from the source
// defaults. The exact user-observed value must still be valid.
assert.equal(seconds('120h0m0s'), 432000);
for (const [input, expected] of Object.entries({
  '': 0, off: 0, '0': 0, '0s': 0, '5d': 432000, '7d': 604800,
  '1w': 604800, '1h30m0s': 5400, '1.5h': 5400, '1500ms': 1,
  '1m500ms': 60, '2500000µs': 2, '1000000000ns': 1,
  '0.5s': 0, '30s': 30, '15m': 900, '24h': 86400,
})) assert.equal(seconds(input), expected, input);
assert.equal(seconds(0), 0);
assert.equal(seconds(300), 300);
for (const bad of [
  '1x', '3mnope', '1hbanana', 'foo', '-5s', '1e3h', '1d2h',
  '1h 30m', '1m-1s', 'Infinityh', 'NaNm', '.5h',
  '99999999999999999999999h', '99999999999999999999w',
  Number.NaN, Infinity, -10, Number.MAX_SAFE_INTEGER + 1,
]) assert.throws(() => seconds(bad), /Unsupported duration/, String(bad));
console.log('PASS_UI01_EMBEDDED_DURATION_BRIDGE_7_PROFILES_AND_NEGATIVES');
