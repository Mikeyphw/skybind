# SB-Q05P4 — WebUI ESM bootstrap syntax repair (V2)

## Observed physical-device symptom

On the rooted KernelSU device the bclone module and `skybind` daemon started,
`skybindd.sock` existed, `webui bridge --capabilities` returned exit 0, and
all six read-only startup operations returned successfully. The embedded WebUI
remained on the literal HTML placeholder `Connecting…`.

## Root cause

The candidate Q05P3 `module/webroot/app.js` contains a surplus `});` after
the `cryptBackdrop` click listener and before the `jobBackdrop` listener.
JavaScript **module** parsing fails with `SyntaxError: Unexpected token '}'`
before `bootstrap()` can run. The original Nexus reference does not contain
this stray closure. Plain `node --check app.js` under environments treating
`.js` as CommonJS is not a sufficient module gate.

## Scope

Remove the single misplaced closure; leave the preserved Nexus callback-name
interface, Skybind native operations, provider binaries, source selection,
module hooks and release gates unchanged. Add a CI gate using
`node --input-type=module --check < module/webroot/*.js` (once per file)
**before** producing Android candidate ZIPs. Add a negative regression test
that reintroduces the exact bad token and confirms parser rejection.

This source fix does not attest actual WebView loading, device installation,
FUSE, cross-app access, source custody, or any release gate.

**G01–G08 BLOCKED; final seal NOT_ISSUED.**
