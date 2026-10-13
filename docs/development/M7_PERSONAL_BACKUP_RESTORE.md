# M7 — Portable Personal Backup and Safe Restore

Status: implemented in source, Android device behavior **not yet verified**. Formal CFS1 gates unchanged and optional for Personal Release.

## Scope and boundaries

- `backup.save` (`run`) requires `acknowledge_public:true`, exports `skybind-personal-backup-<sha256prefix>.json` into the fixed Android `/storage/emulated/0/Download` location. Never overwrites a different file or follows a destination symlink.
- `backup.export` (`query`) returns the same portable backup via authenticated typed RPC; no filesystem path supplied by caller.
- Backup `schema:1` carries typed mount registry, WebUI preferences, *references only* to verified offline pins, timestamp and SHA-256 digest of canonical JSON payload. Each mount's remote reference/path and offline pin filenames remain visible in the portable JSON: keep exports private.
- rclone config/credentials, crypt passphrases, RC secrets, private offline file contents, queued offline edit journals, private encryption keys, running state and Android module installation are **not backed up**. There is **no** weak plaintext credential-export option.
- `backup.preview` validates typed import JSON, checksum, schema, resource limits, paths, mount policies and current config revision. It obtains a time-limited one-use `config.preview` proof for the exact imported candidate, with ALL `enabled` fields explicitly forced false.
- `backup.restore` (`run`) requires `acknowledge_disabled:true` and that fresh proof. Calls the existing `mountEngine.ApplyConfig` path, preserving guarded pre-quiesce/ownership checks, durable pending journal, previous known-good snapshot and crash recovery. It cannot start imported mounts.
- UI settings are independently restored through existing `ui.settings.preview`/`ui.settings.apply` proofs: **a separate transaction**, not claimed atomic with registry restore. Failure must be reported separately.
- The normal 57-operation historical CFS1 API catalog remains untouched. M7 operations are an optional allowlisted extension; no generic root shell/file read/write bridge.

## WebUI workflow

1. Open **Settings → Personal backup & restore → Export backup**. Confirm the data visibility warning. The resulting location and SHA-256 appear on screen.
2. On the target, install/launch Skybind and configure the needed rclone remotes/credentials **separately**. Select the JSON file using **Import from JSON file**.
3. Click **Preview restore**; review every mount change. A valid backup alone does not apply anything.
4. Click **Restore disabled mounts** and explicitly confirm. If quiescing an existing mount is unsafe (pending writes / ownership failure), the existing lifecycle will block restore. Check revision and history before retrying.
5. Optionally click **Restore preferences**, which performs a separate proof-bound settings transaction; an error here does not undo a successful registry restore.
6. Manually review remote references and enable desired mounts using ordinary Skybind controls. Offline pin reference data is informational; pin objects and local write journals are never restored by M7.

### CLI alternative (root, authenticated daemon required)

```
SB=/data/adb/modules/skybind/system/bin/skybind
su -c "$SB rpc backup.export query '{}'"
su -c "$SB rpc backup.save run '{\"acknowledge_public\":true}'"
```

For import, prefer the WebUI file picker, not a root-shell command that reads arbitrary public files. No arbitrary-path privileged import/export operation exists.

## Acceptance evidence / safety tests

- `internal/backup/backup_test.go`: roundtrip, safe disabled candidate, pin reference-only, digest/schema/path corruption, inline-secret rejection, public export no-clobber and no-follow symlink.
- `internal/daemon/backup_m07_test.go`: typed operation/class allowlist, public export consent, proof preview, disabled import, wrong class/unknown arguments, proof replay, previous known-good registry and corrupt document refusal.
- `tests/webui/test_m07_backup_ui.mjs`: explicit controls and two-step application.
- Validate with `go test -count=1 ./...`, `go vet ./...`, `GOOS=android GOARCH=arm64 CGO_ENABLED=0 go build -buildvcs=false ./cmd/skybind`, JS tests and the existing five-file WebUI contract.
- On Android: create backup, copy backup to a test device/location, preview and restore **with all mounts stopped and uploads clean**, simulate interruption/restart, inspect previously configured remotes, and verify manual enabling. Keep a known-good module/package and a copy of the original registry.

## Deferred (not represented as complete)

- User-key-encrypted credential export and restore. No plaintext credential export will be added as a shortcut.
- Actual transfer of private offline pin objects / queued offline edits between devices; pin references are metadata, not downloadable files.
- Atomic *multi-domain* mount registry + UI preferences restore. Each domain has its own separately proof-bound transaction instead.
- Real-device embedded KernelSU file-picker behavior, Android shared-storage permission and provider migration test.
