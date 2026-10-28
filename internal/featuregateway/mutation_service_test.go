package featuregateway

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"skybind/internal/brokeripc"
	"skybind/internal/featureapi"
	"skybind/internal/protocol"
	"strings"
	"sync"
	"testing"
	"time"
)

func mutationFixture(t *testing.T) (*MutationService, brokeripc.KernelPeer, *MutationStore, *int) {
	t.Helper()
	p := samplePolicy()
	p.BKX.CertSHA256 = "38723a2e5e8a17aa7950dc008209944e898f69a7bd10a23c839d341e935fd5ca"
	g, e := NewGuard(p, Dependencies{Packages: pmFixture{ok: true}, Proc: procFixture{pid: 10101, uid: p.BKX.UID, label: p.BKX.SELinuxContext, start: 22}})
	if e != nil {
		t.Fatal(e)
	}
	policy := MutationPolicy{Schema: MutationSchema, ExplicitlyEnabled: true, Operations: []string{"mount.start", "mount.stop"}, MountNames: []string{"safeMount"}}
	if e = policy.Validate(p); e != nil {
		t.Fatal(e)
	}
	dir := filepath.Join(t.TempDir(), "mutation")
	if e = os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	store, e := openMutationStoreAt(dir)
	if e != nil {
		t.Fatal(e)
	}
	count := new(int)
	backend := func(_ context.Context, req protocol.Request) (protocol.Response, error) {
		if req.Operation != "feature.execute" || req.Class != protocol.Query {
			return protocol.Response{}, fmt.Errorf("unauthorized backend call")
		}
		var c featureapi.Call
		if e := protocol.StrictBytes(req.Arguments, &c); e != nil {
			return protocol.Response{}, e
		}
		var inner protocol.Response
		switch c.Operation {
		case "mount.start.preview":
			inner = protocol.Success(c.RequestID, map[string]any{"proof": "native-single-use-proof-123456"})
		case "mount.status":
			inner = protocol.Success(c.RequestID, map[string]any{"state": "RUNNING"})
		case "mount.start", "mount.stop":
			*count++
			inner = protocol.Success(c.RequestID, map[string]string{"state": "OK"})
		case "operation.status":
			inner = protocol.Success(c.RequestID, map[string]any{"request_id": "api04_" + strings.Repeat("0", 32), "action": "mount.start", "state": "succeeded"})
		default:
			return protocol.Response{}, fmt.Errorf("unexpected operation: %s", c.Operation)
		}
		return protocol.Success(req.RequestID, inner), nil
	}
	s, e := NewMutationService(g, policy, store, backend)
	if e != nil {
		t.Fatal(e)
	}
	return s, brokeripc.KernelPeer{PID: 10101, UID: p.BKX.UID, GID: p.BKX.UID}, store, count
}
func TestAPI04P3DecodeRejectsAmbiguityAndOutOfScope(t *testing.T) {
	valid := []byte(`{"version":1,"action":"preview","request_id":"req-1","operation":"mount.start","name":"safeMount"}`)
	if _, e := DecodeMutationCall(valid); e != nil {
		t.Fatal(e)
	}
	for _, raw := range []string{
		`{}`, `[]`, `{"version":1,"version":1,"action":"preview"}`,
		`{"version":1,"action":"preview","request_id":"bad/path","operation":"mount.start","name":"safeMount"}`,
		`{"version":1,"action":"preview","request_id":"a","operation":"namespace.apply","name":"safeMount"}`,
		`{"version":1,"action":"preview","request_id":"a","operation":"mount.stop","name":"../bad"}`,
		`{"version":1,"action":"execute","preview_id":"not-a-hex-id"}`,
		`{"version":1,"action":"status","preview_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","operation":"mount.stop"}`,
		`{"version":1,"action":"approve","preview_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`,
		`{"version":1,"action":"preview","request_id":"a","operation":"mount.stop","name":"safeMount","extra":true}`,
	} {
		if _, e := DecodeMutationCall([]byte(raw)); e == nil {
			t.Fatalf("accepted invalid %s", raw)
		}
	}
}
func TestAPI04P3RootApprovalRequiredAndLostReplySafe(t *testing.T) {
	s, peer, store, count := mutationFixture(t)
	ctx := context.Background()
	preview, e := s.Process(ctx, peer, MutationCall{Action: "preview", RequestID: "R-one", Operation: "mount.start", Name: "safeMount"})
	if e != nil || preview.State != "awaiting_root_approval" || len(preview.Digest) != 64 || len(preview.PreviewID) != 32 {
		t.Fatalf("bad preview %+v %v", preview, e)
	}
	rec, e := store.get(preview.PreviewID)
	if e != nil {
		t.Fatal(e)
	}
	if rec.NativeProof == "" || rec.Digest != preview.Digest {
		t.Fatal("private native proof or digest missing")
	}
	data, _ := json.Marshal(preview)
	if strings.Contains(string(data), rec.NativeProof) || strings.Contains(string(data), rec.ProcessKey) {
		t.Fatal("private approval material leaked")
	}
	exec := MutationCall{Action: "execute", PreviewID: preview.PreviewID}
	if _, e = s.Process(ctx, peer, exec); e == nil {
		t.Fatal("executed without root approval")
	}
	if *count != 0 {
		t.Fatal("mutation occurred without approval")
	}
	if e = store.approve(preview.PreviewID, strings.Repeat("f", 64)); e == nil {
		t.Fatal("approved wrong digest")
	}
	if e = store.approve(preview.PreviewID, preview.Digest); e != nil {
		t.Fatal(e)
	}
	if e = store.approve(preview.PreviewID, preview.Digest); e == nil {
		t.Fatal("approved twice")
	}
	result, e := s.Process(ctx, peer, exec)
	if e != nil || result.State != "succeeded" || *count != 1 {
		t.Fatalf("execution %+v %v count %d", result, e, *count)
	}
	if _, e = s.Process(ctx, peer, exec); e == nil {
		t.Fatal("executed replay")
	}
	if *count != 1 {
		t.Fatal("replayed mutation")
	}
	// Simulated crash/restart: the second process opens only durable state;
	// no retry is issued, status is still retrievable by the verified caller.
	reopened, e := openMutationStoreAt(store.dir)
	if e != nil {
		t.Fatal(e)
	}
	s.Store = reopened
	status, e := s.Process(ctx, peer, MutationCall{Action: "status", PreviewID: preview.PreviewID})
	if e != nil || status.State != "succeeded" {
		t.Fatalf("lost-reply reconciliation %+v %v", status, e)
	}
	if *count != 1 {
		t.Fatal("status caused execution")
	}
	wrong := peer
	wrong.UID++
	if _, e = s.Process(ctx, wrong, MutationCall{Action: "status", PreviewID: preview.PreviewID}); e == nil {
		t.Fatal("other UID received result")
	}
}
func TestAPI04P3StopRequiresManualApprovalToo(t *testing.T) {
	s, peer, store, count := mutationFixture(t)
	x, e := s.Process(context.Background(), peer, MutationCall{Action: "preview", RequestID: "stop-1", Operation: "mount.stop", Name: "safeMount"})
	if e != nil {
		t.Fatal(e)
	}
	rec, e := store.get(x.PreviewID)
	if e != nil || rec.NativeProof != "" {
		t.Fatal("stop unexpectedly acquired native proof", e)
	}
	if e = store.approve(x.PreviewID, x.Digest); e != nil {
		t.Fatal(e)
	}
	r, e := s.Process(context.Background(), peer, MutationCall{Action: "execute", PreviewID: x.PreviewID})
	if e != nil || r.State != "succeeded" || *count != 1 {
		t.Fatalf("stop failed %+v %v", r, e)
	}
}
func TestAPI04P3UncertainExecutionNeverReplayed(t *testing.T) {
	s, peer, store, _ := mutationFixture(t)
	x, e := s.Process(context.Background(), peer, MutationCall{Action: "preview", RequestID: "uncertain", Operation: "mount.stop", Name: "safeMount"})
	if e != nil {
		t.Fatal(e)
	}
	if e = store.approve(x.PreviewID, x.Digest); e != nil {
		t.Fatal(e)
	}
	var mu sync.Mutex
	count := 0
	s.Dispatch = func(ctx context.Context, req protocol.Request) (protocol.Response, error) {
		mu.Lock()
		count++
		mu.Unlock()
		return protocol.Response{}, context.DeadlineExceeded
	}
	r, e := s.Process(context.Background(), peer, MutationCall{Action: "execute", PreviewID: x.PreviewID})
	if e != nil || r.State != "unknown" {
		t.Fatalf("uncertain result not preserved %+v %v", r, e)
	}
	if _, e = s.Process(context.Background(), peer, MutationCall{Action: "execute", PreviewID: x.PreviewID}); e == nil {
		t.Fatal("replayed uncertain mutation")
	}
	mu.Lock()
	c := count
	mu.Unlock()
	if c != 1 {
		t.Fatalf("%d attempts", c)
	}
	record, e := store.get(x.PreviewID)
	if e != nil || record.State != "unknown" {
		t.Fatal("lost durable unknown state")
	}
}
func TestAPI04P3PolicyAndStoreFailures(t *testing.T) {
	q := samplePolicy()
	good := MutationPolicy{Schema: MutationSchema, ExplicitlyEnabled: true, Operations: []string{"mount.start"}, MountNames: []string{"safeMount"}}
	if good.Validate(q) != nil {
		t.Fatal("valid P3 rejected")
	}
	bad := good
	bad.Operations = []string{"mount.start", "mount.start"}
	if bad.Validate(q) == nil {
		t.Fatal("duplicate mutation allowed")
	}
	bad = good
	bad.MountNames = []string{"other"}
	if bad.Validate(q) == nil {
		t.Fatal("out-of-scope mount allowed")
	}
	bad = good
	bad.Operations = []string{"namespace.rollback"}
	if bad.Validate(q) == nil {
		t.Fatal("namespace mutation allowed")
	}
	blob, _ := json.Marshal(good)
	if _, e := DecodeMutationPolicy(blob, q); e != nil {
		t.Fatal(e)
	}
	for _, raw := range [][]byte{[]byte(`{"schema":"x","schema":"x"}`), append(blob, []byte("{}")...), []byte(`{"extra":true}`)} {
		if _, e := DecodeMutationPolicy(raw, q); e == nil {
			t.Fatal("bad policy parsed")
		}
	}
	s, peer, store, _ := mutationFixture(t)
	x, e := s.Process(context.Background(), peer, MutationCall{Action: "preview", RequestID: "exp", Operation: "mount.start", Name: "safeMount"})
	if e != nil {
		t.Fatal(e)
	}
	_ = store.withLock(func() error {
		r, e := store.read(x.PreviewID)
		if e != nil {
			return e
		}
		r.Expires = time.Now().Add(-time.Second).Unix()
		return store.write(r)
	})
	if e = store.approve(x.PreviewID, x.Digest); e == nil {
		t.Fatal("expired preview approved")
	}
	if _, e = s.Process(context.Background(), peer, MutationCall{Action: "execute", PreviewID: x.PreviewID}); e == nil {
		t.Fatal("expired preview executed")
	}
	if e = os.Chmod(store.dir, 0777); e != nil {
		t.Fatal(e)
	}
	if _, e = openMutationStoreAt(store.dir); e == nil {
		t.Fatal("world writable root state accepted")
	}
}

