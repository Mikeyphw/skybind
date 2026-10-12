# SB-Q10R2 — Native Android probe target

Replaces Q10R1 custom Python Android builder with the **same native Devtool Android target model used by Devtool's `android_hud`**.

- `runner = "android"`, `platform = "android"`, `execution_environment = "chroot"`, `chroot_name = "androidos"`
- `:app:assembleDebug`, AAPT2 auto, 2 Gradle workers, cache/parallel enabled
- Gradle **9.7.1**, Android Gradle Plugin **9.3.1**, SDK **36**, Build Tools **36.0.0**, Java **21**
- Native Devtool bootstrap: install missing dependencies, allow network for this **debug** target
- `./devtoolw build-app-probe` uses `runner:android#build`, then stages a source-bound APK receipt
- `./devtoolw app-probe` builds, stages, then installs `org.skybind.probe` as a normal app UID
- `./devtoolw install-app-probe` installs a previously staged matching debug APK

Q10R1's custom `build-apk --no-chroot --android-platform 35` path is **removed**. No release signing or release promotion. Q09 still owns consent-based file access tests.

**Note:** This patch is tested by source/plan validation here; actual Gradle build and KernelSU installation can only be checked on the device. A usable `androidos` chroot configured as for `android_hud` is required.
