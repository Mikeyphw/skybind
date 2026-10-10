package daemon

import (
	"context"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"skybind/internal/control"
	"skybind/internal/diagnostics"
	"skybind/internal/doctor"
	"skybind/internal/jobs"
	"skybind/internal/journal"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/mounts/policy"
	"skybind/internal/mounts/supervisor"
	"skybind/internal/namespace"
	"skybind/internal/protocol"
	"skybind/internal/provider"
	"skybind/internal/rc"
	"skybind/internal/rootmgr"
	"skybind/internal/support"
)

// EngineWithObservability adds only the four documented Doctor/Logs operations.
// Existing callers retain their original typed engine without silent defaults.
func EngineWithObservability(j *journal.Journal, s *config.Store, mount *lifecycle.Engine, caches *cache.Manager, sup *supervisor.Supervisor, facts func() policy.Facts, ns *namespace.Manager, roots rootmgr.Detector, jobStore *jobs.Store, providers *provider.Manager, metrics *rc.Manager, logs *diagnostics.Store, bundles *support.Store, reporter doctor.Reporter) *control.Engine {
	e := EngineWithServices(j, s, mount, caches, sup, facts, ns, roots, jobStore, providers, metrics)
	if logs != nil {
		e.SetAudit(func(operation, outcome string) {
			level := "INFO"
			if outcome != "ok" {
				level = "WARN"
			}
			_ = logs.Write(level, "rpc", "OPERATION", "operation="+operation+" outcome="+outcome)
		})
	}
	register := func(name string, kind protocol.Class, h control.Handler) {
		if err := e.Register(name, kind, h); err != nil {
			panic(err)
		}
	}
	register("doctor.report", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return reporter.Run(ctx), nil
	})
	if logs != nil {
		register("diagnostics.logs", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			var f diagnostics.Filter
			if err := protocol.StrictBytes(a, &f); err != nil {
				return nil, err
			}
			if f.Limit == 0 {
				f.Limit = 100
			}
			return logs.Query(f)
		})
	}
	if bundles != nil {
		register("doctor.bundle", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			report := reporter.Run(ctx)
			safe := map[string]any{"doctor": report, "qualification": map[string]string{"state": "SOURCE_ONLY_DEVICE_NOT_ATTESTED", "final_seal": "NOT_ISSUED"}}
			if logs != nil {
				recent, err := logs.Query(diagnostics.Filter{Limit: 30})
				if err != nil {
					return nil, err
				}
				safe["logs"] = recent
			}
			return bundles.Create(safe)
		})
		register("doctor.bundle.read", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			var req struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(a, &req); err != nil {
				return nil, err
			}
			if req.ID == "" {
				return nil, errors.New("missing bundle id")
			}
			b, err := bundles.Read(req.ID)
			if err != nil {
				return nil, err
			}
			if len(b) > 128*1024 {
				return nil, errors.New("bundle exceeds RPC response bound")
			}
			hash := sha256.Sum256(b)
			return map[string]any{"id": req.ID, "encoding": "base64", "bytes": len(b), "sha256": hex.EncodeToString(hash[:]), "content": base64.StdEncoding.EncodeToString(b)}, nil
		})
	}
	return e
}
