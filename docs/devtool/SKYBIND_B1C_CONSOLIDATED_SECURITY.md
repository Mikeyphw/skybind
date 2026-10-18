# Skybind B1-C4–C7 consolidated security gates

## Preserved evidence (reported; NOT rerun here)

- Historical hosted pipeline: `be9ee025156643fe9a5c21d577dd0d2f` / run `39070051696` / source `1b808119720ed3c042ffc2a8fa84ebe313697eb8`.
- B1-C1 installed pair provenance + Android instrumentation: `PASS_B1C_DEVICE_INSTRUMENTATION` (2 cases).
- B1-C3 UID/SELinux survey: `PASS_B1C3_UID_OBSERVATION_NOT_BROKER_AUTH`.
- Never reinterpret those results as evidence for the newly added Android tests.

## Consolidated lanes

1. **B1-C4 — Binder caller identity (staging):** `BinderCallerGate` only reads `Binder.getCallingUid()` on a synchronous inbound Binder transaction; requires operator-provided UID/package/certificate pins; defaults deny. `BinderCallerGateTest` exercises correct installed signing pin, tampered pin, mismatched UID, missing allowlist, and immutable pin-copy behavior. No exported service registered, no grants.
2. **B1-C5 — Go broker request and TOCTOU hardening:** reject duplicate JSON keys and structured/nested request fields before authorization; verify the kernel peer again after grant authorization and immediately before the read backend. Negative tests assert zero backend calls on malformed requests and process-identity change.
3. **B1-C6 — Source-bound successor APK acceptance:** `r1_b1c_consolidated_device.py` requires a *new* completed Actions-06 pipeline receipt, matching current Git HEAD, signed/debug APK hashes and one archive; expects four exact instrumentation cases; refuses old H4 receipt and byte mismatches. Supports read-only preflight, then explicit optional first install *only when both packages are absent*; never replaces existing applications.
4. **B1-C7 — Grouped Devtool evidence and regression:** single Devtool wrapper `r1-b1c-consolidated` executes both Go and Python source checks and documents the successor device flow. Source receipt is write-once, and remains not device-qualified.

## Acceptance runbook

From `~/Code/skybind`, after source-bound overlay application (which makes a local Git commit):

```sh
./devtoolw r1-b1c-consolidated
# Fallback if wrapper drifted:
python3 scripts/dev/android/r1_b1c_security_source.py
```

Push the **new source commit** using Git. Then dispatch the already-configured Actions-06 hosted pipeline using your existing Devtool command; wait for all nodes to succeed, then use the H4-compatible attestor with the **new pipeline ID**:

```sh
devtool -r "$PWD" actions pipeline run --file docs/devtool/r1_android_hosted_pipeline.json --auth gh --yes --json
# after its result/archive succeed:
python3 scripts/dev/android/r1_hosted_apk_attest.py --pipeline-id NEW_PIPELINE_ID --auth gh
python3 scripts/dev/android/r1_b1c_consolidated_device.py --pipeline-id NEW_PIPELINE_ID --mode preflight
```

The earlier H4 installed APKs may differ in bytes or debug signing certificate from the new build; in that case the runner **blocks rather than replacing them**. Preserve app data and evidence. A separately authorized, explicit signed upgrade strategy is required. Do not automatically uninstall, replace, or wipe anything.

Only after the successor pair is installed and authenticated should you run:

```sh
python3 scripts/dev/android/r1_b1c_consolidated_device.py --pipeline-id NEW_PIPELINE_ID --mode instrument
```

The target `PASS_B1C_CONSOLIDATED_IN_APP_BINDER_TESTS_NOT_CROSS_UID` is intentionally **not** cross-UID acceptance. A *distinct UID* test-caller fixture and an OS-trusted Android PackageManager-to-Go attestor must still be implemented and physically qualified, before any external Go broker listener or grants are enabled.

## Security and reproducibility boundaries

- `Binder.getCallingUid()` is trusted only inside a genuine incoming Binder transaction; a caller-supplied UID/signature string is not proof.
- The Go `brokeridentity.PackageAttestor` interface is still deliberately unwired for production. No serialized Android observation or ADB output is treated as broker authority.
- No production broker listener, privileged token issuer, Android app-data clear, automatic uninstall/reboot, or release qualification.
- Existing archived receipts and old historical passes remain unchanged.
