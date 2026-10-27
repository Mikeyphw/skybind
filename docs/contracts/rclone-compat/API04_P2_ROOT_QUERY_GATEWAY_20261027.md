# Skybind API-04 P2 — separately activated BKX mount-query gateway

Status: **source-candidate; Android SELinux/device acceptance NOT COMPLETE**. No installed policy, root module service hook, or default listener is created by this change.

- Production listener is the single fixed abstract Unix endpoint `skybind-api04-bkx-query-v1`, not a path beneath the root-only `/data/adb` hierarchy. It only starts when a root operator directly invokes `skybind-api04-gateway --operator-approve` with independently approved Skybind authority identity. It does not start in ordinary Skybind daemon/module startup. It is an additional endpoint independent of R1's broker and grant store.
- Separate `skybind-api04-pm-authority-v1` connects to the unprivileged Skybind Android app authority process. The root gateway verifies its kernel credentials, process lifetime, SELinux label and independently approved installed Skybind APK bytes. It delegates installed BKX package UID/signing lookup to the existing strict PackageManager bridge, not BKX-provided claims.
- Policy lives at `/data/adb/skybind/api04-bkx-policy-v1.json` and must be explicitly provisioned by the operator with 0700 root parent and root-owned, regular, non-hardlinked 0600 policy file. This release does **not** create or activate a policy. P1 continues to require exact BKX package, UID, certificate digest, SELinux label and approved named mounts.
- A BKX client checks root peer UID on the abstract socket and may only submit `mount.status` or `mount.health` with one named mount. Root side obtains `SO_PEERCRED`, verifies both Android PackageManager and proc identity and permits only Guard.Prepare validated read-only `feature.execute` requests, forwarded through the canonical private daemon socket. Re-verifies peer identity before publishing result. No shell, arbitrary rclone, R1 token, namespace, preview, mutation, cached grants or alternative request routing.
- One bounded request per connection, a 12s deadline, 8 concurrent connections, 64KiB envelope limit, 256KiB result limit, generic denial codes. Exact request ID is returned and checked by the BKX client.
- BKX UI has separate opt-in mount query controls. No automatic selection, no bypassing Lite/Embedded runtime rules, and no fallback to BKX's bundled rclone if API04 denies.
- Normal Android app access to abstract Unix endpoints is SELinux-policy/device-dependent. A successful host test, Go cross-build, APK build or source preflight does **not** prove that the installed app can connect. No permissive SELinux change, `su` workaround, system privilege change, installed APK update or root process auto-start is authorized by this source overlay.

## Operator-only candidate command (NOT an automatic deployment)

The operator must independently establish Skybind's installed app UID, SELinux process label, installed APK path and exact SHA256, and provision the root-owned P1 policy with a reviewed BKX package pin. The Android app must be in an explicitly enabled local authority foreground session.

```sh
# Run the separately built Android ARM64 gateway diagnostic as root, with
# independently verified real values; placeholders must NOT be copied literally.
skybind-api04-gateway-android-arm64 --operator-approve \
  --authority-uid "$APPROVED_SKYBIND_UID" \
  --authority-context "$APPROVED_SKYBIND_SELINUX" \
  --authority-apk "$APPROVED_SKYBIND_BASE_APK" \
  --authority-apk-sha256 "$APPROVED_SKYBIND_APK_SHA256"
```

## Open gates

1. Exact source candidate accepted by independent Devtool transactions in Skybind and BKX.
2. Real rooted device runtime: independent PackageManager attestation; peer UID/SELinux positive and wrong-signer/wrong-UID negatives; abstract endpoint accessibility with enforcing SELinux; process death/rotation/restart; system Android policy proof. The PM authority foreground service must be explicitly enabled.
3. Signed BKX and Skybind APK instrumentation, live root binary provenance and cross-consumer acceptance.
4. API-04 P3 mutation preview/proof and reconciliation remain separately blocked. No mutation capability is implied by this query-only source.
