# SB-R02 — Durable operation truth and original WebUI contract repair

Scope: SB-A03, SB-A04, SB-A05 and SB-A06. The original HTML/CSS/icon are unchanged. The sole new ES module `flow.js` is deliberately added to the standalone static-file allowlist, and its security boundary is tested.

- Mutating `run`, `cancel` and `reconcile` requests reserve an owned durable journal record before invoking the handler. If reservation fails, the operation does not execute. The record's terminal result is journaled before a successful RPC response is returned. Request ID lookup supports the original Activity progress UI. No false asynchronous cancellation is advertised for synchronous, non-interruptible operations.
- A `job.run` RPC returns a durable `RUNNING` job claim, **not completion**. Journal entries link to the actual job run ID and record `job_claimed_not_finished`. Jobs and Activity use the backend's persisted runs, bytes, speed, ETA, failure reason and final state. Cancellation in Activity is offered only for a real owned RUNNING job ID.
- App visibility requires read-only `namespace.inspect`, an explicit user choice from complete, unprotected, app-only namespaces that are not visible at the exact target, and a fresh backend-native proof. Selection is never inferred from an alias. Backend rechecks topology, source, and scope when applying.
- Cache clear/forget use the native preview `proof`, mount identity and preview file count, confirmed by the user before `cache.<action>` with `proof`. Changed trees and reused proofs remain rejected by the native cache manager.
- Automated Devtool validation covers Go unit/adversarial tests, Node model and production contract tests, both umasks, supported-host race checks, vet, Android/arm64 cross-build, bootstrap compatibility, and a read-only blocked release audit. This is **not** a browser/WebView or physical Android qualification.

There is no dynamic runtime implementation or migration work in this repair.
