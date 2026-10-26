# API-01 — native rclone, Skybind-owned config, managed mount API boundary

## Decision (merge window API-01 / API-02)

API-01 (module CLI packaging) and API-02 (versioned managed mount interface) were reviewed together but **not combined**: they have distinct device acceptance and different security boundaries. The native public CLI must be usable without granting broad remote access through the external gateway. API-02 is deferred until API-01 source and device validation. Existing internal and R1 API operations remain usable until explicit consumer migration, NOT silently deleted.

## Contract

- Module `system/bin/rclone` and explicit `system/bin/skybind-rclone` alias share the same small `/system/bin/sh` launcher. It execs the **unchanged native pinned provider ELF** at `system/bin/skybind-rclone-engine` beside it; passes all arguments exactly (`"$@"`) and return code, including upstream `serve restic --stdio` streams. No command filtering, shell-eval, RPC emulation or root escalation.
- Launcher sets `RCLONE_CONFIG=/data/adb/skybind/config/rclone.conf` as the canonical *default*. Upstream `--config /other.conf` remains an explicit override. Caller-provided `RCLONE_CONFIG` is intentionally replaced by default. The native engine is still directly usable via its explicit path.
- Root-owned configuration stays `0700/0600`, is **not** exposed to ordinary app UIDs. Root shell and privileged consumers may invoke the launcher; normal app processes do not receive automatic read access or root authority. No broad grant, no PATH injection into unrelated processes. Usability of `/system/bin/rclone` requires the root-manager systemless mount to be active and visible; Termux with a PATH omitting `/system/bin` must use the absolute path or adjust its *own* PATH.
- Provenance: offline provider runtime input is verified unmodified; installed module records native engine ELF, launcher and FUSE helper under exact hashes; the release manifest records input runtime package, upstream provenance SHA and native ELF SHA. Skybind daemon uses **only** the pinned native engine path for jobs/mounts and preserves `--config` arguments. Existing legacy runtime inputs may be verified, but new installed module packaging demands the canonical launcher layout.
- **API boundary:** CLI supports ordinary upstream rclone operations, including writes (subject to native rclone credentials and filesystem rights). Skybind-managed mount lifecycle, namespace changes, health and job control remain gated by daemon policy and capability negotiation. The legacy R1 read-only gateway stays as backwards compatibility until BKX/chrootctl independently qualify direct CLI adoption and Skybind-only API replacements.

## Acceptance (not device-qualified)

- Local deterministic candidate ZIP, executable-mode and byte-hash verification including negative mutations.
- Local shell forward/override test, no symlink or missing provider fallback; validated Go runtime provenance tests.
- **Still required on device:** root-manager systemless `/system/bin/rclone` visibility, `su -c '/system/bin/rclone version'`, real `listremotes`, `lsjson`, config override, exact module runtime verifier, mount lifecycle behavior, BKX restic `serve restic --stdio` and chrootctl. No real remote writes without explicitly approved disposable prefix. Do **not** use module candidate as release seal or silently overwrite installed module.

## Open operational conflict

Native rclone operations can refresh/write config independently of Skybind remote-manager transactions. The config is intentionally shared but concurrency is **not yet qualified**. Preserve backups/revisions; detect stale writes and test token refresh vs UI remote edits in API-02 before enabling multi-writer operational acceptance.

## Next two overlays

- API-02: typed versioned managed mounts/namespace/events feature gateway with existing proof/ownership semantics and compatible consumer adapters.
- API-03: BKX/chrootctl migration, deprecations only after independent test receipts.

## Existing qualification scripts updated

Q12 now inventories **both public commands** `system/bin/rclone`, `system/bin/skybind-rclone` and the native `system/bin/skybind-rclone-engine`. Q13 expects the launcher bytes to match between providers, but compares provider-native ELF hashes at the new path. Q15 synthetic receipts updated to include the native path. These receipt-format changes do NOT rewrite historical Q12/Q13/Q15 evidence.

## Promise audit R2 — public alias and source CI preflight

The public CLI is available under both `rclone` and `skybind-rclone` (two immutable identical launcher bytes beside `skybind-rclone-engine`). No module command takes unrestricted root authority from another UID. Q05P7 source regression expectations follow the preexisting local-only Go compiler policy; CI remains pinned at Go 1.27.2. Root-manager PATH, real installed config, actual source-bound candidate and FUSE API acceptance remain open.
