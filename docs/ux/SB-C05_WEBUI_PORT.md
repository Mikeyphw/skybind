# SB-C05 Original WebUI port — assurance boundary

The original eight WebUI files are captured under `tests/fixtures/webui-reference/raw`. The module WebUI is copied directly from that baseline, with narrowly scoped Skybind renames, retained styling/navigation, a local one-time-token form, and an adapter for the C04 native typed response and CSRF contracts.

The original CSS selectors and icon bytes are retained, except for the isolated authentication styles. Excluded features: dynamic runtime, crypt data migration/cleanup, and legacy activity toggles. These are not runnable in Skybind.

Automated evidence: SHA-256 reference manifest checks, audited DOM IDs/views, transport security contracts, browser interaction/screenshot smoke where supported, full affected Go tests, cross-build, roadmap and gate invariants. Device WebView/root-manager testing and full cross-device golden-image comparisons remain NOT_ATTESTED until separately executed.

This is SOURCE_IMPLEMENTED_NOT_PROMOTED; SB-G07 is NOT_ATTESTED and SB-FS1 NOT_ISSUED.
