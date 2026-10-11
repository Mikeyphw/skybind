package namespace

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"sort"
	"strings"
	"sync"
	"time"
)

type OwnedSource interface {
	VerifiedMount(string) (lifecycle.Ownership, lifecycle.MountObservation, error)
}
type Discovery interface {
	Scan(context.Context, Signature) (Snapshot, error)
}
type BindRecord struct {
	Namespace string    `json:"namespace"`
	PID       int       `json:"pid"`
	MountID   string    `json:"mount_id"`
	Source    Signature `json:"source"`
	Target    string    `json:"target"`
}
type Ledger struct {
	Schema  int          `json:"schema"`
	Mount   string       `json:"mount"`
	State   string       `json:"state"`
	Source  Signature    `json:"source"`
	Records []BindRecord `json:"records"`
	Updated int64        `json:"updated"`
}
type Worker interface {
	Bind(context.Context, int, string, Signature) (string, error)
	Detach(context.Context, BindRecord) error
}
type Manager struct {
	mu     sync.Mutex
	source OwnedSource
	scan   Discovery
	worker Worker
	dir    string
	proof  *previewproof.Store
}
type Plan struct {
	Mount           string    `json:"mount"`
	Selected        []string  `json:"selected"`
	Source          Signature `json:"source"`
	Groups          []Group   `json:"groups"`
	Fingerprint     string    `json:"fingerprint"`
	Proof           string    `json:"proof,omitempty"`
	DeviceQualified bool      `json:"device_qualified"`
}

