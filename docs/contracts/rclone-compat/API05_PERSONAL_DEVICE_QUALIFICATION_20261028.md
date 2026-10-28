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
