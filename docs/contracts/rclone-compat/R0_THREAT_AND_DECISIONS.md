# R0 threat model and R1 decision log

**Threats:** untrusted app impersonating BKX via package name; malicious `--config` / `--rclone-config` / `--rc` or environment tokens; remote prefix confusion and traversal; local pathname escape; sync/delete beyond grant; duplicate mutation after process restart; arbitrary provider-specific backend flags; credential disclosure by stderr; Restic lock and prune corruption; changed authorization during long streams; unauthenticated HTTP/loopback control endpoint.

**Baseline:** deny every invocation until executable broker, identity/grants, source/runtime provenance and input-validation layers exist. Mock classification is not actual authorization. Request-handling must bind UID, signing certificate and SELinux process facts from OS, not from request fields. A user grant should expire/revoke and restrict each remote, operation, subtree, and where needed file type/byte quotas.

**Open R1 choices:** determine module-owned Unix socket vs bound Android RootService in both Termux/ordinary BKX UID; SELinux context and fd-passing viability; credential-free remote listing for BKX `ConfiguredRemoteNames`; structured error-to-exit mapping; exact process cancellation and transfer lifetime. Do not expose an RC API or unrestricted root-service method.

**Risk hold:** destructive `sync`, `deletefile`, `copyto` overwrite and `serve restic --stdio` must not be enabled by a read-only compatibility negotiation. R5 test matrix must cover init, backup, check, restore, prune, locks, abrupt termination, concurrent clients and content hashes across providers.
