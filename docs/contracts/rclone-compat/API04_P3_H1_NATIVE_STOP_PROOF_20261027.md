# API04 P3-H1 — native revision-bound mount.stop proof

Source candidate, not Android device qualified. Changes Skybind only.

## Private API02 operations

- `mount.stop.preview` (class `preview`): takes exactly `{ "name": "<configured mount>" }`, requires a desired and verified running, owned FUSE mount, returns short-lived, private single-use `proof`, mount name, observed state, registry revision, and `device_qualified:false`. The proof binds the exact registry revision, full mount config, desired state, owned process (PID, start ticks, executable, original FUSE mount ID), and observed mount identity.
- `mount.stop.guarded` (class `run`): takes exactly `{ "name": "<configured mount>", "proof": "<64-hex token>" }`; rechecks the binding under the lifecycle engine mutex, consumes the proof, then uses the existing owner-aware writeback, FUSE unmount and pidfd stop path. Forged, stale, replayed or mismatched proofs do not initiate a detach.
- Existing root-only `mount.stop` is unchanged for trusted internal and root clients. The operation catalog now has 59 typed operations (57 historical plus these two).

## API04 mutation gateway

- Public operation continues to be `mount.stop` (operator-approved and named-mount scoped), but preview dispatches to private `mount.stop.preview`, and execution dispatches ONLY to private `mount.stop.guarded`.
- The native proof is held in private 0600 approval state and never returned through the cross-UID gateway. Approval still binds operation, mount, preview digest and caller incarnation. Native proof is consumed once; durable reservation remains before side effects and lost-reply status is read-only.
- Both start and stop preview decoders now extract the 64-character lowercase hexadecimal proof from a strict JSON object while accepting native descriptive fields such as `mount`, `revision`, and `runtime_verified`.
- P2 query endpoint, P1 policy and original R1 gateway remain untouched. Mutations stay operator-disabled by default.

## Security and qualification

Host tests include stale registry changes without mount restart, replaced PID/fuse identity, forged/replayed proof, stopped mount, operator approval and uncertain delivery. Host Go suites, race, vet and Android ARM64 cross-builds pass in the reconstructed source.

Still OPEN: actual Devtool receipt and installed Android package/signature, kernel peer, SELinux, mount, reboot/power-loss and lifecycle tests. No service is automatically started by this overlay.
