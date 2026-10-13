# Skybind M4 — Personal Release recovery-test scheduling hotfix

## Failure reported on Termux

`TestM04EventWakeAndCancel` failed with `initial recovery missing` after its
original 200-millisecond goroutine startup deadline. The nearby periodic
fallback test also used a 150-millisecond scheduling deadline. These
deadlines can expire under Android CPU contention without proving recovery
logic is defective.

## Test-only changes

- Give each asynchronous assertion up to **3 seconds** to be scheduled.
- Set the event-test's periodic fallback interval to **one hour** inside
  the test only. Therefore the second Start must come from the explicit
  network notification, not a periodic retry while waiting 3 seconds.
- Keep cancellation and periodic-fallback assertions intact.
- Do not change the production 10s/30s/90s recovery intervals, resource
  policy checks, supervisor retry budget, FUSE behavior, or build gates.

## Test and rebuild

```sh
cd ~/Code/skybind
go test -count=30 -run '^TestM04' ./cmd/skybind
./devtoolw personal-release
```

The Personal Release builder still runs the complete Go test suite and can
block on any genuine test failure. The initial failing job produced no
installable ZIP; no module reinstall is needed solely for this test fix.

## Qualification boundary

This corrects timing-sensitive **unit tests**, not a proven on-device
recovery defect. It is not a substitute for the previously supplied M0–M8
real-device test plan, particularly Wi-Fi reconnection and explicit Stop.
