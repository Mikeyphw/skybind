# Skybind

Android root-integrated FUSE and cloud filesystem management, using an immutable
installed rclone-family executable and a native Go daemon. The existing WebUI
has been ported directly with narrow Skybind backend and authentication adapters.

**Current source state:** `SB-C01` through `SB-C06` implemented with Devtool
source/fault validation. This does **not** mean an Android release is approved.
Provider release pins are incomplete; G01/G02 remain BLOCKED, G03–G08 require
independent device/UX evidence, and final seal `SB-CFS1` is NOT ISSUED.

## Roadmap, evidence, and application

- [Active consolidated Devtool campaign](docs/roadmap/SKYBIND_DEVTOOL_ROADMAP.md)
- [Machine-readable artifact/obligation index](docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json)
- [Complete feature specification](docs/roadmap/SKYBIND_FEATURE_SPEC.md)
- [C06 real-device matrix](docs/qualification/SB-C06_DEVICE_MATRIX.md)
- [Reproducible candidate packaging](docs/release/SB-C06_RELEASE_PROCESS.md)

Apply each supplied `.devtool-overlay.zip` with Devtool. Its preflight and
validation script run automatically, with atomic rollback on failures. No manual
post-apply `go test`/`go vet` commands are required. The device-probe and
release-candidate workflows are Devtool targets, but their mere presence does
not qualify real hardware or a publication artifact.

The CLI/daemon and module ID are `skybind`; upstream runtime executable remains
`rclone`, canonical root-owned state is `/data/adb/skybind`. No dynamic
installed-runtime system or migration logic is implemented.

## Independent milestone gate package

SB-CG1 installs six read-only gate evaluators (SB-G03..G08), original-promise ledgers, and Devtool-owned validation. The definitions are source implemented, not promoted. SB-G01/G02 remain blocked and SB-CFS1 is not issued. No unsigned or user-supplied evidence can qualify Android devices or releases.
