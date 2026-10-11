# SB-Q05P7 local Devtool build wrappers (unqualified)

Like the earlier Rclone Nexus workflow, Skybind supports native Devtool wrappers:

```sh
./devtoolw runtime-newfuture   # acquire/verify selected Q04 inputs; no module build
./devtoolw runtime-bclone      # acquire/verify selected Q04 inputs; no module build
./devtoolw build               # default NewFuture prebuilt provider
./devtoolw build-newfuture     # NewFuture provider + exact pinned FUSE helper
./devtoolw build-bclone        # previously built, byte-verified Q04 bclone provider
./devtoolw build-both          # compile Skybind once, package both provider candidates
```

`build*` runs locally through `devtool wrapper exec`, **not GitHub Actions**. The
selected CI compiler remains `go1.27.2`. For **local unqualified module
assembly only**, the exact Termux compiler `go1.27.1` is additionally accepted,
without changing the source lock or the two independent provider build lanes.
The local compiler must be visible as `go` or be selected with
`SKYBIND_LOCAL_GO_BIN=/absolute/path/to/go`. Required commands:
`python3`, `node`, `go`, and `gh` (only for the initial Q04 evidence download).
On Termux, the pinned Go toolchain must execute for `android/arm64` natively.
Every other Go version, including `go1.27.0` and `go1.27.3`, fails closed.
The builder refuses arbitrary compiler substitutions or runtime inputs.

The first invocation retrieves the **already successful Q04 run 38110749243**
through authenticated `gh`, binds its exact repository, run identity, source
commit, both independent lane artifacts, byte comparison, receipts, and every
provider ZIP hash against `q04.inputs.json` and `source.lock.json`. It caches
this under the ignored `build/local-q04-evidence/`. Subsequent builds work
without a network connection when that cache remains verified.

If you have the original Q04 evidence bundle unpacked locally, skip network
retrieval by setting `SKYBIND_Q04_EVIDENCE_ROOT=/absolute/path/to/the/unpacked/evidence-folder`
(the directory must contain `run.json` and `artifacts/`). A damaged cache is
an error, **never an invitation to try a different build or use mutable tags**.

Skybind's own native daemon is compiled from the current checkout with the
**accepted actual local compiler**, `CGO_ENABLED=0`, `GOOS=android`, and
`GOARCH=arm64`, after native host Go
tests and WebUI ES-module checks. The existing deterministic Q05 packager
consumes the selected Q04 NewFuture or bclone ZIPs *unchanged*. The builder
never attempts an NDK/source rebuild of bclone on the phone. Each invocation
writes a distinct output folder at `dist/local-candidates/candidate-*/`
containing `skybind-<provider>-CANDIDATE-UNQUALIFIED.zip` and
`candidate-evidence.json`. The on-disk evidence always records the **actual**
compiler (`toolchain`, e.g. `go1.27.1`), selected CI pin (`selected_ci_toolchain`,
`go1.27.2`), and `local_go_matches_ci_pin=false` when different; it remains
`LOCAL_DEVELOPMENT_UNQUALIFIED` with all gates blocked. This avoids overwriting
earlier outputs or misrepresenting a local build as a CI-equivalent artifact.

`runtime-newfuture`/`runtime-bclone` only fetch/verify evidence; **they do
not build a new provider release**. NewFuture is the official prebuilt with
its recorded custody exception. Local candidate construction is never
independent build attestation, device qualification, signing, or release
sealing. All eight canonical gates stay BLOCKED, seal `NOT_ISSUED`. Do not
flash a local build as a production release without device qualification.

### Local build feedback and missing toolchain (SB-Q05P7 V3)

The wrapper checks the exact selected compiler version before requesting any Q04
artifacts from GitHub. A mismatch exits promptly and reports the detected Go
version and selected `SKYBIND_LOCAL_GO_BIN` executable. To inspect what your
current Termux environment offers:

```sh
command -v go || true
go version
```

The **CI pin remains Go 1.27.2**. With `go1.27.1 android/arm64` already installed
in Termux, `./devtoolw build-bclone` uses that compiler automatically, prints
`LOCAL, UNQUALIFIED`, and verifies that the resulting ELF's Go build metadata
identifies **Go 1.27.1**. No local builds using Go 1.27.1 may be used as
independent CI reproducibility evidence or release qualification. No provider
or FUSE-helper binaries are rebuilt. For a CI-pin-matching local build,
select an actual Go 1.27.2 compiler with `SKYBIND_LOCAL_GO_BIN`.

During successful builds, stages are reported as they begin and complete:
compiler preflight, immutable Q04 evidence acquisition and validation, WebUI
syntax and regressions, Go tests, Android cross-compilation, ELF verification,
module assembly, and final ZIP verification. Long-running steps emit a liveness
line every 15 seconds. Local **Go** test and compiler output is streamed to
Devtool. Provider/`gh` stdout and stderr remain suppressed to avoid leaking
remote details or credentials. No artifact is marked qualified or sealed.
