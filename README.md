# Skybind

Android rooted FUSE/cloud filesystem management project. Its new implementation
is planned as the **Skybind Devtool Overlay Campaign**.

**Status: greenfield foundation implemented (SB-O01+O02 and SB-O03).**
The product contract is frozen, the original WebUI assets are retained as an
immutable test reference (not yet shipped as a Skybind UI), and the native Go
CLI/path/atomic-file foundation now compiles and is covered by source tests.
The 45-overlay roadmap remains normative. The daemon, mounts, Android app
visibility, runtime binaries, actual WebUI integration, device qualification,
milestone gates, and release seal remain **unimplemented/not attested**.

## Roadmap

- [Devtool overlay campaign](docs/roadmap/SKYBIND_DEVTOOL_ROADMAP.md)
- [Machine-readable overlay inventory](docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json)
- [Normative feature specification](docs/roadmap/SKYBIND_FEATURE_SPEC.md)

The upstream `rclone` binary remains `rclone`; product CLI `skybind`, daemon
`skybindd`, module ID `skybind`, and state path `/data/adb/skybind/`.
No installed dynamic-runtime functionality or migration/legacy UX is included.
The original WebUI must be copied with practical visual and interaction parity.

## Bootstrap checks (NOT implementation/release proof)

```bash
python3 -m unittest discover -s tests -p 'test_bootstrap.py' -v
devtool -r . targets --json
devtool -r . workflows --json
devtool -r . plan bootstrap --target skybind_release --json
devtool -r . preflight --target skybind_release --workflow bootstrap --json
devtool -r . --target skybind_release invoke bootstrap
```

After installing your matching Devtool, run `devtool wrapper init` to generate
`./devtoolw`, then `./devtoolw bootstrap`.

Every future SB-Oxx overlay adds its own real tests and execution jobs; each
SB-Gxx gate must verify actual evidence, and SB-FS1 must verify device release
qualification. No gate is represented as passed by these bootstrap checks.

## Implemented foundation checks (source qualification only)

```bash
python3 -m unittest discover -s tests/contracts -p 'test_*.py' -v
bash scripts/devtool/check_native.sh
# Via Devtool, after installing the matching local Devtool version:
devtool -r . --target skybind_release invoke foundation
devtool -r . --target skybind invoke native
```

`SB-O01+O02` imports byte-frozen `tests/fixtures/webui-reference/raw/` assets.
These are **reference fixtures only**, including excluded historical UI controls;
they must not be served to end users. Visual screenshots and device evidence are
intentionally not fabricated. `SB-O03` does not start a daemon or mount filesystems.
