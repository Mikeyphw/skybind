# Skybind native app — B1 scaffold

Android builds (both `app-debug.apk` and `app-debug-androidTest.apk`) are authorized **only on GitHub Actions** through `.github/workflows/skybind-android-apks.yml`. Never run `gradle`, `gradlew`, or a Devtool Android build locally for this project. Local/Termux runs may inspect downloads, verify signatures/manifest and instrument an already verified APK on the selected device.

The Compose UI is currently intentionally disconnected. Jobs is an actionable queue, Activity a read-only timeline. No socket/grant/credential access, root or broad storage permissions are implemented. Artifact manifest completion is NOT device qualification. The APKs use ephemeral hosted debug signing until a persistent, independently reviewed signing policy is established.
