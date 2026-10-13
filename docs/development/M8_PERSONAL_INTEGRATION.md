# Skybind M8 — Personal Integration & Optimization

Status: implemented in source, **Android device validation pending**. M8 does **not** issue CFS1 G01–G08 approvals and does not replace an installed KernelSU module automatically.

## What changed

- The Mounts quick card exposes **Start/Stop**, **Restart**, **Keep offline**, **Cache**, and **Details**. Folder, Logs, Edit and the existing advanced action sheet are retained inside Details. These buttons delegate to the existing authenticated M0–M7 flows, not additional backends.
- Performance and offline panels are only queried when opened. An RC response from an earlier FUSE process PID is now discarded after a Restart instead of being shown on the replacement mount.
- The passive **Mounts** screen uses a 15-second minimum refresh when no panels or lifecycle work are active; open offline/performance panels retain the configured live refresh interval (default 5 seconds). Hidden WebUI screens do not poll. Log-follow disabled or paused now means no log timer at all. This optimization affects **WebUI requests only**, never mount recovery / supervisor timing.
- Remote/provider metadata is refreshed no more than once per 60 seconds during routine Mounts or Jobs polling. Explicit editor and Remotes views still refresh it on demand. Missing metadata never suppresses authoritative mount statuses.
- Existing `personal-release` compilation now runs the full JS WebUI suite and the Q08 mount action integration test, instead of only two historical UI checks. The pinned-provider and signed-release rules remain unchanged.
- `scripts/dev/integration/m8_device_smoke.sh` is a non-destructive optional Android read-only check of installed binary, canonical runtime, authenticated daemon API, mount registry and jobs. It never starts/stops a mount, exports private data or runs privileged arbitrary shell actions.

## Required device acceptance (not yet performed here)

| Scenario | Expected result | Status |
|---|---|---|
| Personal bclone ZIP build and install | verified SHA256, installer reports success, rollback ZIP retained | Pending device |
| Optional NewFuture build | same module semantics using second provider, ZIP independently verified | Pending device |
| Idle Start / Stop / Restart 5x | success with original FUSE process-identity checks | Pending device |
| Active upload during Stop/Restart | waits or refuses; original data and dirty cache preserved | Pending device |
| Mount refresh after Restart | no old-PID transfer graph, no stale writeback state | Simulated test PASS; device pending |
| Wi-Fi disconnect / reconnect | managed mount recovers within policy, manually stopped stays stopped | Pending device |
| Battery idle | hidden app & paused logs emit no WebUI poll; kernel supervisor 90-second stable checks | UI contract PASS; power measurement pending |
| Cache pressure | no automatic deletion of unverified or dirty cache; advisory only | Existing regressions PASS; device pending |
| Offline pin, airplane mode and read-only view | complete, locally verified snapshots open at explicit offline location | Pending device |
| Offline edit with changed remote | flags conflict, requires explicit separate-copy upload | Existing regressions PASS; device pending |
| Backup/restore of mounts/preferences | backed-up mounts remain disabled and credentials excluded | Existing regressions PASS; device pending |
| Ordinary unprivileged app read/write via mounted FUSE | still works (prior Q09 probe), test again after M8 build | Pending device |
| One reboot | mounts recovered per policy, private pin and edit journal recover | Pending device |

M5 same-path offline FUSE fallback remains **not implemented**. M6 uploading does not automatically replace original remote content. Encrypted credential migration remains deferred. No CFS1 independent release seal is granted.

## Optional performance baseline worksheet

Record values on a *single installed device*, before/after the same workload. Measurements should be recorded in your local notes; avoid publishing remote filenames, paths or credentials:

- Cold first mount readiness (seconds) and five warm mount cycles (seconds).
- Directory listing median duration (100, 1,000 files); 1 GB video seek-to-play latency (seconds).
- Dirty writeback flush completion after a 100 MB test upload (seconds); safe-stop refusal under active writes.
- 24-hour screen-off idle RAM (MiB) and battery percent consumed, on a stable network; compare to M7.
- Wi-Fi-loss → recovery duration (seconds), one normal disconnect and one slow/unstable reconnect.
- Local private pin bytes, public view copy bytes, VFS cache bytes, and storage pressure after offline exports.

A pass/fail regression suite does not substantiate performance claims. Report `not measured` until actual measurements exist.

## Usage

On the source checkout: `./devtoolw test` or `./devtoolw personal-release`. To run the read-only device probe **after installing the new personal ZIP**:

```sh
cd "$HOME/Code/skybind"
su -c "sh $PWD/scripts/dev/integration/m8_device_smoke.sh"
```

The smoke probe runs **no state-changing operation**, but a successful read-only probe cannot replace the manual matrix above. Keep your previous working module and do not delete offline caches/journals on rollback.
