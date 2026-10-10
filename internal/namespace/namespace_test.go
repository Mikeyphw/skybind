package namespace

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"skybind/internal/mounts/lifecycle"
	"strings"
	"testing"
)

var source = Signature{Target: "/storage/skybind/test", FS: "fuse.rclone", Source: "rclone", MountID: "42"}

type fakeSource struct{ fail bool }

func (s fakeSource) VerifiedMount(n string) (lifecycle.Ownership, lifecycle.MountObservation, error) {
	if s.fail {
		return lifecycle.Ownership{}, lifecycle.MountObservation{}, errors.New("not owned")
	}
	return lifecycle.Ownership{Name: n, Mountpoint: source.Target, MountID: source.MountID}, lifecycle.MountObservation{Point: source.Target, FsType: source.FS, Source: source.Source, MountID: source.MountID}, nil
}

type fakeScan struct {
	groups   []Group
	complete bool
}

func (s *fakeScan) Scan(_ context.Context, src Signature) (Snapshot, error) {
	out := Snapshot{Source: src, Target: src.Target, Complete: s.complete, Groups: append([]Group(nil), s.groups...)}
	return out, nil
}

type fakeWorker struct {
	scan       *fakeScan
	calls      int
	failAt     int
	detachFail bool
}

func (w *fakeWorker) Bind(_ context.Context, pid int, ns string, src Signature) (string, error) {
	w.calls++
	if w.failAt == w.calls {
		return "", errors.New("injected bind failure")
	}
	id := fmt.Sprint(1000 + w.calls)
	for i := range w.scan.groups {
		if w.scan.groups[i].Namespace == ns {
			w.scan.groups[i].Visibility = VisibleAtTarget
			w.scan.groups[i].Observed = Signature{Target: src.Target, FS: src.FS, Source: src.Source, MountID: id}
		}
	}
	return id, nil
}
func (w *fakeWorker) Detach(_ context.Context, r BindRecord) error {
	if w.detachFail {
		return errors.New("injected detach failure")
	}
	for i := range w.scan.groups {
		if w.scan.groups[i].Namespace == r.Namespace {
			w.scan.groups[i].Visibility = NotVisible
			w.scan.groups[i].Observed = Signature{}
		}
	}
	return nil
}
func appGroup(ns string, pid int) Group {
	return Group{Namespace: ns, Complete: true, Members: []Member{{PID: pid, UID: 10123, Class: "app", User: 0}}, Visibility: NotVisible}
}
func managerFixture(t *testing.T, n int) (*Manager, *fakeScan, *fakeWorker) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	g := []Group{}
	for i := 1; i <= n; i++ {
		g = append(g, appGroup(fmt.Sprintf("mnt:[%d]", i), i))
	}
	scan := &fakeScan{groups: g, complete: true}
	worker := &fakeWorker{scan: scan}
	return NewManager(fakeSource{}, scan, worker, dir), scan, worker
}
func TestPlanApplyRollbackAndReplay(t *testing.T) {
	m, s, w := managerFixture(t, 2)
	ctx := context.Background()
	ns := []string{"mnt:[1]", "mnt:[2]"}
	p, e := m.Preview(ctx, "Demo", ns)
	if e != nil || p.Proof == "" {
		t.Fatal(e)
	}
	l, e := m.Apply(ctx, "Demo", ns, p.Proof)
	if e != nil || l.State != "active" || len(l.Records) != 2 || w.calls != 2 {
		t.Fatal(l, e)
	}
	if _, e = m.Apply(ctx, "Demo", ns, p.Proof); e == nil {
		t.Fatal("replayed proof accepted")
	}
	pr, e := m.RollbackPreview(ctx, "Demo")
	if e != nil {
		t.Fatal(e)
	}
	l, e = m.Rollback(ctx, "Demo", pr["proof"].(string))
	if e != nil || l.State != "released" || len(l.Records) != 0 {
		t.Fatal(l, e)
	}
	if s.groups[0].Visibility != NotVisible {
		t.Fatal("detach not observed")
	}
	if _, e = m.Rollback(ctx, "Demo", pr["proof"].(string)); e == nil {
		t.Fatal("replayed rollback accepted")
	}
}
func TestProtectedAliasIncompleteAndForeignDenied(t *testing.T) {
	m, s, w := managerFixture(t, 1)
	ctx := context.Background()
	s.groups[0].Protected = true
	if _, e := m.Preview(ctx, "Demo", []string{"mnt:[1]"}); e == nil {
		t.Fatal("protected namespace accepted")
	}
	s.groups[0].Protected = false
	s.groups[0].Visibility = VisibleAtAlias
	if _, e := m.Preview(ctx, "Demo", []string{"mnt:[1]"}); e == nil {
		t.Fatal("alias treated as exact target")
	}
	s.groups[0].Visibility = IdentityMismatch
	if _, e := m.Preview(ctx, "Demo", []string{"mnt:[1]"}); e == nil {
		t.Fatal("foreign target accepted")
	}
	s.groups[0].Visibility = NotVisible
	s.complete = false
	if _, e := m.Preview(ctx, "Demo", []string{"mnt:[1]"}); e == nil {
		t.Fatal("incomplete scan accepted")
	}
	s.complete = true
	if _, e := m.Preview(ctx, "Demo", []string{"not-found"}); e == nil {
		t.Fatal("vanished group accepted")
	}
	if w.calls != 0 {
		t.Fatal("worker called during rejected previews")
	}
}
func TestFailedMultiBindCompensation(t *testing.T) {
	m, _, w := managerFixture(t, 2)
	ctx := context.Background()
	ns := []string{"mnt:[1]", "mnt:[2]"}
	p, e := m.Preview(ctx, "Demo", ns)
	if e != nil {
		t.Fatal(e)
	}
	w.failAt = 2
	l, e := m.Apply(ctx, "Demo", ns, p.Proof)
	if e == nil || l.State != "released" || len(l.Records) != 0 {
		t.Fatal(l, e)
	}
	if safe, e := m.NoOutstanding("Demo"); !safe || e != nil {
		t.Fatal(safe, e)
	}
}
func TestFailedCompensationPreservesOwnership(t *testing.T) {
	m, _, w := managerFixture(t, 2)
	ctx := context.Background()
	ns := []string{"mnt:[1]", "mnt:[2]"}
	p, _ := m.Preview(ctx, "Demo", ns)
	w.failAt = 2
	w.detachFail = true
	l, e := m.Apply(ctx, "Demo", ns, p.Proof)
	if e == nil || l.State != "attention" || len(l.Records) != 1 {
		t.Fatal(l, e)
	}
	if safe, _ := m.NoOutstanding("Demo"); safe {
		t.Fatal("failed rollback allowed teardown")
	}
}
func TestStalePreviewAndChangedOwnershipDenied(t *testing.T) {
	m, s, w := managerFixture(t, 1)
	ctx := context.Background()
	ns := []string{"mnt:[1]"}
	p, e := m.Preview(ctx, "Demo", ns)
	if e != nil {
		t.Fatal(e)
	}
	s.groups[0].Members[0].PID = 22
	if _, e = m.Apply(ctx, "Demo", ns, p.Proof); e == nil {
		t.Fatal("changed PID accepted")
	}
	if w.calls != 0 {
		t.Fatal("mutated changed namespace")
	}
	s.groups[0].Members[0].PID = 1
	p, _ = m.Preview(ctx, "Demo", ns)
	l, e := m.Apply(ctx, "Demo", ns, p.Proof)
	if e != nil {
		t.Fatal(e)
	}
	s.groups[0].Observed.MountID = "foreign"
	if _, e = m.RollbackPreview(ctx, "Demo"); e == nil {
		t.Fatal("foreign mount accepted")
	}
	if _, e = m.Reconcile(ctx, "Demo"); e == nil {
		t.Fatal("reconcile hid foreign mount")
	}
	if l.State != "active" {
		t.Fatal(l)
	}
}
func TestVisibilityClassifierExactAliasMismatch(t *testing.T) {
	g := appGroup("mnt:[1]", 1)
	classifyVisibility(&g, []Signature{{Target: "/storage/emulated/0", FS: "fuse.rclone", Source: "rclone", MountID: "2"}}, source)
	if g.Visibility != VisibleAtAlias {
		t.Fatal(g.Visibility)
	}
	classifyVisibility(&g, []Signature{{Target: source.Target, FS: "ext4", Source: "disk", MountID: "3"}}, source)
	if g.Visibility != IdentityMismatch {
		t.Fatal(g.Visibility)
	}
	classifyVisibility(&g, []Signature{{Target: source.Target, FS: source.FS, Source: source.Source, MountID: "4"}}, source)
	if g.Visibility != VisibleAtTarget {
		t.Fatal(g.Visibility)
	}
}
func TestScannerSyntheticMultiUser(t *testing.T) {
	root := t.TempDir()
	for _, x := range []struct{ pid, ns, uid, comm, point string }{{"100", "mnt:[1]", "10123", "com.example.app", source.Target}, {"110", "mnt:[2]", "10123", "zygote64", source.Target}, {"200", "mnt:[3]", "110123", "com.work.app", "/storage/emulated/1"}} {
		p := filepath.Join(root, x.pid)
		_ = os.MkdirAll(filepath.Join(p, "ns"), 0700)
		_ = os.Symlink(x.ns, filepath.Join(p, "ns/mnt"))
		_ = os.WriteFile(filepath.Join(p, "status"), []byte("Uid:\t"+x.uid+"\t"+x.uid+"\n"), 0600)
		_ = os.WriteFile(filepath.Join(p, "comm"), []byte(x.comm+"\n"), 0600)
		mount := fmt.Sprintf("44 33 0:40 / %s rw - fuse.rclone rclone rw\n", x.point)
		_ = os.WriteFile(filepath.Join(p, "mountinfo"), []byte(mount), 0600)
	}
	snap, e := (Scanner{Proc: root}).Scan(context.Background(), source)
	if e != nil || !snap.Complete || len(snap.Groups) != 3 {
		t.Fatal(snap, e)
	}
	got := map[string]Group{}
	for _, g := range snap.Groups {
		got[g.Namespace] = g
	}
	if got["mnt:[1]"].Visibility != VisibleAtTarget || !got["mnt:[2]"].Protected || got["mnt:[3]"].Visibility != VisibleAtAlias {
		t.Fatalf("invalid groups %+v", got)
	}
	if got["mnt:[3]"].Members[0].User != 1 {
		t.Fatal("work user not classified")
	}
}
func TestWorkerGuards(t *testing.T) {
	if e := validNoSymlinks("/../tmp"); e == nil {
		t.Fatal("unsafe target accepted")
	}
	if code := RunWorker([]string{"bind"}); code == 0 {
		t.Fatal("invalid request allowed")
	}
	if !strings.HasPrefix(source.FS, "fuse") {
		t.Fatal("test fixture broken")
	}
}
