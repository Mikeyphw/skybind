package daemon

import (
	"context"
	"encoding/json"
	"errors"
	"skybind/internal/control"
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
	"skybind/internal/runtimeauth"
	"time"
)

func emptyArgs(raw json.RawMessage) error {
	if len(raw) == 0 {
		return nil
	}
	var x map[string]json.RawMessage
	if err := protocol.StrictBytes(raw, &x); err != nil {
		return err
	}
	if x == nil || len(x) != 0 {
		return errors.New("expected an empty object")
	}
	return nil
}
func BaseEngine(j *journal.Journal) *control.Engine { return EngineWithConfig(j, nil) }

// EngineWithConfig is the only daemon registration point for the current
// implemented feature set. No nonfunctional operation is registered.
func EngineWithConfig(j *journal.Journal, s *config.Store) *control.Engine {
	return EngineWithMounts(j, s, nil, nil, nil, nil)
}

// EngineWithMounts registers only actually implemented native features.
func EngineWithMounts(j *journal.Journal, s *config.Store, mount *lifecycle.Engine, caches *cache.Manager, sup *supervisor.Supervisor, facts func() policy.Facts) *control.Engine {
	return EngineWithPlatform(j, s, mount, caches, sup, facts, nil, nil)
}

// EngineWithPlatform exposes Android functionality only when the privileged
// daemon owns its canonical namespace and root-manager observers.
func EngineWithPlatform(j *journal.Journal, s *config.Store, mount *lifecycle.Engine, caches *cache.Manager, sup *supervisor.Supervisor, facts func() policy.Facts, ns *namespace.Manager, roots rootmgr.Detector) *control.Engine {
	return EngineWithServices(j, s, mount, caches, sup, facts, ns, roots, nil, nil, nil)
}

