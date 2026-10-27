# Skybind API-04 P1 — BKX cross-UID scoped admission core (source-only)

## Trust boundary

This change prepares a **denied-by-default, source-only** read-only query admission layer. It does **not** start an Android Binder service or cross-UID socket, install policy, dispatch a daemon request, grant root to BKX, enable API-04 mutation, or replace the existing R1 read-only consumer gateway or API-02 root-only feature CLI. Source tests do not establish Android SELinux feasibility.

- The operator provisions a root-owned, regular, hardlink-free 0600 policy at `/data/adb/skybind/api04-bkx-policy-v1.json` under a root-owned 0700 private parent. `LoadCanonical()` enforces root-only access. Neither BKX nor the future socket request may select a policy file.
- Policy schema is `skybind-api04-bkx-readonly-policy-v1`, with `explicitly_enabled=true`, exact `com.mikeyphw.bkx.android` Android UID, SHA-256 of installed APK certificate DER, current process SELinux label, finite operation list and explicit mount-name allowlist. Empty, duplicate, unknown, non-query and unapproved values are rejected, including duplicate nested JSON keys.
- The only allowed operations in this initial implementation are `mount.status` and `mount.health`, with a **single exact mount name** in arguments. `mount.list`, arbitrary operation history, namespace inspection, previews, mutations and client-specified commands are denied. There is no global status fallback.
- `NewGuard` requires independent PackageManager attestation and `/proc` identity evidence. `Guard.Prepare` compares kernel SO_PEERCRED UID/PID/GID to the policy, invokes the existing R1 `AndroidVerifier`, validates versioned and duplicate-key-free API-02 JSON, checks the operation **and object scope**, and produces a typed `feature.execute` query for later privileged dispatch.
- `Guard.Prepare` does not run or schedule that query. The returned request/identity is **not** a permission token and never crosses a security boundary. Only an operator-owned process may later connect the authenticated and scoped request to the private API-02 daemon.
- A changed BKX signer, UID, SELinux context or mount scope requires explicit policy reapproval; no TOFU and no consumer-authored policy.

## Expected policy shape (documentation only; NOT provisioned by overlay)

```json
{
  "schema": "skybind-api04-bkx-readonly-policy-v1",
  "explicitly_enabled": true,
  "bkx": {
    "package": "com.mikeyphw.bkx.android",
    "uid": 11091,
    "cert_sha256": "<64 lowercase hexadecimal characters from independently verified installed APK>",
    "selinux_context": "u:r:untrusted_app:s0:cNNN,cMMM"
  },
  "operations": ["mount.status", "mount.health"],
  "mount_names": ["operatorApprovedMount"]
}
```

UID and label values are **illustrative**, not permission recommendations. Do not deploy an unverified example pin or grant broad visibility.

## Roadmap gates / non-merge window

- **API-04 P1 (this change):** operator policy parser, exact mount-scoped admission, existing AndroidVerifier reuse, regression tests; offline source gate only.
- **API-04 P2 (NOT delivered):** independent trusted PackageManager runtime linkage; explicit root-owned service activation; peer credentials and SELinux access, bounded wire protocol/response, safe shutdown; a BKX app client/opt-in with no bundled-rclone behavior regression; per-peer concurrency and request replay; device verification. No R1 grant reuse for mutation.
- **API-04 P3 (NOT delivered):** typed per-operation approval, preview/proof, mutation request-id reconciliation, per-resource permissions and audit; do not enable until real device acceptance.
- **API-05 (NOT delivered):** device installation, signer identity and SELinux, end-to-end read-only probes, failure/rollback and cross-consumer qualification. It cannot be merged into P1 absent device evidence.

No APK is built, installed or granted permission by P1. No installed root module state is modified.
