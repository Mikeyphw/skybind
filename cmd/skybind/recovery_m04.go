package main

import (
	"context"
	"time"

	"skybind/internal/diagnostics"
	"skybind/internal/jobs"
	"skybind/internal/mounts/supervisor"
)

// Healthy mounts do not need 30-second FUSE/process inspections. Still check
// idle mounts on a bounded fallback to catch missed route events or exits.
const (
	recoveryInitial       = 10 * time.Second
	recoveryPending       = 30 * time.Second
	recoveryHealthy       = 90 * time.Second
	recoveryEventDelay    = 3 * time.Second
	recoveryEventThrottle = 15 * time.Second
	recoveryJobInterval   = 30 * time.Second
)

func recoveryInterval(health []supervisor.Health, err error) time.Duration {
	if err != nil {
		return recoveryPending
	}
	if len(health) == 0 {
		return recoveryHealthy
	}
	for _, h := range health {
		if !(h.State == "RUNNING" && h.Reason == "ready" || h.State == "STOPPED" && h.Reason == "explicit_stop") {
			return recoveryPending
		}
	}
	return recoveryHealthy
}

// The supervisor loop has no extra daemon, foreground service, wakelock, or
// network access. Jobs retain their established 30-second cadence. A loss of
// netlink delivery never prevents bounded periodic reconciliation.
func runRecoveryLoop(ctx context.Context, sup *supervisor.Supervisor, logs *diagnostics.Store, store *jobs.Store, changes <-chan struct{}) {
	runRecoveryLoopWithTiming(ctx, sup, logs, store, changes, recoveryTiming{
		initial: recoveryInitial, pending: recoveryPending, healthy: recoveryHealthy,
		eventDelay: recoveryEventDelay, eventThrottle: recoveryEventThrottle, jobInterval: recoveryJobInterval,
	})
}

type recoveryTiming struct {
	initial, pending, healthy, eventDelay, eventThrottle, jobInterval time.Duration
}

func runRecoveryLoopWithTiming(ctx context.Context, sup *supervisor.Supervisor, logs *diagnostics.Store, store *jobs.Store, changes <-chan struct{}, timing recoveryTiming) {
	audit := newSupervisorAuditor()
	timer := time.NewTimer(timing.initial)
	defer timer.Stop()
	jobsTimer := time.NewTicker(timing.jobInterval)
	defer jobsTimer.Stop()
	deadline := time.Now().Add(timing.initial)
	var lastEvent time.Time
	for {
		select {
		case <-ctx.Done():
			return
		case <-jobsTimer.C:
			if store != nil {
				_, _ = store.Tick()
			}
		case _, ok := <-changes:
			if !ok {
				changes = nil
				continue
			}
			now := time.Now()
			if !lastEvent.IsZero() && now.Sub(lastEvent) < timing.eventThrottle {
				continue
			}
			lastEvent = now
			// Wakes may bypass only a policy-deferred timer, not a real failure.
			sup.NetworkChanged()
			target := now.Add(timing.eventDelay)
			if target.Before(deadline) {
				if !timer.Stop() {
					select {
					case <-timer.C:
					default:
					}
				}
				timer.Reset(timing.eventDelay)
				deadline = target
			}
		case <-timer.C:
			health, err := sup.Reconcile(ctx)
			audit.Write(logs, health, err)
			interval := recoveryInterval(health, err)
			if interval == recoveryHealthy {
				interval = timing.healthy
			} else {
				interval = timing.pending
			}
			timer.Reset(interval)
			deadline = time.Now().Add(interval)
		}
	}
}
