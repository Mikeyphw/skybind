# SB-FPH01 — R01/R02 + FP01/FP02/FP03 promise audit and contract hotfix

Assurance: inspected source and reproducible fixtures only. Release and physical-device qualification remain BLOCKED. All dynamic-runtime and migration operations remain excluded.

## Audit by released overlay

| Source | Explicit promise | Checked result |
|---|---|---|
| R01 | Ship runtime provenance; verify archive members | Source implementation and negative fixture tests present. Official upstream supply-chain evidence outstanding |
| R01 | Quiesce verified old mounts before config publication; record failed restart | Native lifecycle calls wired to config apply and rollback; injected owner/rollback regressions present. Device mount tests outstanding |
| R02 | Journal mutations before effects; link job claims to real run IDs | Production `control.Engine.Dispatch` reserves and commits records and links job `RunID`; terminal job state remains independently polled |
| R02 | Explicit namespace selection and backend proof | Original-WebUI `flow.js` and `app.js` select app-only groups and forward native `proof`; Android app access unverified |
| R02 | Cache proofs and job progress | Adapter translates previews; status reads durable actual job runs; not a live event stream |
| FP01 | Original UI styling; runtime/platform/bundle adapters; configured idle policy | Source integration present; original HTML/CSS untouched; screenshots/WebView evidence outstanding |
| FP01 | Avoid fake crypt generation inventory | Unknown revisions represented by `null` and explicit unknown presentation; FP02 adds tracked revision metadata |
| FP02 | Fixed CLI commands | **FOUND** `mount health NAME` incorrectly encoded `{}` and `mount reconcile` required an unaccepted name; fixed by SB-FPH01 |
| FP02 | Secure stdin-only crypt password; local media jobs; revisioned crypt records | Source paths and tests present, limited to Android media tree by design; real remote/crypto device tests outstanding. **FOUND:** retained WebUI password notices still said generation tracking did not exist; corrected to show an actual tracked revision or Unknown |
| FP03 | Metering and stabilization use observed facts | `SampleAndroidFacts` maintains daemon-lifetime transitions; ambiguous Android output remains unknown; device/parser compatibility unverified |
| FP03 | Doctor checks actionable and truthful in original UI | **FOUND** original UI expected code/summary/detail/guidance/overall, backend returned id/reason/remedy and no overall. SB-FPH01 maps checked data and adds an explicit unqualified device warning |
| FP03 | Advisory VFS; stacked namespace rejection; queryable operation progress | Source implementations present; device facts/Android WebView remain unverified |

## Hotfix behavior

- `mount health NAME` produces `{ "name": "NAME" }`, the exact argument expected by the registered `mount.health` query; missing/extra arguments fail.
- `mount reconcile` produces `{}` for the registered `mount.reconcile` operation; extra arguments fail.
- `doctor.report` is presented through the original UI fields without changing backend or original HTML/CSS. Unknown/malformed check IDs, duplicate checks, incomplete check inventory, invalid statuses and unexpected qualification markers fail closed.
- Password notices show an attested tracked generation or **Unknown**; they never incorrectly claim that the FP02 generation-tracking feature is absent.
- All-source PASS results **never** produce a green device-qualified Doctor summary. A synthesized explicit device-qualification WARN reflects the backend's `SOURCE_ONLY_DEVICE_NOT_ATTESTED` marker; real FAIL remains FAIL.

## Automated Devtool acceptance

Apply uses exact source-hash guards and automatically validates Go CLI, backend, original UI adapters, both umasks, supported-host races, Android ARM64 compile, prior FP01/FP02 contracts and independent release `BLOCKED` audit. No separate manual tests are required.

## Outstanding, not misrepresented as delivered

Official NewFuture/bclone source pins and independently verified build, physical Android FUSE lifecycle, namespace reads from ordinary apps, root-manager boot/uninstall, actual cloud/crypt jobs, complete WebUI screenshot/interaction parity, all G01–G08 qualification and final seal. The five repaired overlays delivered source features, **not** this external assurance evidence.
