# Skybind M1/M2 — persistent hosted debug signer (2026-10-19)

## Purpose and authorization

The M1+M2 APK pair from GitHub Actions run `39198019698` compiled and uploaded, but it was signed by an ephemeral debug certificate (`91b8735c3f3637d611e715dff61f49bd4fba4afff6cb7f3a9145453c8354471e`) while the installed app and AndroidTest packages use `9b3e1758bf2e623b0905419a568e3d4f0c4c66ba007110554c613ff439511e49`. Neither APK is a directly upgradable replacement. The user has authorized replacing **only** the Skybind app and its separately installed test APK, and has explicitly waived **old app data backups**. Uninstall will erase those packages' private app data. The Skybind KernelSU module, daemon, remotes and other packages are outside authorization scope.

## Implementation

`stable_signing.py provision` uses `keytool` to generate (or re-use, never silently rotate) one private PKCS12 signer under the user's home directory. It uploads the encrypted base64 keystore, password, and public certificate SHA-256 pin to GitHub Actions encrypted repo secrets using the authenticated `gh` CLI. The private keystore, password and base64 never enter the repository, GitHub artifact, source receipt or terminal output.

`.github/workflows/skybind-android-apks.yml` allows signed APK builds only via manual dispatch on protected `main`; source validation remains on push. `ci-prepare` requires all secrets and the exact certificate pin before building. Gradle has no ephemeral debug signer fallback. `ci-finalize` requires the hosted app and test APKs match the certificate pin before the manifest is uploaded and records `persistent-github-debug`. This is a debug **developer** key, not a production release key.

## Qualification plan

1. Apply the source-bound overlay to clean `250f44201014d005f522f96001190945fdeb63b2` and run local **source-only** validation; no APK build is permitted locally.
2. Install Termux OpenJDK if necessary (`pkg install openjdk-17`), ensure `gh auth status` has repository-secret write permission, then run `python3 -B scripts/dev/android/stable_signing.py provision` interactively. Choose a strong password and keep the private signing keystore safe, separate from repo; losing it prevents future signed updates. This is *not* a backup of previous Skybind app data.
3. Push the overlay commit, manually dispatch the hosted APK workflow from `main`, then require success, run SHA match, both APK signatures equal the pinned certificate, and source-bound archive evidence.
4. Compare installed package identities again. Only with verified new APK pair perform the user-authorized **two Skybind package** uninstall/reinstall sequence. No backup, no app data preservation claim; no generic cleanup command.
5. Run Compose navigation/RootService/remote browsing tests and guarded real-device read-only connection checks. Preserve old B1-C receipts, mark new M1/M2 physical acceptance only from authenticated evidence.

Any missing secret, GitHub workflow from a different ref, key rotation, signer mismatch, invalid package, unknown device or inability to verify artifact identity is BLOCKED. No attempt to salvage build/install by generating a new ephemeral key, copying old data, or altering unrelated applications.
