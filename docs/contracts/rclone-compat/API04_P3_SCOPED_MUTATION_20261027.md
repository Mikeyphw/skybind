# Skybind API-04 P3 — separately approved scoped mount mutations

**Source-only candidate; not active by default; never a blanket Android privilege escalation.**

P3 modifies only the Skybind producer. Existing P1 read-only policy and P2 read-only socket `\0skybind-api04-bkx-query-v1` stay **query-only**. This phase adds a new independently enabled abstract endpoint `\0skybind-api04-mutations-v1`.

## Requirements and explicit activation

- Root-owned P1 canonical policy `/data/adb/skybind/api04-bkx-policy-v1.json` remains mandatory; the approved BKX UID/package/signer/SELinux pin and mount allowlist are reused exactly.
- An **additional** root-owned mode 0600 file `/data/adb/skybind/api04-mutation-policy-v1.json` must contain strict JSON:

```json
{
  "schema":"skybind-api04-mutation-policy-v1",
  "explicitly_enabled":true,
  "operations":["mount.start","mount.stop"],
  "mount_names":["YOUR_EXISTING_APPROVED_MOUNT"]
}
```

All mount names must be a subset of the P1 allowlist; enabling mutations does **not** authorize global mounts, namespaces or arbitrary commands. Operator must separately create root-owned 0700 directory `/data/adb/skybind/api04-mutations` before startup. **No script in this artifact creates state or enables modules automatically.**

- Start the existing root operator gateway with its unchanged, independently pinned PackageManager authority flags plus `--enable-mutations`; omit the flag for original P2 query-only behavior. Do not use P3 on a production device until Android/SELinux acceptance passes.

## Wire protocol (mutations endpoint only)

The caller uses the same live kernel peer UID and authenticated installed-package identity as P2. Each request is a single bounded JSON envelope followed by socket write-half close.

Preview request:

```json
{"version":1,"action":"preview","request_id":"client-42","operation":"mount.start","name":"YOUR_EXISTING_APPROVED_MOUNT"}
```

Preview returns `preview_id` (server generated), `preview_sha256`, `expires_unix` (90 seconds), operation and mount. **It never returns Skybind daemon's native proof or unrestricted mount config**. For `mount.start`, the private daemon provides a single-use native mount preview token. For `mount.stop`, the private daemon verifies mount status and the operator approves the exact name and operation; no native stop-specific preview proof exists yet.

Root operator inspection (the root-only command reads **private** state and reveals no native proof):

```bash
skybind-api04-approve --preview-id PREVIEW_ID --inspect
```

Then an explicit single-record root operator approval, naming the same operation and mount:

```bash
skybind-api04-approve --preview-id PREVIEW_ID --preview-sha256 EXACT_DIGEST \
  --operation mount.start --mount YOUR_EXISTING_APPROVED_MOUNT --approve-exact
```

Mutation execution request:

```json
{"version":1,"action":"execute","preview_id":"PREVIEW_ID"}
```

Lost-reply status request, which never reexecutes a mutation:

```json
{"version":1,"action":"status","preview_id":"PREVIEW_ID"}
```

Status returns only the caller-authorized mutation's bounded stage: `previewed`, `approved`, `expired`, `submitted`, `unknown`, `running`, `succeeded`, `failed`, `cancelled`, or `interrupted`. Denials are intentionally generic. Client cannot call `approve`, specify a root path or supply a native proof.

## Durable execution and failure contract

A private 0600 record is reserved as `submitted` and fsynced before calling API-02. The request ID sent to the daemon is a separate server-generated ID (`api04_` + private preview ID). Native journal operations are already guarded against duplicate mutation requests. When execution succeeds or fails, the result state is persisted; if the reply or store commit is lost, `submitted/unknown` can be reconciled by querying the **same single** journal request ID. The API **never** retries automatically after submission. Individual preview records are kept as replay tombstones; to prevent unbounded client storage, the directory is capped at 2048 files and must be retired by trusted root maintenance after review, not auto-deleted while replay evidence is needed.

## Explicitly unqualified

Android ELF cross-build, local Go tests and race tests do not prove SELinux access to abstract socket, actual signer identity, kernel peer lifecycle, real mounts, recovery after power loss, native FUSE behavior, or production readiness. Do not describe P3 as device-qualified before API05 evidence. Stop-preview config-revision binding remains a hardening follow-up.
