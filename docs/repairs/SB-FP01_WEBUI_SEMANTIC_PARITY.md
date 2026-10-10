# SB-FP01 — WebUI semantic parity (source repair)

- Preserve the original Rclone Nexus-derived `index.html`, `style.css`, icon, navigation and modal structure unchanged.
- Adapt only known typed responses: `runtime.status` uses verified manifest fields, while FUSE usability and Android device qualification remain unproven; `platform.status` reports root-manager detection without treating it as bridge/identity attestation.
- `doctor.bundle` translates the native ID to the historical UI field; `doctor.bundle.read` verifies ID, size and SHA-256 **before** permitting a browser download. Corrupt, oversized, unverified and cross-ID bundles fail closed. The existing native 128-KiB RPC boundary remains intact.
- Crypt password/recovery UIs no longer manufacture generation `1` or zero managed remotes when Skybind does not possess provenance. Detailed generation inventory is an SB-FP02 backend obligation.
- Standalone WebUI idle timeout is bound to private, validated `ui.settings` state; it is re-read per authenticated request, clamps to 30–3600 seconds, and expires even when the setting is shortened. Private-state read errors prevent authentication.
- Negative tests in the Devtool overlay cover tampering, missing browser SHA, protocol response errors, unsigned device facts, expired sessions, and unsupported settings. No raw secret logging or arbitrary RC/exec proxy added.
- Source validation **does not** establish Chromium/WebView screenshot parity, physical Android mount visibility, provider authenticity, or final release qualification. G01–G08 and the final seal remain blocked.
