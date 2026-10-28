# Skybind API04 P3-H1 R2 — catalog-contract validation fix

Source: clean pushed P3 commit `ebf056968a9dac6d6921c1fb73c6b8e449a716e8`.

The original H1 mutation overlay added two daemon-private typed operations to the 57-operation frozen CFS1 catalog: `mount.stop.preview` and `mount.stop.guarded`. Its Devtool transaction `dadc79aa425c41dca157f03dd5595f34` failed during Python bootstrap because the historical planning index still intentionally contains 57 operations and the live catalog contained 59.

R2 replaces H1, not an after-H1 hotfix. It keeps the original 57 source definitions and 45-obligation ledger immutable, validates both operation catalogs have byte-identical contents, and allows exactly two fully specified new operations. It does not broaden the query listener or bypass identity, proof, journal, or operator authorization. All baseline source pins and transactional rollback requirements remain mandatory.

All legacy count tests and personal-release policy code share the same fail-closed catalog checker; unknown names, mismatched class/description/provenance, deleted historical names, renamed original operations, duplicates, tampered totals and catalog divergences fail.

Validation: focused Python and Go tests locally; actual Devtool transaction and Android SELinux/device acceptance still open. No device/release gate promoted. No BKX/chrootctl changes.
