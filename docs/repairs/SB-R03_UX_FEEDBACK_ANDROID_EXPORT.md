# SB-R03 — WebUI feedback, flatter surfaces, Android support-bundle save

This is incorporated into the original SB-R03 FUSE helper PATH repair overlay,
not a second sequential overlay. Apply only to the unmodified SB-R03 source baseline.

## Product changes

- Persistent inline outcomes plus non-blocking, dismissible toast/banner
  feedback for actions, errors and support ZIP progress; skip noisy periodic
  health refreshes. Accessibility status and keyboard focus indicators remain.
- Simplify both light and dark WebUI surfaces: plain opaque backgrounds, no
  backdrop blur or radial gradient; remove secondary card outlines while
  retaining field/focus, dangerous status, and selected control distinctions.
- Move generated support output immediately under the Doctor action toolbar.
- On embedded KernelSU WebUI, Generate & save ZIP verifies the bounded ZIP
  through the existing typed `doctor.bundle.read` transport, then invokes the
  narrowly scoped root-only `skybind support-export <id> <sha256>`. It saves to
  `/storage/emulated/0/Download/skybind-support-<id>.zip`. A retry button stays
  visible. Unlike a browser `blob:` download, success is only displayed after
  the command returns the expected path. No shell interpolation of paths or
  credentials, private archive mutation, arbitrary destinations, or overwrites.
- In standalone browsers, explicitly use a Download ZIP button (direct user
  gesture), avoid promising the browser completed the download, and preserve
  the SHA-256/size/ID validation before rendering it.
- The ZIP itself remains sanitized, owned, and size/hash validated. The export
  revalidates it and refuses to overwrite an unrelated file or symlink.

## Validation

- `go test -count=1 ./...`
- `go vet ./...`
- `node tests/integration/test_r03_feedback_support_export.mjs`
- Existing WebUI parity, diagnostic truth and mount flow suites.
- Syntax checks on app.js and bridge.js, no weakening of G01–G08 gates.

## Required Android device check

1. Build and install a new module candidate. Source tests do **not** modify the
   installed module or prove WebView/Android Downloads behavior.
2. Open KernelSU Skybind WebUI > More > Doctor > Generate & save ZIP. Watch the
   toast, inline Save to Downloads status, and filesystem file in Android
   Downloads. Tap Save again to verify idempotent behavior.
3. Confirm no scrolling is needed to find the generated ZIP controls; check
   mounts/actions and dark/light styles, including screen readers and focus.
4. Test the mount (SB-R03 FUSE PATH) on device; safety/release seals remain
   unqualified and unchanged until evidenced.

## Safe failure behavior

If `/storage/emulated/0/Download` is inaccessible, the copy command fails and
shows an error plus retry action; the private original remains in
`/data/adb/skybind/support`. No alternate uncontrolled root path is guessed.
