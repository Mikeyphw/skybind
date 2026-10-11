# Skybind build-time runtime inputs (SB-O04 + SB-O05)

This implementation creates a deterministic **runtime-input ZIP**, NOT a complete or
installable Android application. Later overlays add root-manager hooks, CLI/daemon
installation, WebUI, and device qualification.

## Required immutable upstream inputs

1. Obtain the *official* `NewFuture/rclone-fuse3-magisk` release archive named
   `magisk-rclone_arm64-v8a.zip` corresponding to the pinned tag. Verify its
   source and SHA-256 through a separately trusted release/artifact channel.
2. Commit that complete SHA-256 into `scripts/dev/runtime/source.lock.json`.
   The provided lock leaves it `null` **intentionally**: no upstream bytes have
   been independently acquired and authenticated in this deliverable.
3. To build bclone, pin a full source commit, official Android NDK revision and
   exact `go version`; obtain a clean checkout at that commit. The NDK compiler
   currently requires the official host-specific `linux-x86_64` or `darwin-x86_64`
   toolchain. Termux's native Android-hosted NDK path is pending separate
   qualification. No prebuilt arbitrary override is permitted.

```sh
python3 scripts/dev/runtime/skybind_runtime.py package \
  --provider newfuture \
  --newfuture-archive /trusted/magisk-rclone_arm64-v8a.zip \
  --output build/runtime/skybind-newfuture-arm64.zip

python3 scripts/dev/runtime/skybind_runtime.py package \
  --provider bclone \
  --newfuture-archive /trusted/magisk-rclone_arm64-v8a.zip \
  --bclone-checkout /pinned/bclone-checkout \
  --ndk /verified/android-ndk \
  --output build/runtime/skybind-bclone-arm64.zip

python3 scripts/dev/runtime/skybind_runtime.py verify \
  build/runtime/skybind-newfuture-arm64.zip
```

`newfuture` and `bclone` packaging always uses the **same unchanged NewFuture
fusermount3 and libfuse bytes**. Provider choice is only at build time.
No runtime download, selection, modification or switching logic is installed.

The source tests generate tiny artificial AArch64 ELF fixtures. Those are
**not trusted upstream executables**, and the test coverage is not build
reproducibility of actual provider releases. SB-G01 must remain BLOCKED until
both real, pinned provider outputs and independent clean-build evidence exist.
