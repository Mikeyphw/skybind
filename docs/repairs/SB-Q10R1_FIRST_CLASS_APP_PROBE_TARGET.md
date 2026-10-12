# SB-Q10R1 — First-class Devtool Android probe target

The Q10 app build was blocked because its embedded builder used `--toolchain-downloads never --bootstrap-network deny`, while `platforms;android-35` was not installed. This update creates a dedicated **`skybind_app_probe`** target, rooted at the existing `tests/device/probe-app` Gradle project.

Run from Termux:

```sh
cd ~/Code/skybind
./devtoolw app-probe
```

Alternatively use `./devtoolw build-app-probe` followed by `./devtoolw install-app-probe`.

The target calls Devtool's managed Android builder with `--android-platform 35 --toolchain-downloads missing --bootstrap-network allow`. It can bootstrap missing SDK/build-tool packages and resolve the Gradle debug dependencies when network is available. Only missing toolchains are requested; the setting does not alter `~/.config/devtool/config.toml` globally or trigger a module build. A network connection and sufficient disk space are required for uncached dependencies. If Android bootstrap still fails, preserve the Devtool log instead of claiming a build succeeded.

The original app sources (AGP 8.7.3, compileSdk 35) remain unchanged. App packaging stays debug-only, `org.skybind.probe`; original source digests, APK SHA-256 receipt, root-staging checks and non-root app UID verification remain mandatory. Installing the app does not execute its actual read/write test or seal a release. To qualify read/write access, run `~/.local/bin/skybind-q09 app-probe --yes` after installation.

This Devtool overlay requires SB-Q10 already applied and a clean tree. It changes no Android mount/runtime code, signing credentials or release policy.
