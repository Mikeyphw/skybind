# Skybind

Android rooted FUSE/cloud filesystem management project. Its new implementation
is planned as the **Skybind Devtool Overlay Campaign**.

**Status: bootstrap planning only.** This commit supplies the original feature
specification, 45-overlay dependency roadmap, five Devtool targets, executable
planning-contract tests, and repository wrapper declarations. It does **not**
contain the implemented app, copied WebUI, a real Android qualification,
completed gates, or a release seal.

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
