# Skybind normative product contract — SB-O01

Canonical naming and retained features derive from the active roadmap and its 57-operation inventory. `docs/contracts/identity.json` and `typed-operations.json` are machine-checkable assertions, not implementations.

- Root module identity: `skybind`; read-only module: `/data/adb/modules/skybind`; persistent private state: `/data/adb/skybind`.
- CLI: `skybind`; daemon: `skybindd`; primary upstream engine binary: `system/bin/rclone`; helper: `system/vendor/bin/fusermount3`.
- Provider choice (NewFuture versus bclone) happens at **build time only**; exactly one runtime binary is included in any installed package.
- Frontend must retain original DOM/style/interaction behavior with brand-only and approved historical control exclusions. `tests/fixtures/webui-reference/raw/` is byte-pinned and never shipped.
- App starts neither device qualification nor release seal automatically. Source-level tests cannot attest mounted app visibility.
- Every typed operation has an implementing overlay and consumer in `typed-operations.json`; a controller cannot expose arbitrary commands.
- Product-state crash recovery and Devtool transactional recovery remain in scope.

## Evidence policy

UI screenshots and real-device tests are **pending**; they are not generated or claimed by SB-O01. Security threat coverage is documented in `docs/architecture/THREAT_MODEL.md` and promoted only with actual proof.