func TestAPI04P3ExactOperatorScopeAndConcurrentSingleUse(t *testing.T) {
	s, peer, store, count := mutationFixture(t)
	x, e := s.Process(context.Background(), peer, MutationCall{Action: "preview", RequestID: "once", Operation: "mount.start", Name: "safeMount"})
	if e != nil {
		t.Fatal(e)
	}
	if e = store.approveExact(x.PreviewID, x.Digest, "mount.stop", "safeMount"); e == nil {
		t.Fatal("operator approved wrong operation")
	}
	if e = store.approveExact(x.PreviewID, x.Digest, "mount.start", "wrongMount"); e == nil {
		t.Fatal("operator approved wrong mount")
	}
	if e = store.approveExact(x.PreviewID, x.Digest, "mount.start", "safeMount"); e != nil {
		t.Fatal(e)
	}
	var wg sync.WaitGroup
	success := make(chan bool, 24)
	for i := 0; i < 24; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			r, e := s.Process(context.Background(), peer, MutationCall{Action: "execute", PreviewID: x.PreviewID})
			success <- e == nil && r.State == "succeeded"
		}()
	}
	wg.Wait()
	close(success)
	got := 0
	for ok := range success {
		if ok {
			got++
		}
	}
	if got != 1 || *count != 1 {
		t.Fatalf("single use violated: responses=%d mutations=%d", got, *count)
	}
}
func TestAPI04P3PolicyFileRequiresPrivateOwnerModeAndNoSymlink(t *testing.T) {
	p := samplePolicy()
	valid := MutationPolicy{Schema: MutationSchema, ExplicitlyEnabled: true, Operations: []string{"mount.start"}, MountNames: []string{"safeMount"}}
	b, _ := json.Marshal(valid)
	dir := filepath.Join(t.TempDir(), "policy")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	path := filepath.Join(dir, "p3-policy.json")
	if e := os.WriteFile(path, b, 0600); e != nil {
		t.Fatal(e)
	}
	if _, e := loadMutationAt(path, p); e != nil {
		t.Fatal(e)
	}
	if e := os.Chmod(path, 0644); e != nil {
		t.Fatal(e)
	}
	if _, e := loadMutationAt(path, p); e == nil {
		t.Fatal("group-readable operator policy accepted")
	}
	if e := os.Chmod(path, 0600); e != nil {
		t.Fatal(e)
	}
	link := filepath.Join(dir, "alias.json")
	if e := os.Symlink(path, link); e != nil {
		t.Fatal(e)
	}
	if _, e := loadMutationAt(link, p); e == nil {
		t.Fatal("symlinked mutation policy accepted")
	}
	if e := os.Chmod(dir, 0755); e != nil {
		t.Fatal(e)
	}
	if _, e := loadMutationAt(path, p); e == nil {
		t.Fatal("public operator policy directory accepted")
	}
}

func TestAPI04P3TransportIsDistinctAndNeverImplicitlyEnabled(t *testing.T) {
	if mutationEndpoint == Endpoint || mutationEndpoint == "" || mutationEndpoint[0] != 0 {
		t.Fatal("mutation/query endpoints alias")
	}
	if e := (&MutationEndpointServer{}).Start(); e == nil {
		t.Fatal("started without policy/guard")
	}
	s, _, _, _ := mutationFixture(t)
	server := &MutationEndpointServer{Service: s}
	if e := server.Start(); e == nil {
		t.Fatal("started without independent operator opt-in")
	}
}