func CanonicalManager(source OwnedSource) *Manager {
	return NewManager(source, CanonicalScanner(), linuxWorker{}, filepath.Join(paths.StateRoot, "namespace"))
}
func NewManager(src OwnedSource, scan Discovery, work Worker, dir string) *Manager {
	return &Manager{source: src, scan: scan, worker: work, dir: dir, proof: previewproof.New()}
}
func safeName(s string) bool {
	if len(s) < 1 || len(s) > 63 || s[0] < 'A' && s[0] < 'a' {
		return false
	}
	for _, r := range s {
		if !(r >= 'A' && r <= 'Z' || r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '_' || r == '-') {
			return false
		}
	}
	return true
}
func (m *Manager) file(n string) string { return "binds-" + n + ".json" }
func (m *Manager) load(n string) (Ledger, error) {
	b, e := atomicfile.Read(m.dir, m.file(n), 256*1024)
	if os.IsNotExist(e) {
		return Ledger{Schema: 1, Mount: n, State: "none", Records: []BindRecord{}}, nil
	}
	if e != nil {
		return Ledger{}, e
	}
	var l Ledger
	if json.Unmarshal(b, &l) != nil || l.Schema != 1 || l.Mount != n || len(l.Records) > maxScanGroups {
		return Ledger{}, errors.New("invalid ownership ledger")
	}
	return l, nil
}
func (m *Manager) save(l Ledger) error {
	l.Updated = time.Now().Unix()
	b, e := json.Marshal(l)
	if e != nil {
		return e
	}
	if len(b) > 256*1024 {
		return errors.New("ownership ledger too large")
	}
	return atomicfile.Write(m.dir, m.file(l.Mount), b)
}
func (m *Manager) owned(ctx context.Context, n string) (Signature, Snapshot, error) {
	if !safeName(n) {
		return Signature{}, Snapshot{}, errors.New("invalid mount name")
	}
	rec, obs, e := m.source.VerifiedMount(n)
	if e != nil {
		return Signature{}, Snapshot{}, e
	}
	src := Signature{Target: rec.Mountpoint, FS: obs.FsType, Source: obs.Source, MountID: obs.MountID}
	if rec.MountID != obs.MountID || !strings.HasPrefix(obs.FsType, "fuse") {
		return Signature{}, Snapshot{}, errors.New("FUSE identity mismatch")
	}
	snap, e := m.scan.Scan(ctx, src)
	return src, snap, e
}
func (m *Manager) Inspect(ctx context.Context, n string) (Snapshot, error) {
	_, snap, e := m.owned(ctx, n)
	return snap, e
}
func selectGroups(s Snapshot, names []string) ([]Group, error) {
	if !s.Complete {
		return nil, errors.New("incomplete proc topology")
	}
	if len(names) == 0 || len(names) > maxScanGroups {
		return nil, errors.New("choose explicit app namespace groups")
	}
	chosen := map[string]bool{}
	for _, v := range names {
		if chosen[v] || v == "" {
			return nil, errors.New("duplicate or empty namespace")
		}
		chosen[v] = true
	}
	groups := []Group{}
	for _, g := range s.Groups {
		if !chosen[g.Namespace] {
			continue
		}
		if !g.Complete || g.Protected || g.Visibility != NotVisible || len(g.Members) == 0 {
			return nil, fmt.Errorf("unsafe selected namespace %s: %s", g.Namespace, g.Reason)
		}
		for _, mem := range g.Members {
			if mem.Class != "app" {
				return nil, errors.New("mixed or protected namespace")
			}
		}
		groups = append(groups, g)
		delete(chosen, g.Namespace)
	}
	if len(chosen) != 0 {
		return nil, errors.New("selected namespace disappeared")
	}
	return groups, nil
}
func digestPlan(p Plan) string {
	b, _ := json.Marshal(struct {
		Mount    string
		Selected []string
		Source   Signature
		Groups   []Group
	}{p.Mount, p.Selected, p.Source, p.Groups})
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}
func (m *Manager) prepare(ctx context.Context, n string, selected []string) (Plan, error) {
	src, snap, e := m.owned(ctx, n)
	if e != nil {
		return Plan{}, e
	}
	names := append([]string(nil), selected...)
	sort.Strings(names)
	gr, e := selectGroups(snap, names)
	if e != nil {
		return Plan{}, e
	}
	p := Plan{Mount: n, Selected: names, Source: src, Groups: gr, DeviceQualified: false}
	p.Fingerprint = digestPlan(p)
	return p, nil
}
func (m *Manager) Preview(ctx context.Context, n string, selected []string) (Plan, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	l, e := m.load(n)
	if e != nil {
		return Plan{}, e
	}
	if l.State != "none" && l.State != "released" {
		return Plan{}, errors.New("existing or interrupted namespace ownership must be reconciled")
	}
	p, e := m.prepare(ctx, n, selected)
	if e != nil {
		return Plan{}, e
	}
	p.Proof, e = m.proof.Issue(previewproof.Binding{Action: "namespace.apply", Subject: n, Revision: 1, Digest: p.Fingerprint}, 2*time.Minute)
	return p, e
}
func (m *Manager) Apply(ctx context.Context, n string, selected []string, token string) (Ledger, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	p, e := m.prepare(ctx, n, selected)
	if e != nil {
		return Ledger{}, e
	}
	if e = m.proof.Consume(token, previewproof.Binding{Action: "namespace.apply", Subject: n, Revision: 1, Digest: p.Fingerprint}); e != nil {
		return Ledger{}, e
	}
	l, e := m.load(n)
	if e != nil {
		return l, e
	}
	if l.State != "none" && l.State != "released" {
		return l, errors.New("namespace ledger already active/interrupted")
	}
	l = Ledger{Schema: 1, Mount: n, State: "pending", Source: p.Source, Records: []BindRecord{}}
	if e = m.save(l); e != nil {
		return l, e
	}
	compensate := func(cause error) (Ledger, error) {
		l.State = "releasing"
		if e := m.save(l); e != nil {
			return l, fmt.Errorf("%v; cannot record rollback: %w", cause, e)
		}
		for i := len(l.Records) - 1; i >= 0; i-- {
			rec := l.Records[i]
			if e := m.worker.Detach(ctx, rec); e != nil {
				l.State = "attention"
				_ = m.save(l)
				return l, fmt.Errorf("%v; guarded compensation failed: %w", cause, e)
			}
			l.Records = l.Records[:i]
			if e := m.save(l); e != nil {
				l.State = "attention"
				return l, e
			}
		}
		l.State = "released"
		if e := m.save(l); e != nil {
			return l, e
		}
		return l, cause
	}
	for _, g := range p.Groups {
		freshSrc, fresh, e := m.owned(ctx, n)
		if e != nil || freshSrc != p.Source || !fresh.Complete {
			return compensate(errors.New("source or namespace scan changed"))
		}
		found := false
		for _, current := range fresh.Groups {
			if current.Namespace == g.Namespace {
				found = true
				if current.Protected || !current.Complete || current.Visibility != NotVisible || !reflect.DeepEqual(current.Members, g.Members) {
					return compensate(errors.New("namespace group changed or occupied"))
				}
			}
		}
		if !found {
			return compensate(errors.New("namespace vanished"))
		}
		id, e := m.worker.Bind(ctx, g.Members[0].PID, g.Namespace, p.Source)
		if e != nil {
			return compensate(fmt.Errorf("guarded bind failed: %w", e))
		}
		rec := BindRecord{Namespace: g.Namespace, PID: g.Members[0].PID, MountID: id, Source: p.Source, Target: p.Source.Target}
		l.Records = append(l.Records, rec)
		if e := m.save(l); e != nil {
			return compensate(e)
		}
	}
	l.State = "active"
	if e = m.save(l); e != nil {
		return compensate(e)
	}
	return l, nil
}
func (m *Manager) rollbackPlan(ctx context.Context, n string) (Ledger, string, error) {
	l, e := m.load(n)
	if e != nil {
		return l, "", e
	}
	if l.State == "none" || l.State == "released" || len(l.Records) == 0 {
		return l, "", errors.New("no owned binds")
	}
	// Never silently rollback with a changed source FUSE identity or namespace membership.
	src, snap, e := m.owned(ctx, n)
	if e != nil || src != l.Source || !snap.Complete {
		return l, "", errors.New("source or topology cannot be verified")
	}
	for _, rec := range l.Records {
		found := false
		for _, g := range snap.Groups {
			if g.Namespace == rec.Namespace {
				found = true
				if !g.Complete || g.Protected || g.Visibility != VisibleAtTarget || g.Observed.MountID != rec.MountID {
					return l, "", errors.New("owned target changed or is protected")
				}
			}
		}
		if !found {
			return l, "", errors.New("owned namespace vanished")
		}
	}
	b, _ := json.Marshal(l)
	return l, previewproof.Digest(b), nil
}
func (m *Manager) RollbackPreview(ctx context.Context, n string) (map[string]any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	l, d, e := m.rollbackPlan(ctx, n)
	if e != nil {
		return nil, e
	}
	tok, e := m.proof.Issue(previewproof.Binding{Action: "namespace.rollback", Subject: n, Revision: 1, Digest: d}, 2*time.Minute)
	if e != nil {
		return nil, e
	}
	return map[string]any{"mount": n, "records": l.Records, "proof": tok, "device_qualified": false}, nil
}
func (m *Manager) Rollback(ctx context.Context, n, token string) (Ledger, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	l, d, e := m.rollbackPlan(ctx, n)
	if e != nil {
		return l, e
	}
	if e = m.proof.Consume(token, previewproof.Binding{Action: "namespace.rollback", Subject: n, Revision: 1, Digest: d}); e != nil {
		return l, e
	}
	l.State = "releasing"
	if e = m.save(l); e != nil {
		return l, e
	}
	for i := len(l.Records) - 1; i >= 0; i-- {
		rec := l.Records[i]
		if e = m.worker.Detach(ctx, rec); e != nil {
			l.State = "attention"
			_ = m.save(l)
			return l, e
		}
		l.Records = l.Records[:i]
		if e = m.save(l); e != nil {
			return l, e
		}
	}
	l.State = "released"
	return l, m.save(l)
}
func (m *Manager) Reconcile(ctx context.Context, n string) (Ledger, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	l, e := m.load(n)
	if e != nil {
		return l, e
	}
	if l.State == "none" || l.State == "released" {
		return l, nil
	}
	src, snap, e := m.owned(ctx, n)
	if e != nil || src != l.Source || !snap.Complete {
		l.State = "attention"
		_ = m.save(l)
		return l, errors.New("namespace recovery cannot prove ownership")
	}
	for _, rec := range l.Records {
		matched := false
		for _, g := range snap.Groups {
			if g.Namespace == rec.Namespace && g.Complete && !g.Protected && g.Visibility == VisibleAtTarget && g.Observed.MountID == rec.MountID {
				matched = true
			}
		}
		if !matched {
			l.State = "attention"
			_ = m.save(l)
			return l, errors.New("namespace bind ownership drift")
		}
	}
	if l.State == "pending" || l.State == "releasing" {
		l.State = "attention"
		_ = m.save(l)
		return l, errors.New("interrupted namespace operation requires explicit verified decision")
	}
	if l.State == "attention" {
		return l, errors.New("manual recovery required")
	}
	return l, nil
}

// NoOutstanding is required by guarded module uninstall. Interrupted or
// unknown ownership always blocks FUSE teardown, even with zero journal entries.
func (m *Manager) NoOutstanding(n string) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if !safeName(n) {
		return false, errors.New("invalid mount name")
	}
	l, e := m.load(n)
	if e != nil {
		return false, e
	}
	return (l.State == "none" || l.State == "released") && len(l.Records) == 0, nil
}
