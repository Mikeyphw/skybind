# Skybind M0–M8 — Real Android test plan (personal project)

**Purpose:** Spend a little time actually using Skybind after the new personal ZIP is installed, and record what really works. No compliance theatre. The included Python script collects **only status codes and your notes**, and produces readable Markdown and JSON summaries you can attach here.

## Before starting (10 minutes)

- **Apply the accompanying hotfix** if your local checkout matches its preflight; run `./devtoolw personal-release`, then install the resulting ZIP in KernelSU. The source tarball itself does **not** establish that the installed phone module has these changes.
- Keep your last known-good KernelSU ZIP somewhere safe for rollback; don't wipe the previous private cache or edit journals.
- Use a **disposable test remote**, or a separate directory under an existing remote with dummy files only. Have 3 tiny text files, 1 folder with a few files, a 50–100 MB file and optionally a small video. Never practice delete/overwrite on irreplaceable data.
- Have Android Files or another **ordinary unprivileged file manager**, Termux + root, and an app that can edit a plain text file. Enable Wi-Fi initially. If Termux cannot write Android Downloads yet, run `termux-setup-storage` once and grant its storage permission.
- Avoid recording passwords, tokens, account identifiers, sensitive paths, raw rclone.conf, private backup JSON or screenshots with personal information.

## Run the JSON checklist

Open Termux and run:

```bash
cd "$HOME/Code/skybind"
TESTER=scripts/dev/integration/m0_m8_device_tests.py
python3 "$TESTER" selftest
python3 "$TESTER" init --mount safegdrive
```

The last command prints a directory under `/storage/emulated/0/Download/Skybind-Device-Tests/skybind-device-<UTC>/`. **Copy that path** into the shell variable below (replace the example):

```bash
RUN='/storage/emulated/0/Download/Skybind-Device-Tests/skybind-device-YYYYMMDDTHHMMSSZ'
python3 "$TESTER" probe --run "$RUN"       # read-only root CLI probes; no raw output retained
python3 "$TESTER" show --run "$RUN"
```

For each scenario, do the activity on the phone, **then** record its real outcome:

```bash
python3 "$TESTER" record --run "$RUN" --case M2-01 --status PASS \
  --notes 'Copied disposable 80 MB test file; graph responded' --seconds 24
python3 "$TESTER" record --run "$RUN" --case M1-02 --status FAIL \
  --notes 'Stop unexpectedly detached during pending upload'
python3 "$TESTER" record --run "$RUN" --case M5-05 --status BLOCKED \
  --notes 'Known gap: same-path offline fallback not implemented'
```

Statuses are `PASS`, `FAIL`, `BLOCKED`, `SKIP` or untouched `NOT_RUN`. Mark `PASS` **only after actually observing** the expected behavior. `BLOCKED` means unsupported or impossible; `SKIP` means you chose not to run it. A read-only smoke check is not proof that an upload/reboot test passed.

When finished:

```bash
python3 "$TESTER" report --run "$RUN"
python3 "$TESTER" bundle --run "$RUN"
```

This creates `summary.json`, `summary.md`, and an integrity-listed `skybind-device-*.zip` alongside the run directory. **You can share the ZIP here**; it does not automatically include root logs, downloaded files, remote URL, credentials, Android identifiers or full private backup contents. Your manually typed notes may still expose information, so review them.

## Suggested order — actual daily work, not isolated synthetic unit tests

### Session 1 — Mounts + performance (about 30–45 minutes)

1. Confirm the right personal module is installed; run the `probe` above (M8 baseline).
2. Create a small document using Android Files through the mounted remote, open it, edit it, copy it, then delete **only that disposable file** (M8-01).
3. Open Mounts → Performance; transfer a 50–100 MB file. Record transfer rate, VFS cache size and upload counters (M0-01, M2-01). When the panel is collapsed/hidden, check polling behavior (M2-02).
4. Safely test idle Stop, Start and Restart three times (M1-01). Repeat a Restart with Performance expanded; history must reset (M2-03).
5. Copy a larger disposable file and request Stop then Restart while it is **still uploading** (M1-02, M1-03). Expected: drain or refusal; NOT silent cache loss. Do not kill rclone/daemon or wipe its cache to simulate failure.
6. Check the quick buttons / Logs Follow option and the UI on narrow portrait (M8-02). Try Documents, Streaming, Read-only profiles and read-only app rejection on a disposable mount (M3-01, M3-02).

### Session 2 — Networking and offline data (about 30–45 minutes)

7. On a test mount, disconnect/reconnect Wi-Fi, time recovery; explicitly stopped mount must stay stopped (M4-01, M4-02).
8. Pin a small document and a small folder (M5-01). Go into airplane mode. Try offline status and **Export** from private pins (M5-02). Then Publish offline view and open the copy through Android Files (M5-03). This is a *separate Downloads path*. M5-05 remains BLOCKED until transparent original-path FUSE fallback exists.
9. For the export hotfix, on disposable mount definitions only: pin a file, change that mount to another test remote, try export, and expect refusal before public copy. Restore original settings afterward (M5-04). Skip if uncomfortable changing config.
10. Draft/queue a small edited file offline; reboot after staging to confirm persistence. Reconnect, inspect queue and deliberate conflict by modifying original from another client (M6-01, M6-02). If you choose to upload, allow **only the separate copy** and hash-check the original (M6-03).
11. Enable reconnect review if desired, toggle network, and verify it never uploads on its own (M6B-01). Interrupted transfer simulation is optional (M6B-02).

### Session 3 — Backup, reboot, battery (20–30 minutes + optional waiting)

12. Export M7 configuration backup and inspect its keys for plaintext secrets; never share raw JSON (M7-01).
13. Use only disposable mount settings to preview a restore. Confirm restored mounts are disabled, and UI preferences restore separately (M7-02, M7-03).
14. Reboot, time mount recovery, check offline pin and queued edit persistence (M4-03, M8-04).
15. Optional real-life performance: play a local-sized video via FUSE, browse many files, record seek/list latency and cache MiB; keep WebUI hidden for a 60-minute idle sample and write down starting/ending battery percentage (M8-01, M8-03). Don't claim battery improvement without a previous comparable baseline.

## Cases to mark BLOCKED for known, undelivered features

- `M1-04`: live WebUI cancel after Stop/Restart confirmation.
- `M5-05`: transparent same-path offline FUSE reads.
- `M7-04`: encrypted credential migration.

Automatic original-file offline sync/merge and certified stopped-cache eviction were also not delivered. **Do not** simulate them by forcibly manipulating private VFS files or running destructive shell commands. The audit tracks those promises explicitly.

## What to send me

Send **one small `skybind-device-*.zip`** and, if something fails, a *redacted* screenshot or the exact on-screen error. I can read `results.json` and `summary.json` to separate working features, regressions, unknowns and targeted fixes. No independent G01–G08 certification is needed for a personal build.

## Stop conditions / rollback

Stop testing if normal files disappear, an unapproved overwrite occurs, cache data seems endangered, or FUSE refuses to remount after an ordinary Start. Don't delete `/data/adb/skybind/cache`, private `offline/objects`, `writes/`, or your prior ZIP as a repair attempt. Take a screenshot of the error, keep the evidence run, and return to the prior module ZIP through KernelSU if needed.
