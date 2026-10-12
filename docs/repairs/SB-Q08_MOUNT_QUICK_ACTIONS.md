# SB-Q08 — Direct mount controls

## Scope
WebUI-only overlay built against the exact SB-R03 UX WebUI files. Compatible with
SB-R03 + SB-Q06R2, with or without SB-Q07 backend reliability patch.

## UX
- Contextual Start/Stop as the first and prominent action; Restart alongside.
- Stop and Restart require an in-page, keyboard-accessible confirmation.
- Mount state comes from native `mount.status` (`observed`) / `mount.health`, never optimistic UI state.
- Pending lifecycle operations lock only that mount's quick actions and show toasts.
- Native lifecycle operations and start preview-proof remain unchanged.
- Folder shows and copies a path; Android file-manager launching is intentionally not claimed.
- Logs, Edit and the advanced action sheet remain available; Delete still requires the existing configuration preview.
- Flat cards, reduced borders and compact secondary actions.
- Status counter and normal STOPPED label are not classified as a health failure.

## Safety/invariants
No FUSE, supervisor, lifecycle, runtime, security boundary, or release-gate files modified.
Preflight checks exact previous WebUI fingerprints and blocked release policy.
Existing RPC authorization, start preview-proof, safety gate and audit paths remain.
No filesystem modifications by the WebUI itself. Module rebuild/install required.

## Testing
Run `node tests/integration/test_q08_mount_quick_actions.mjs` for state and DOM-contract tests.
Validation also executes remaining WebUI regressions, `go test -count=1 ./...`, `go vet ./...`.
Device UI, native Android WebView clipboard support, stop/restart side effects and resulting
mount health still require user-device confirmation.
