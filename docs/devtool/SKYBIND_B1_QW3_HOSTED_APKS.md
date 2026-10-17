# B1-QW3: hosted Android debug APK evidence through Devtool

B1-QW3 extends the applied QW2 scheduling baseline. It does not run Gradle,
install Android apps, enable the privileged broker or claim a qualified release.

## Native pipeline

The committed `docs/devtool/r1_android_hosted_pipeline.json` is consumed by
**Devtool Actions-06** directly. Nodes: `source` (clean local Git), `policy`
(existing `skybind_android_app#build-policy` via native Devtool invoke),
`build` (GitHub workflow_dispatch of `skybind-android-apks.yml` on `main`),
`result` (exact GitHub workflow/source/dispatch success), and `archive`
(Actions-04 authenticated digest-verified exact artifact archive). The pipeline
is journaled before any POST. Never use `run` to retry a waiting or uncertain
request: call `status`, then `resume` for **that pipeline ID**. An uncertain
POST or interrupted mutable operation requires explicit reconciliation. In
particular, if GitHub returns HTTP 204 (dispatch accepted but no run ID),
Devtool records an **uncorrelated** dispatch and stops. Do not invoke `run`
again to manufacture a correlation or accidentally start a second build; inspect
the stored Actions dispatch receipt and remote runs, and wait for a supported
identity-reconciliation workflow.

## Before running

The Devtool apply step makes a **new local commit** but never pushes it.
Commit/push the resulting source to the target GitHub remote `main`; local HEAD
and GitHub `main` must match exactly. `gh auth status` must confirm appropriate
permissions for dispatch and artifact download. Use this repository only, not
an unrelated fork. The pipeline's `ref: main` is deliberately fixed.

```sh
cd "$HOME/Code/skybind"
./devtoolw r1-hosted-source
# Read-only remote preflight (does not dispatch)
devtool -r "$PWD" actions pipeline plan --file docs/devtool/r1_android_hosted_pipeline.json --auth gh --json
# Only when ready to authorize ONE GitHub build:
devtool -r "$PWD" actions pipeline run --file docs/devtool/r1_android_hosted_pipeline.json --auth gh --yes --json
# Save pipeline_id from the response; do not run again to check completion.
devtool -r "$PWD" actions pipeline status --pipeline-id PIPELINE_ID --json
devtool -r "$PWD" actions pipeline resume --pipeline-id PIPELINE_ID --auth gh --yes --json
# Repeat *resume of the existing pipeline* as needed; not redispatch.
```

`run` can return `incomplete`/`waiting` while the hosted run continues. A
successful dispatch is not a successful build, and downloaded ZIP bytes are not
a verified installable app.

## Paired APK independent acceptance

After the native pipeline reports `completed_successfully=true`, run:

```sh
python3 scripts/dev/android/r1_hosted_apk_attest.py --pipeline-id PIPELINE_ID --auth gh
```

The attestor invokes **native** `devtool actions verify` to re-check GitHub
artifact metadata and the previously downloaded archive, ties its digest,
repository, source, run, attempt and workflow ID to the exact native Devtool
journal and registry, and requires exactly the two expected APKs plus the
hosted build manifest. It checks manifest names, byte lengths, hashes, GitHub
source/run/attempt/workflow fields, then calls Devtool's existing
`actions_android.inspect_android_zip` APK inspector for each **exact ZIP
member**, requiring `apksigner` plus `aapt` or `aapt2` on the host. Both
signing certificate hashes must agree. If Android tools are unavailable, this
gate fails closed rather than claiming APK acceptance. It never extracts or
installs the APK files. One immutable receipt is created under
`build/evidence/r1-android-hosted/PIPELINE_ID/attestation.json` only on success.

Result: `PASS_HOSTED_PAIR_INSPECTED_NOT_DEVICE_QUALIFIED`. This remains **debug
APK provenance**, not device qualification or release certification. Debug
signing is ephemeral on GitHub and not production identity continuity.

## Known Devtool limit

The general-purpose `devtool actions android collect` ACTIONS-05 code is
hard-coded to `devtool-android-build.yml` and rejects a successful run from
Skybind's `skybind-android-apks.yml`. Do not bypass its workflow check, forge a
second named workflow, or claim the stock collector succeeded. QW3 reuses the
native ACTIONS-04 verifier and native shared APK inspection function with an
explicit Skybind workflow binding. A future upstream Devtool improvement
should allow source-pinned arbitrary workflow identity for Android collect.

## Scope and provenance

No real GitHub dispatch, artifact download, Termux Android SDK check, device
installation, cross-UID trusted attestation, broker activation or final
release acceptance was run while preparing the overlay. Source tests use
synthetic ZIP bytes and an injected fake package inspector, explicitly **not**
real signed APKs.
