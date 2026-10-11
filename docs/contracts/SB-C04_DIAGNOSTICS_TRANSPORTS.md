# SB-C04 — Diagnostic and Transport Source Contract

Scope: original SB-O25–SB-O28, bundled without weaker trust boundaries.

* 57-operation catalog unchanged; four Doctor/logging operations become registered only when their private backing services are available.
* Doctor reports PASS/INFO/WARN/FAIL, including explicit unverified device information; no green response from missing proof.
* Logs are size-bounded private JSONL records with level/source filtering and prepublication sanitization; no unredacted sensitive data is intentionally accepted.
* Support ZIPs contain only bounded sanitized generated summaries, hashed manifest entries and opaque random IDs; the `doctor.bundle.read` operation validates ownership, size, and entry hashes.
* Standalone HTTP binds only 127.0.0.1 on ephemeral port. Bootstrap tokens are short-lived and single-use, session cookies are HttpOnly Strict, CSRF and exact loopback Host/Origin are enforced, and static assets remain absent until C05.
* Embedded bridge uses the fixed native `skybind webui bridge --request-base64` entrypoint, decodes a bounded typed operation and calls the same authenticated daemon RPC client as standalone and CLI. No untrusted shell interpolation.
* Devtool runs complete affected tests, platform-aware race validation, Go vet, Android arm64 cross-build, API/campaign contract and negative-path tests automatically at apply time.

Source-level checks do not establish Android manager integration, browser visual parity, end-to-end device qualification, SB-G06 promotion, or any release seal.
