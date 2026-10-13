// Package supervisor performs bounded reconciliation. No unbounded retry loop
// and no forced remount on a resource-policy outage.
package supervisor

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/paths"
	"sync"
	"time"
)

type Engine interface {
	List() ([]string, error)
	Status(string) (lifecycle.State, error)
	Desired(string) (bool, error)
	Start(string) (lifecycle.State, error)
}
type Health struct {
	Name     string    `json:"name"`
	State    string    `json:"state"`
	Reason   string    `json:"reason"`
	Attempts int       `json:"attempts"`
	RetryAt  time.Time `json:"retry_at,omitempty"`
}
type retry struct {
	attempts int
	next     time.Time
	deferred bool // Only a pre-spawn policy denial may be expedited by a network hint.
}
type Supervisor struct {
	mu              sync.Mutex
	engine          Engine
	now             func() time.Time
	retry           map[string]retry
	maxAttempts     int
	lastNetworkWake time.Time
	dir             string
	cache           *cache.Manager
	registry        *config.Store
}

func New(e Engine) *Supervisor {
	return &Supervisor{engine: e, now: time.Now, retry: map[string]retry{}, maxAttempts: 5}
}

// NewCanonical persists bounded retry budgets across daemon restarts. A corrupt
// or unsafe state file blocks startup rather than resetting the budget.
func NewCanonical(e Engine) (*Supervisor, error) {
	return NewPersistent(e, filepath.Join(paths.StateRoot, "health"))
}
func NewPersistent(e Engine, dir string) (*Supervisor, error) {
	s := New(e)
	s.dir = dir
	b, err := atomicfile.Read(dir, "retry-v1.json", 131072)
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	var v map[string]struct {
		Attempts int       `json:"attempts"`
		Next     time.Time `json:"next"`
		Deferred bool      `json:"deferred,omitempty"`
	}
	if err = json.Unmarshal(b, &v); err != nil {
		return nil, err
	}
	for k, r := range v {
		if k == "" || r.Attempts < 0 || r.Attempts > s.maxAttempts {
			return nil, errors.New("invalid persisted retry state")
		}
		s.retry[k] = retry{attempts: r.Attempts, next: r.Next, deferred: r.Deferred}
	}
	return s, nil
}
func (s *Supervisor) persist() error {
	if s.dir == "" {
		return nil
	}
	v := map[string]struct {
		Attempts int       `json:"attempts"`
		Next     time.Time `json:"next"`
		Deferred bool      `json:"deferred,omitempty"`
	}{}
	for k, r := range s.retry {
		v[k] = struct {
			Attempts int       `json:"attempts"`
			Next     time.Time `json:"next"`
			Deferred bool      `json:"deferred,omitempty"`
		}{r.attempts, r.next, r.deferred}
	}
	b, e := json.Marshal(v)
	if e != nil {
		return e
	}
	return atomicfile.Write(s.dir, "retry-v1.json", b)
}

// NetworkChanged handles a debounced OS notification as a hint, never proof of
// connectivity. Only policy-deferred next checks may be brought forward. It
// cannot reset retry attempts, provider-failure backoff, or exhausted budgets.
// A burst of kernel notifications cannot induce more than one expedited check
// in fifteen seconds. The real Start policy still samples trusted device facts.
func (s *Supervisor) NetworkChanged() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	now := s.now()
	if !s.lastNetworkWake.IsZero() && now.Sub(s.lastNetworkWake) < 15*time.Second {
		return false
	}
	changed := false
	for name, r := range s.retry {
		if !r.deferred || r.attempts >= s.maxAttempts || !now.Before(r.next) {
			continue
		}
		r.next = now
		s.retry[name] = r
		changed = true
	}
	if changed {
		s.lastNetworkWake = now
	}
	return changed
}

// ConfigureCache applies bounded high/low-water maintenance during periodic reconciliation.
func (s *Supervisor) ConfigureCache(c *cache.Manager, r *config.Store) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.cache = c
	s.registry = r
}
func (s *Supervisor) maybePrune(name string) {
	if s.cache == nil || s.registry == nil {
		return
	}
	r, e := s.registry.Snapshot()
	if e != nil {
		return
	}
	for _, m := range r.Mounts {
		if m.Name == name && m.CacheMaxBytes > 0 && m.CacheHighPercent > 0 && m.CacheHighPercent > m.CacheLowPercent {
			// M3: a stopped cache can still contain unsent uploads. Only the
			// running rclone process may perform native VFS eviction. Without
			// a durable, independently verified clean writeback manifest we
			// must not unlink stopped-cache files or spend CPU scanning them.
			return
		}
	}
}
func (s *Supervisor) Health(name string) (Health, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	v, e := s.engine.Status(name)
	r := s.retry[name]
	return Health{Name: name, State: v.Observed, Reason: v.Reason, Attempts: r.attempts, RetryAt: r.next}, e
}
func (s *Supervisor) Reconcile(ctx context.Context) ([]Health, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	names, e := s.engine.List()
	if e != nil {
		return nil, e
	}
	out := []Health{}
	for _, name := range names {
		if ctx.Err() != nil {
			return out, ctx.Err()
		}
		desired, err := s.engine.Desired(name)
		if err != nil {
			return out, err
		}
		status, err := s.engine.Status(name)
		if err != nil {
			out = append(out, Health{Name: name, State: "DEGRADED", Reason: "inspection_failed"})
			continue
		}
		if !desired {
			delete(s.retry, name)
			s.maybePrune(name)
			out = append(out, Health{Name: name, State: "STOPPED", Reason: "explicit_stop"})
			continue
		}
		if status.Observed == "RUNNING" {
			delete(s.retry, name)
			out = append(out, Health{Name: name, State: "RUNNING", Reason: "ready"})
			continue
		}
		r := s.retry[name]
		if r.attempts >= s.maxAttempts {
			out = append(out, Health{Name: name, State: "DEGRADED", Reason: "retry_budget_exhausted", Attempts: r.attempts})
			continue
		}
		if s.now().Before(r.next) {
			out = append(out, Health{Name: name, State: "RETRYING", Reason: "backoff", Attempts: r.attempts, RetryAt: r.next})
			continue
		}
		v, startErr := s.engine.Start(name)
		if errors.Is(startErr, lifecycle.ErrResourcePolicyDeferred) {
			// Start returned before touching FUSE or provider processes. Delay
			// the next policy check without exhausting the budget reserved for
			// actual failed starts. Keep any previously spent tokens.
			r.next = s.now().Add(30 * time.Second)
			r.deferred = true
			s.retry[name] = r
			out = append(out, Health{Name: name, State: "RETRYING", Reason: "policy_deferred", Attempts: r.attempts, RetryAt: r.next})
			continue
		}
		r.attempts++
		r.deferred = false
		backoff := time.Second * time.Duration(1<<uint(min(r.attempts, 6)))
		if backoff > time.Minute {
			backoff = time.Minute
		}
		r.next = s.now().Add(backoff)
		s.retry[name] = r
		if startErr != nil {
			out = append(out, Health{Name: name, State: "DEGRADED", Reason: fmt.Sprintf("start_blocked:%v", startErr), Attempts: r.attempts, RetryAt: r.next})
		} else {
			out = append(out, Health{Name: name, State: v.Observed, Reason: v.Reason, Attempts: r.attempts, RetryAt: r.next})
		}
	}
	if err := s.persist(); err != nil {
		return out, err
	}
	return out, nil
}
func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
