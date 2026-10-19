# Skybind native Android — read-only RootService M1

This repo produces app and test APKs **only through GitHub Actions**, not local Gradle. The native app has five Compose screens (Home, Browser, Jobs, Activity, More) backed by a real read-only RPC client. It is not a privileged file manager or a generic rclone executor.

## Privilege and connection model

1. App launches **unpaired**; it does not auto-request root or access `/data/adb`.
2. The user explicitly taps **Connect** and must approve the app through the device's supported root manager.
3. libsu 6.0.0 starts an **app-owned RootService**; Binder checks the real UID, installed package ownership and signing information on every request. No exported Android broker component is registered. App process remains unprivileged.
4. RootService only permits `system.capabilities`, `runtime.status`, `provider.remotes`, `mount.list`, `jobs.status`, and `operation.events`, all using RPC `class=query`. It requires a root-owned `0700` daemon socket directory, `0600` Unix socket, and root peer credentials. No endpoint override or arbitrary shell.
5. Strict JSON and response limits; the app maps only non-secret fields. Disconnect, malformed responses, unsupported versions and root refusal leave UI unpaired/disconnected with stale data hidden. Jobs and Activity are different authoritative data sources; all controls that mutate remain disabled.

**Security scope:** This app-owned root service is an opt-in RootService, not an independently credentialed cross-UID module broker. It does **not** establish authorization for BKX or chrootctl, nor does it qualify release security. Once the root manager grants root to an app, its privileged code is security-sensitive and must be audited as such.

**Outstanding device gates:** hosted GitHub Kotlin/AIDL compilation, dependency resolution, exact APK/signature provenance, authorization refusal and acceptance under KernelSU, live daemon capabilities/status/remotes/mounts/jobs/events, rebind on Activity recreation, root-service death/disconnect, journal gap, no mutation and root rollback. Do not claim these from source tests.

**Signing transition:** The previous ephemeral hosted debug certificate cannot update already installed Skybind APKs. A source-bound persistent signing policy is now provided through `scripts/dev/android/stable_signing.py` and encrypted GitHub Actions secrets. First-time migration of both packages requires explicit uninstall, which erases their private app data. Subsequent successful builds use the same certificate, provided the signing key is retained. No APK build, install, uninstall, data clear or backup happens as part of the signing overlay.

**Provision once:** In Termux, run `python3 -B scripts/dev/android/stable_signing.py provision` after installing `keytool` (`pkg install openjdk-17` if needed) and authenticating `gh`. Choose a strong password. The key persists at `$HOME/.local/share/skybind/signing/skybind-dev.p12` (mode 0600), outside Git; keep a secure private copy of **this signing key** for future upgrades. This is unrelated to backups of previous app data. The command uploads only the encoded keystore, password, and public certificate pin as GitHub Actions secrets. It does not display or commit the password/key. Do not run `gh workflow run` until all three secrets are configured.

**CI enforcement:** `ci-prepare` requires GitHub-hosted execution, three secrets, valid keystore bytes and the exact pinned certificate before Gradle can execute. `ci-finalize` requires BOTH app and AndroidTest APK signing identities to match that pin. The hosted manifest records `persistent-github-debug` and `signing_certificate_pin_sha256`. Missing credentials or signer rotation BLOCK the build; there is no ephemeral fallback. PR builds without access to secrets fail closed rather than using public credentials. This key is for development APKs, not a production release key.


### M2-N1 folder browsing

After explicitly connecting the read-only RootService, open Browser, select a configured remote and navigate directories with Up/Remotes. This uses daemon `provider.browse` (`lsjson --max-depth 1`) rather than Android root storage access. Folder and file names, path segments, and response size are bounded; stale replies are dropped when the remote changes or a connection is lost. Upload, download, overwrite and cancellation remain disabled pending separate proof-bound operations. Device/browser checks still require GitHub-hosted APKs and authentic fixtures.
