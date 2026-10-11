# SB-FP02 — CLI / crypt / local jobs original-feature parity

This feature overlay restores user-facing commands and original non-migration behaviors. The executable still uses the static, pinned rclone bundled within Skybind. No raw shell, runtime switching or migration operations are introduced.

## Fixed, typed CLI workflows

Use `skybind mount list|status NAME|preview NAME|start --stdin|stop NAME|restart NAME`, `skybind jobs list|status|preview --stdin|apply --stdin`, `skybind job preview NAME|run --stdin`, `skybind remotes list|browse REMOTE:PATH`, `skybind crypt password status|password set --stdin|recovery|preview --stdin|create --stdin`, `skybind doctor report|bundle`, `skybind namespace inspect NAME|preview --stdin|apply --stdin`, `skybind runtime status`, `skybind platform status`, `skybind rc metrics NAME`.

JSON request bodies for privileged proof operations are read from bounded stdin; no generic shell or free-form rclone flags are accepted. Password input requires a protected stdin pipe. Generic `skybind rpc` / `skybind operation` CLI invocations of `provider.crypt.password.set` are explicitly rejected to prevent process-argument/history disclosure. The server retains its typed operation for authenticated, private WebUI transport.

## Jobs

Absolute local paths inside Android media trees are accepted alongside `remote:path`, with explicit rejection of `/data/adb`, system/private paths, traversal components, nested local source/destination, unsafe symlinks, and control bytes. Both copy and check are nondestructive; sync still requires a fresh proof. Local paths elsewhere on Android need separately qualified root/path ownership before allowance.

## Crypt

The root-private `crypt-metadata-v1.json` tracks password revisions, managed crypt names, backing endpoints and creation times without secrets. Recovery distinguishes current and older password generations from unmanaged remotes. Existing encrypted remotes without a proven record remain untracked; no old-generation count is invented. A new managed crypt requires a tracked password generation, and preview proofs bind both config and password-generation state. Config and provenance publication are two distinct atomic-file operations; any partial failure is reported instead of passing.

## Evidence boundary

Devtool applies this artifact with targeted tests, two umasks, host-supported race checks, Android arm64 crossbuild, and release-negative verification. No real cloud-transfer, Android physical-device, visual parity or official-provider gate passes are claimed. G01–G08 BLOCKED; final seal NOT_ISSUED.
