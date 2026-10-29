# Skybind API-05 — personal-device qualification kit

**Scope:** One personally managed rooted Android phone; no fleet management, enterprise certificates, enrollment, external CI service, or BKX implementation. This adds **diagnostics only**, not another permanently running daemon or a gateway activation feature.

**Source baseline:** pushed Skybind API-04 P3-H1 R3 `f50c35b46ad78e310661e16fe0bb645bd3ca7cea`.

## What the kit can actually establish

The local Python 3 standard-library collector (`scripts/devtool/api05_personal_device.py`) reads Android root availability and SELinux mode, root-owned API-04 policy file ownership/mode/link count, and the kernel's `SO_PEERCRED` identity of two separate live gateways. When explicitly requested **and** given an independently pinned approved consumer UID, it sends invalid JSON as the *unapproved Termux UID* and requires the expected denial (`api04_peer_denied` / `api04_mutation_peer_denied`). No valid mutation request is issued. It optionally snapshots a mount from **Termux's namespace**, which cannot prove the daemon's namespace or mount owner. It can compare two boot IDs for observed reboot evidence. Evidence files use mode `0600`.

The evaluator produces a four-gate JSON report with `BLOCKED`, `NOT_RUN` and at most `PARTIAL` for local observations. **It deliberately cannot issue a final PASS** from self-reported or read-only evidence. Independent on-device positive identity and lifecycle proof is still necessary; an intentionally disabled gateway yields `NOT_RUN`, not a synthetic success.

## Quick, non-mutating first run (Termux)

From `~/Code/skybind`, with `python3`, `su` and Android system tools available:

```sh
E="$HOME/.local/state/skybind/api05-personal"
mkdir -p "$E"
python3 scripts/devtool/api05_personal_device.py capture \
  --stage baseline --output "$E/baseline.json"
python3 scripts/devtool/api05_personal_device.py evaluate \
  --output "$E/report.json" "$E/baseline.json"
cat "$E/report.json"
```

The script **does not enable or start** either API-04 gateway. The mutation endpoint remains opt-in. A non-running gateway is correctly marked untested.

If **you** have already activated both endpoints under the existing root-operator workflow and independently know the pinned consumer UID (from your private root-owned policy), capture a safe negative-authentication attempt:

```sh
python3 scripts/devtool/api05_personal_device.py capture \
  --stage gateway --output "$E/gateway.json" \
  --approved-consumer-uid YOUR_INDEPENDENTLY_VERIFIED_UID \
  --probe-unapproved-client
python3 scripts/devtool/api05_personal_device.py evaluate \
  --output "$E/report.json" "$E/baseline.json" "$E/gateway.json"
```

Never use Termux's own UID as the approved UID, and never read a UID from a client-supplied request. Socket probes are explicitly opt-in, send no operation, and can be denied by SELinux before userspace; capture that as blocked/untested evidence, not a pass. Do not disable SELinux to make the probe succeed.

For reboot observation only, optionally add the **same** `--mountpoint /absolute/path` to baseline and after-reboot captures, then physically reboot using your normal device controls and run:

```sh
python3 scripts/devtool/api05_personal_device.py capture \
  --stage after_reboot --output "$E/reboot.json" --mountpoint /absolute/path
python3 scripts/devtool/api05_personal_device.py evaluate \
  --output "$E/report.json" "$E/baseline.json" "$E/reboot.json"
```

A boot ID change and mountinfo observation are **partial evidence only**, not proof of successful crash recovery or authorized mount state.

## Four-gate acceptance checklist

| Gate | Source implemented | Must still be demonstrated on the phone |
|---|---|---|
| 05-1 Security | Root policy metadata, Enforcing mode and kernel peer checks | Independently pinned installed APK signature, PackageManager responder, UID, SELinux identity, impersonation and PID-reuse negatives |
| 05-2 Gateway | Root server-UID check; optional unapproved-client denial on query **and** mutation endpoints | Actual authorized package query, separate root-approved preview/proof/execute, denied stale proof/replay/other mount |
| 05-3 Lifecycle | Private boot/mount snapshots | Disposable named FUSE mount start/stop, crash, reboot, lost reply, ownership and journal reconciliation in daemon namespace |
| 05-4 Closure | Explicit blocked/pending report | Go supported-host race receipt, successful Termux Devtool transaction, results of 05-1..05-3 and a human-reviewed final device evidence assessment |

**Privacy:** Evidence is stored under your Termux home and is never uploaded. The collector never serializes installed APK contents, policy JSON, secrets, filesystem listings, or full mountinfo lines. The evidence still contains a boot ID and file metadata; treat it as private. Do not publish evidence bundles indiscriminately.

