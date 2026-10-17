# R0 chrootctl source-bound rclone consumer contract

**State: NOT_IMPLEMENTED / NOT DEVICE QUALIFIED.** Generated from the supplied `chroot-ctl-20261015-205232-256052.tar.gz`; does not run the root module or import secrets. Companion JSON pins exact source bytes and reports parser/command/flag expectations.

- Probe: `version` first line must start with `rclone v`; protected root-owned executable and config behavior remain chrootctl-owned.
- Metadata: `lsjson --max-depth 1 --no-mimetype`, and `lsjson --stat --no-mimetype`; preserve strict JSON stat fields.
- Streaming: `cat` stdout with JSON stats on stderr; `rcat` consumes stdin and retries; cancellation kills child.
- Publication: `moveto --immutable` must have no-clobber semantics; `deletefile` is reserved exclusively for owned `.partial-*` objects.
- Config: never copy chrootctl or Skybind credentials or bypass chrootctl root runtime seal.
- Explicit source verification: `python3 scripts/dev/provider/chrootctl_r0.py --audit-source /path/to/chrootctl`.

A passing R0 fixture is **source-level inspection only**, not authorization of any operation or a statement of BKX/chrootctl migration success.
