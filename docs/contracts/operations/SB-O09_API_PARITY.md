# SB-O09: Canonical typed API, CLI and daemon coverage

`docs/contracts/typed-operations.json` remains the normative 57-operation
inventory. `internal/control/operations.json` is an exact embedded byte copy,
checked by `tests/cli/test_crosswalk.py` and Devtool's `api-parity` job.

- `system.capabilities` is a transport-level discovery operation, not a
  58th product feature. Its response includes the 57 canonical operations,
  protocol `{min,max}`, each operation's class, descriptor, schema, status,
  and cancellation contract. Unimplemented operations are declared
  `implemented: false` and dispatch returns `not_implemented`.
- `skybind operation NAME [JSON]` infers the class from the exact catalog;
  `skybind rpc NAME CLASS [JSON]` checks the same catalog. There is no
  shell or arbitrary RC pass-through.
- The actual root daemon constructs `EngineWithConfig(journal, registry)`.
  Seven `config.*` operations now invoke the transactional registry rather
  than remaining inert behind a status-only engine.
- Secrets, private paths, and arbitrary rclone flags are never arguments
  to a WebUI operation. Strict JSON is enforced for registered handlers.
- The untouched original WebUI `requiredOperations` source is checked
  against the retained catalog, excluding explicitly disallowed operations.
  A surgical copy/adapter update is owned by later WebUI overlays. Visual
  and on-device evidence are NOT attested here.

## Scoped assurance

Devtool apply runs the contract crosswalk, Go tests under two umasks,
Go race tests, `go vet`, Android/arm64 compile, and baseline contract tests.
The first source milestone SB-G01 and second gate SB-G02 are not promoted by
this overlay. No Android app mount, WebUI parity or release seal is claimed.