**No implicit release seal.** The kit is implemented when its source tests and Devtool transaction pass. API-05 itself remains *not qualified* until independent installed-device evidence is reviewed. The default mutation gateway remains disabled.

## H1: Termux SELinux probe and query-only staging (2026-10-28)

- Termux's unprivileged `/system/bin/getenforce` can be denied despite Android running in Enforcing mode. The collector now attempts an exact `su -c /system/bin/getenforce` fallback and records `environment.selinux_source` as `termux`, `root` or `unavailable`. It accepts only exact Android SELinux mode words. No `setenforce` or policy modification occurs.
- API-05 05-1 security is still **at most PARTIAL** when root, Enforcing, secure parent and secure query policy are observed. The mutation policy may legitimately be `NOT_CONFIGURED` while the mutation socket is disabled; the report separately records `mutation_policy_state` and `mutation_readiness_blockers`.
- An **existing but insecure** mutation policy, a mutation socket reachable without secure mutation policy, or any query socket reachable without secure query policy **blocks** 05-1. Unprovisioned query policy also blocks query readiness.
- Query-only negative-authentication evidence can make 05-2 PARTIAL without a mutation socket; it never supplies authorization-positive evidence or a final seal. No live gateway is started and no policy is provisioned by this patch.
- The tested personal-phone case was `Enforcing` via `su`, root-owned 0700 parent, and two absent policies. After H1 that remains 05-1 BLOCKED until the read-only policy is explicitly and correctly provisioned. Do not create a mutation policy merely to make an evidence report appear green.

After application, recapture your baseline with the existing `capture` and `evaluate` commands. If query policy remains missing, security stays BLOCKED for the correct reason. The new `selinux_source: root` should be present. All four real-device gates and supported-host `-race` remain independently open.


## H2: Personal core qualification independent of unused API-04 (2026-10-29)

**Scope correction:** BKX's installed Android app currently has no API-04 client. Do not provision `/data/adb/skybind/api04-bkx-policy-v1.json`, start either API-04 listener, or alter consumer code solely to make Skybind's native daemon/FUSE/recovery qualification appear ready. This is not a claim that API-04 has passed device acceptance.

The collector's `capture` subcommand remains read-only and compatible with existing v1 evidence files. The `evaluate` subcommand accepts **independent explicit scopes**:

| `--scope` | Meaning | 05-1 security | 05-2 gateway |
|---|---|---|---|
| `core` (**default**) | Skybind root/private-state/SELinux evidence and native lifecycle only | Requires root, Android, Enforcing, secure `/data/adb/skybind` parent, and no insecure/active API-04 surfaces | `DEFERRED_NOT_USED` if both API-04 endpoints are inactive |
| `api04-query` | Opt-in future read-only cross-UID consumer qualification | Additionally requires secure root-owned query policy | At most PARTIAL from approved-peer-negative checks; positive installed-app checks remain open |
| `api04-full` | Opt-in mutation plus query qualification | Additionally requires both secure root-owned query and mutation policies | Both authorized query and mutation proof/replay device tests remain open |

Any **present insecure policy**, **non-root API-04 socket**, **socket without its secure policy**, or **unexpectedly active or visibility-denied API-04 socket in core mode** blocks 05-1. No scope can turn passive evidence into a final PASS: `core_qualification_complete=false`, `device_qualification_complete=false` and `05-4-final-seal=BLOCKED` remain authoritative. The core lifecycle gate is at most PARTIAL from passive reboot/mount observations made in Termux's namespace, not proof of daemon-owned FUSE state. A true core acceptance requires separately reviewed root-daemon, native runtime, FUSE lifecycle and recovery receipts, plus supported-host Go race evidence.

Evaluate an existing H1 capture **without running a new collection or provisioning BKX policy**:

```sh
E="$HOME/.local/state/skybind/api05-personal"
python3 scripts/devtool/api05_personal_device.py evaluate \
  --scope core --output "$E/report-core.json" "$E/baseline-h1.json"
cat "$E/report-core.json"
```

The explicit API-04 flows remain available for later use:

```sh
python3 scripts/devtool/api05_personal_device.py evaluate \
  --scope api04-query --output "$E/report-api04-query.json" "$E/baseline-h1.json"
```

Never use the core `DEFERRED_NOT_USED` status to claim API-04 security, app identity, cross-UID execution or operator-approved mutations have passed. Re-evaluate under the appropriate explicit scope if a consumer is later integrated.

Socket visibility is also bounded: newer captures distinguish `absent` (ENOENT/ECONNREFUSED) from `permission_denied` (EACCES/EPERM) and `unknown_error`. The latter two block security rather than masquerade as a disabled listener; legacy captures lack this field and cannot independently prove absence.
