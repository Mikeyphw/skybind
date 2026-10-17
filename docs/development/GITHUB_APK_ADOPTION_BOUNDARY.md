# Hosted APK adoption boundary (B1)

The hosted manifest is **self-asserted build output** until authenticated against the GitHub Actions API for the exact expected repository, ref, head SHA, run ID and attempt, completed job conclusion and artifact ID. Verify downloaded ZIP and APKs, their certificate SHA-256 and installed APK bytes, then real Android package/UID identity before device tests. Never rely on an untrusted manifest alone for qualification. The `apk_manifest.py verify` command reports `github_run_authenticated=false` by design; it is intentionally insufficient to authorize install.

For the hosted source scaffold the Android app has no runtime root or storage permission and no socket access. The Linux source verifier cannot replace a signed GitHub APK build. `WAITING_REMOTE` is not failure nor artifact success. The legacy Q10 local Gradle builder is retired and intentionally BLOCKED by its wrappers; historical Q10 evidence and source remain preserved.
