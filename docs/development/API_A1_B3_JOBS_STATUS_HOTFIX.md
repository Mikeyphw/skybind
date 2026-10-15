# Skybind A1–B3 jobs.status JSON contract hotfix

Issue: the first device A1–B3 read-only run passed direct bridge, event cursor/replay and negative cases, but A1/A3 jobs.status failed. The source serializes an empty Go run slice as `null`, violating the stable JSON array contract expected by the test runner and WebUI. This is a source-grounded likely diagnosis; the first raw device evidence ZIP has not been inspected.

Implementation:
- `internal/jobs/jobs.go`: nonnil slice in jobs.status so an empty history marshals as `[]`.
- Go JSON serialization regression verifies exactly `[]`.
- Device runner checks actual numeric A3 fields, validates values (including retry flag and percent total), and reports null/missing distinctly with no private paths, job names, or raw RPC output.
- Python host regression covers empty, null, valid and invalid run fields.

This is SOURCE ONLY, atomic Devtool overlay. The installed module still needs a rebuilt binary before `jobs.status` changes on the phone. Existing event logs and offline queues are untouched. No mount restart, data mutation or release seal.

After a verified build/install, run `./devtoolw api-device-readonly`; ideally set a harmless existing remote test folder through `SKYBIND_QA_REMOTE_BASE` first. Upload the resulting JSON/ZIP. Do not run disposable mode until all required nonblocked readonly checks pass and the folder is dedicated to testing. Historical failure evidence must be retained.
