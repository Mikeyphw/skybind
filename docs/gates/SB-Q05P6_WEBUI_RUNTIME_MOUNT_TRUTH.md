# SB-Q05P6 — Runtime view and mount-wizard readiness truth

Scope: **WebUI-only source repair** against SB-Q05P5 V2 on `main`. The Android runtime executable, bclone, NewFuture prebuilt, FUSE helper, config, daemon, module scripts, pinning, and release gates are unchanged.

## Evidence / reproduced regressions

1. Runtime page raised `ReferenceError: detailBlock is not defined` after rendering the runtime authority notice. The source called an undefined DOM builder. The repair introduces a bounded, DOM-only detail renderer and a smoke test that executes it.
2. Native `provider.status` reports `{ready,remote_count,config_path_redacted}`. The previous wizard instead queried non-existent `binary_ready`, `fuse_helper_ready`, and `config_ready` booleans, which JavaScript interpreted as false and displayed as three false errors. We now query `runtime.status` separately and use its verified runtime/helper data; remote recognition is based on native provider readiness and the enumerated configured remotes. Unknown observations remain unknown.
3. The backend `config.preview` approves a configuration transaction; it does **not** independently prove a FUSE mount or Android app visibility. The preview now labels its authority precisely, and enabled mounts require observed runtime/helper integrity and recognized remote configuration. Saving disabled drafts remains possible without claiming mount readiness.

## Safety

- No generic shell execution, permission broadening, integrity bypass, lock modification, or release-gate promotion.
- Neither successful remote browsing nor local backend readiness proves cross-app storage visibility.
- Initial physical test should use an empty dedicated mountpoint, a nonessential remote, and autostart disabled.
- Not a sealed or device-qualified release; G01–G08 `BLOCKED`, final seal `NOT_ISSUED`.
