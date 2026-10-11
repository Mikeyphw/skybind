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
selected `go1.27.2` must exist on the local host and be visible as `go` or be
selected with `SKYBIND_LOCAL_GO_BIN=/absolute/path/to/go`. Required commands:
`python3`, `node`, `go`, and `gh` (only for the initial Q04 evidence download).
On Termux, the pinned Go toolchain must execute for `android/arm64` natively.
The builder refuses ambient compiler substitutions or arbitrary runtime inputs.

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

Skybind's own native daemon is compiled from the current checkout with pinned
Go, `CGO_ENABLED=0`, `GOOS=android`, and `GOARCH=arm64`, after native host Go
tests and WebUI ES-module checks. The existing deterministic Q05 packager
consumes the selected Q04 NewFuture or bclone ZIPs *unchanged*. The builder
never attempts an NDK/source rebuild of bclone on the phone. Each invocation
writes a distinct output folder at `dist/local-candidates/candidate-*/`
containing `skybind-<provider>-CANDIDATE-UNQUALIFIED.zip` and
`candidate-evidence.json`. This avoids overwriting earlier outputs.

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

The selected compiler remains **Go 1.27.2**; this repair never substitutes an
unreviewed version. Set `SKYBIND_LOCAL_GO_BIN` to an executable that reports
that exact version. `pkg install golang` may provide a different version,
so check `go version` rather than assuming its compatibility. A Linux Go
binary for glibc cannot be assumed executable in native Termux.

During successful builds, stages are reported as they begin and complete:
compiler preflight, immutable Q04 evidence acquisition and validation, WebUI
syntax and regressions, Go tests, Android cross-compilation, ELF verification,
module assembly, and final ZIP verification. Long-running steps emit a liveness
line every 15 seconds. Local **Go** test and compiler output is streamed to
Devtool. Provider/`gh` stdout and stderr remain suppressed to avoid leaking
remote details or credentials. No artifact is marked qualified or sealed.