// EngineWithServices also owns the job and provider boundaries. It is the
// single privileged registration point; no generic backend execution exists.
func EngineWithServices(j *journal.Journal, s *config.Store, mount *lifecycle.Engine, caches *cache.Manager, sup *supervisor.Supervisor, facts func() policy.Facts, ns *namespace.Manager, roots rootmgr.Detector, jobStore *jobs.Store, providers *provider.Manager, metrics *rc.Manager) *control.Engine {
	e := control.New()
	e.SetJournal(j)
	register := func(name string, class protocol.Class, fn control.Handler) {
		if err := e.Register(name, class, fn); err != nil {
			panic(err)
		}
	}
	register("runtime.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return runtimeauth.StatusCanonical(), nil
	})
	register("system.capabilities", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
		if err := emptyArgs(a); err != nil {
			return nil, err
		}
		return e.Catalog()
	})
	if j != nil {
		register("operation.list", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return j.List()
		})
		register("operation.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.ID == "" {
				return nil, errors.New("empty id")
			}
			rec, e := j.Get(p.ID)
			if e != nil {
				rec, e = j.ByRequest(p.ID)
			}
			if e != nil {
				return nil, e
			}
			if rec.RunID != "" && jobStore != nil {
				run, e := jobStore.RunStatus(rec.RunID)
				if e != nil {
					return map[string]any{"id": rec.ID, "request_id": rec.RequestID, "state": "unknown", "stage": "job_status_unavailable", "job_run_id": rec.RunID, "evidence": "job_run_not_observable"}, nil
				}
				return map[string]any{"id": rec.ID, "request_id": rec.RequestID, "state": run.State, "stage": "job_execution", "job_run_id": run.ID, "progress": map[string]any{"bytes": run.Bytes, "speed_bytes_per_second": run.SpeedBytesPerSecond, "eta_seconds": run.ETASeconds}, "finished_unix": run.FinishedUnix}, nil
			}
			return rec, nil
		})
		register("operation.cancel", protocol.Cancel, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				ID string `json:"id"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.ID == "" {
				return nil, errors.New("empty id")
			}
			if jobStore != nil {
				if run, e := jobStore.Cancel(p.ID); e == nil {
					return run, nil
				}
			}
			return j.Cancel(p.ID)
		})
	}
	if s != nil {
		register("config.snapshot", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.Snapshot()
		})
		register("config.previous", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.Previous()
		})
		decodeCandidate := func(a json.RawMessage) ([]byte, error) {
			var p struct {
				Candidate json.RawMessage `json:"candidate"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if len(p.Candidate) == 0 {
				return nil, errors.New("missing candidate")
			}
			return p.Candidate, nil
		}
		register("config.validate", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			c, err := decodeCandidate(a)
			if err != nil {
				return nil, err
			}
			return s.Validate(c)
		})
		register("config.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			c, err := decodeCandidate(a)
			if err != nil {
				return nil, err
			}
			return s.Preview(c)
		})
		register("config.apply", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				Candidate json.RawMessage `json:"candidate"`
				Proof     string          `json:"proof"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if len(p.Candidate) == 0 || p.Proof == "" {
				return nil, errors.New("missing candidate/proof")
			}
			if mount != nil {
				return mount.ApplyConfig(p.Candidate, p.Proof)
			}
			return s.Apply(p.Candidate, p.Proof)
		})
		register("config.rollback.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return s.RollbackPreview()
		})
		register("config.rollback", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				Proof string `json:"proof"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.Proof == "" {
				return nil, errors.New("missing proof")
			}
			if mount != nil {
				return mount.RollbackConfig(p.Proof)
			}
			return s.Rollback(p.Proof)
		})
	}
	if mount != nil {
		decodeName := func(a json.RawMessage) (string, error) {
			var p struct {
				Name string `json:"name"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return "", err
			}
			if p.Name == "" {
				return "", errors.New("missing name")
			}
			return p.Name, nil
		}
		register("mount.list", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			return mount.List()
		})
		register("mount.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			n, e := decodeName(a)
			if e != nil {
				return nil, e
			}
			return mount.Status(n)
		})
		register("mount.start.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			n, e := decodeName(a)
			if e != nil {
				return nil, e
			}
			return mount.Preview(n)
		})
		register("mount.start", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var p struct {
				Name  string `json:"name"`
				Proof string `json:"proof"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return nil, err
			}
			if p.Name == "" || p.Proof == "" {
				return nil, errors.New("missing mount name or proof")
			}
			return mount.StartGuarded(p.Name, p.Proof)
		})
		register("mount.stop", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, e := decodeName(a)
			if e != nil {
				return nil, e
			}
			return mount.StopContext(ctx, n)
		})
		register("mount.restart", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, e := decodeName(a)
			if e != nil {
				return nil, e
			}
			return mount.RestartContext(ctx, n)
		})
		if sup != nil {
			register("mount.health", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
				n, e := decodeName(a)
				if e != nil {
					return nil, e
				}
				return sup.Health(n)
			})
			register("mount.reconcile", protocol.Reconcile, func(ctx context.Context, a json.RawMessage) (any, error) {
				if err := emptyArgs(a); err != nil {
					return nil, err
				}
				return sup.Reconcile(ctx)
			})
		}
		if s != nil && facts != nil {
			register("policy.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
				n, e := decodeName(a)
				if e != nil {
					return nil, e
				}
				r, e := s.Snapshot()
				if e != nil {
					return nil, e
				}
				for _, m := range r.Mounts {
					if m.Name == n {
						return policy.Evaluate(m, facts(), time.Now()), nil
					}
				}
				return nil, errors.New("mount not found")
			})
		}
		register("vfs.profiles", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if err := emptyArgs(a); err != nil {
				return nil, err
			}
			profiles := policy.Profiles()
			// Add optional advisory metadata without changing the historical
			// array response contract consumed by the copied WebUI.
			advice := policy.DeviceAdvice("/data/adb/skybind/cache")
			for i := range profiles {
				if advice.Known && profiles[i].Name == advice.Profile {
					profiles[i].Recommended = true
					profiles[i].SuggestedMaxBytes = advice.SuggestedMaxBytes
					profiles[i].RecommendationReason = advice.Reason
				}
			}
			return profiles, nil
		})
	}
	if caches != nil {
		decodeCache := func(a json.RawMessage) (string, string, int64, string, error) {
			var p struct {
				Name        string `json:"name"`
				Proof       string `json:"proof"`
				TargetBytes int64  `json:"target_bytes"`
			}
			if err := protocol.StrictBytes(a, &p); err != nil {
				return "", "", 0, "", err
			}
			if p.Name == "" {
				return "", "", 0, "", errors.New("missing name")
			}
			return p.Name, p.Proof, p.TargetBytes, "", nil
		}
		register("cache.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			n, _, _, _, e := decodeCache(a)
			if e != nil {
				return nil, e
			}
			return caches.Status(n)
		})
		for _, kind := range []string{"prune", "clear", "forget"} {
			action := kind
			register("cache."+kind+".preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
				n, _, target, _, e := decodeCache(a)
				if e != nil {
					return nil, e
				}
				if action != "prune" && target != 0 {
					return nil, errors.New("unexpected target")
				}
				return caches.Preview(n, action, target)
			})
			register("cache."+kind, protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
				n, proof, target, _, e := decodeCache(a)
				if e != nil {
					return nil, e
				}
				if proof == "" {
					return nil, errors.New("missing cache proof")
				}
				if action != "prune" && target != 0 {
					return nil, errors.New("unexpected target")
				}
				return caches.Apply(n, action, proof, target)
			})
		}
	}

	if ns != nil {
		decodeMount := func(a json.RawMessage) (string, error) {
			var v struct {
				Name string `json:"name"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return "", e
			}
			if v.Name == "" {
				return "", errors.New("missing mount name")
			}
			return v.Name, nil
		}
		decodeGroup := func(a json.RawMessage) (string, []string, string, error) {
			var v struct {
				Name       string   `json:"name"`
				Namespaces []string `json:"namespaces"`
				Proof      string   `json:"proof"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return "", nil, "", e
			}
			if v.Name == "" {
				return "", nil, "", errors.New("missing mount name")
			}
			return v.Name, v.Namespaces, v.Proof, nil
		}
		register("namespace.inspect", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, e := decodeMount(a)
			if e != nil {
				return nil, e
			}
			return ns.Inspect(ctx, n)
		})
		register("namespace.preview", protocol.Preview, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, g, _, e := decodeGroup(a)
			if e != nil {
				return nil, e
			}
			return ns.Preview(ctx, n, g)
		})
		register("namespace.apply", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, g, p, e := decodeGroup(a)
			if e != nil {
				return nil, e
			}
			return ns.Apply(ctx, n, g, p)
		})
		register("namespace.rollback.preview", protocol.Preview, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, e := decodeMount(a)
			if e != nil {
				return nil, e
			}
			return ns.RollbackPreview(ctx, n)
		})
		register("namespace.rollback", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Name  string `json:"name"`
				Proof string `json:"proof"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return ns.Rollback(ctx, v.Name, v.Proof)
		})
		register("namespace.reconcile", protocol.Reconcile, func(ctx context.Context, a json.RawMessage) (any, error) {
			n, e := decodeMount(a)
			if e != nil {
				return nil, e
			}
			return ns.Reconcile(ctx, n)
		})
	}
	if roots != nil {
		register("platform.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return roots.Status()
		})
	}

	if jobStore != nil {
		register("jobs.snapshot", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return jobStore.Snapshot()
		})
		register("jobs.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return jobStore.Status()
		})
		register("jobs.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Candidate json.RawMessage `json:"candidate"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return jobStore.Preview(v.Candidate)
		})
		register("jobs.apply", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Candidate json.RawMessage `json:"candidate"`
				Proof     string          `json:"proof"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return jobStore.Apply(v.Candidate, v.Proof)
		})
		register("job.run.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Name string `json:"name"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return jobStore.RunPreview(v.Name)
		})
		register("job.run", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Name  string `json:"name"`
				Proof string `json:"proof"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return jobStore.RunManual(v.Name, v.Proof)
		})
	}
	if providers != nil {
		register("remote.list", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Endpoint string `json:"endpoint"`
			}
			if err := protocol.StrictBytes(a, &v); err != nil {
				return nil, err
			}
			return providers.Browse(ctx, v.Endpoint)
		})
		register("remote.stat", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Endpoint string `json:"endpoint"`
			}
			if err := protocol.StrictBytes(a, &v); err != nil {
				return nil, err
			}
			return providers.Stat(ctx, v.Endpoint)
		})
		if jobStore != nil {
			register("remote.transfer.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
				var t jobs.RemoteTransfer
				if err := protocol.StrictBytes(a, &t); err != nil {
					return nil, err
				}
				fingerprint, err := providers.TransferFingerprint(t.Source, t.Destination)
				if err != nil {
					return nil, err
				}
				return jobStore.RemoteTransferPreview(t, fingerprint)
			})
			register("remote.transfer.start", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
				var v struct {
					Kind        string `json:"kind"`
					Source      string `json:"source"`
					Destination string `json:"destination"`
					Proof       string `json:"proof"`
				}
				if err := protocol.StrictBytes(a, &v); err != nil {
					return nil, err
				}
				t := jobs.RemoteTransfer{Kind: v.Kind, Source: v.Source, Destination: v.Destination}
				fingerprint, err := providers.TransferFingerprint(t.Source, t.Destination)
				if err != nil {
					return nil, err
				}
				return jobStore.RemoteTransferStart(t, fingerprint, v.Proof)
			})
		}
		register("provider.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return providers.Status()
		})
		register("provider.remotes", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return providers.Remotes()
		})
		register("provider.browse", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Remote string `json:"remote"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return providers.Browse(ctx, v.Remote)
		})
		register("provider.crypt.password.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return providers.PasswordStatus()
		})
		register("provider.crypt.password.set", protocol.Run, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Password string `json:"password"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return providers.PasswordSet(ctx, v.Password)
		})
		register("provider.crypt.recovery.status", protocol.Query, func(_ context.Context, a json.RawMessage) (any, error) {
			if e := emptyArgs(a); e != nil {
				return nil, e
			}
			return providers.RecoveryStatus(), nil
		})
		register("provider.crypt.preview", protocol.Preview, func(_ context.Context, a json.RawMessage) (any, error) {
			var v provider.CryptSpec
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return providers.CryptPreview(v)
		})
		register("provider.crypt.create", protocol.Run, func(_ context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Spec  provider.CryptSpec `json:"spec"`
				Proof string             `json:"proof"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return providers.CryptCreate(v.Spec, v.Proof)
		})
	}
	if metrics != nil {
		register("rc.metrics", protocol.Query, func(ctx context.Context, a json.RawMessage) (any, error) {
			var v struct {
				Name string `json:"name"`
			}
			if e := protocol.StrictBytes(a, &v); e != nil {
				return nil, e
			}
			return metrics.Metrics(ctx, v.Name)
		})
	}
	return e
}
