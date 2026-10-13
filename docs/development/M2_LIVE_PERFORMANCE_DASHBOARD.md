# Skybind M2 — Live Performance Dashboard

Track: Personal Release. Baseline: M0+M1 trusted writeback and safe lifecycle.

## Delivered

- Flat, expandable **Performance** pane on each Mounts card.
- The pane is **closed by default**. Only opened panes poll authenticated `rc.metrics`; at most **three** may remain open simultaneously.
- Sampling uses the existing visible-page refresh cadence (3 seconds minimum), not a background task. Polling stops on navigation away and when Android hides the WebUI; no network work is done to populate closed panes.
- Per-mount aggregate rclone `core/stats` transfer speed (bytes/sec), transferred bytes, accumulated RC errors; `vfs/stats.diskCache` used bytes/files when the provider publishes those fields.
- M0 writeback condition, queued/in-progress uploads and errored files, with unknown differentiated from zero.
- Lightweight SVG trend of at most **60** speed samples, kept in process memory only. Trend clears when the mount stops or its observed PID changes. Metrics unavailable/not trusted are not charted as zeros.
- Uses the existing 57-operation API, with no privileged generic RC proxy and no changes to FUSE, root permissions, private file paths, credential handling, writeback gating or release policy.

## Honest limits

- `core/stats.speed` is **aggregate rclone throughput**, not a reliable directional upload/download measurement. The UI does not invent per-direction rates.
- RC metrics depend on a currently verified running mount. Remote errors, missing counters, unexpected provider shape, invalid numbers and older M0/M1 modules surface as *unavailable*.
- Session history is neither persisted nor a measurement of transferred data during periods when the WebUI is closed. There is no energy-intensive daemon gathering history.
- The unchanged M1 writeback safety still needs real-device testing during actual uploads. M2 does not relax its fail-closed Stop/Restart behavior.
- Chromium interaction tests are optional and cannot qualify Android WebView without a physical device.

## Device acceptance

1. Build and install the Personal Release after applying the overlay; retain the old module ZIP.
2. On the Mounts page, expand `Performance` for a running mount. Observe aggregate rate, VFS cache and writeback values. Without traffic, zero speed may be correct if the source reports zero.
3. Start an actual download or upload and verify changing aggregate throughput; queued/active values depend on the rclone VFS queue.
4. Collapse the panel and change screens; traffic collection must cease while closed/hidden. Reopen and check new samples.
5. Stop/Restart the mount and ensure no stale performance trend is presented for the new process. Verify safe M1 behavior separately with a queued upload.
6. If RC is unavailable, the panel must show `Telemetry unavailable`, not a fabricated idle or 0 KB/s state.
7. Confirm Android WebView layout in narrow portrait and landscape, and that Start, Stop, Restart and Downloads export still work.

## Rollback

Use Devtool transaction rollback if application validation fails; if installation causes an issue, reinstall the prior known-good KernelSU ZIP. The overlay does not itself install anything.
