package brokerissue

import (
	"errors"
	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
	"testing"
	"time"
)

type verifier struct {
	calls  int
	fail   bool
	mutate bool
	peer   brokergrant.Identity
}

func (v *verifier) VerifyPeer(p brokeripc.KernelPeer) (brokergrant.Identity, error) {
	v.calls++
	if v.fail {
		return brokergrant.Identity{}, errors.New("bad identity")
	}
	if v.mutate && v.calls%2 == 0 {
		return brokergrant.Identity{UID: p.UID, ProcessKey: "reused-pid"}, nil
	}
	return v.peer, nil
}
func TestApprovedExactScopedIssuanceAndRevocation(t *testing.T) {
	peer := brokeripc.KernelPeer{UID: 10089, GID: 10089, PID: 22}
	id := brokergrant.Identity{UID: peer.UID, ProcessKey: "platform-pin-startticks"}
	v := &verifier{peer: id}
	s := brokergrant.New()
	i := &Issuer{Grants: s, Verifier: v, Rules: []Rule{{Caller: id, Remote: "drive", Prefix: "bkx", Operations: []string{"rclone.lsjson"}, MaxTTL: time.Minute}}}
	want := Request{Remote: "drive", Prefix: "bkx", Operations: []string{"rclone.lsjson"}, TTL: time.Second * 30}
	token, r, e := i.IssueForPeer(peer, want)
	if e != nil || token == "" || r.ID == "" || v.calls != 2 {
		t.Fatalf("issue: %v %+v", e, r)
	}
	if e = s.Authorize(token, id, "rclone.lsjson", "drive", "bkx/subdir"); e != nil {
		t.Fatal(e)
	}
	if !s.Revoke(r.ID) || s.Authorize(token, id, "rclone.lsjson", "drive", "bkx/subdir") == nil {
		t.Fatal("revocation failed")
	}
	for _, req := range []Request{{Remote: "other", Prefix: "bkx", Operations: want.Operations, TTL: want.TTL}, {Remote: "drive", Prefix: "bkx2", Operations: want.Operations, TTL: want.TTL}, {Remote: "drive", Prefix: "bkx", Operations: []string{"rclone.cat"}, TTL: want.TTL}, {Remote: "drive", Prefix: "bkx", Operations: want.Operations, TTL: 2 * time.Minute}, {Remote: "drive", Prefix: "bkx", Operations: want.Operations}} {
		if _, _, e = i.IssueForPeer(peer, req); e == nil {
			t.Fatalf("minted unapproved %+v", req)
		}
	}
	v.fail = true
	if _, _, e = i.IssueForPeer(peer, want); e == nil {
		t.Fatal("unverified")
	}
	v.fail = false
	v.calls = 0
	v.mutate = true
	if _, _, e = i.IssueForPeer(peer, want); e == nil {
		t.Fatal("pid reuse authorized")
	}
}
func TestNoRulesOrUnconfiguredAuthority(t *testing.T) {
	p := brokeripc.KernelPeer{UID: 11200}
	v := &verifier{peer: brokergrant.Identity{UID: p.UID, ProcessKey: "x"}}
	for _, i := range []*Issuer{nil, {}, {Verifier: v, Grants: brokergrant.New()}, {Verifier: v, Rules: []Rule{{Caller: v.peer}}}} {
		if _, _, e := i.IssueForPeer(p, Request{}); e == nil {
			t.Fatal("default allow")
		}
	}
}

// A policy permitting five reads must issue a one-op grant when the operator
// approves just one. The other four reads remain forbidden by the grant.
func TestIssueApprovedSubsetNeverWidensGrant(t *testing.T) {
	peer := brokeripc.KernelPeer{UID: 10332, GID: 10332, PID: 6451}
	identity := brokergrant.Identity{UID: peer.UID, ProcessKey: "approved-bkx-incarnation"}
	v := &verifier{peer: identity}
	store := brokergrant.New()
	policyOps := []string{"system.capabilities", "rclone.version", "rclone.listremotes", "rclone.lsjson", "rclone.size"}
	i := &Issuer{Grants: store, Verifier: v, Rules: []Rule{{Caller: identity, Remote: "GDDavys", Prefix: "", Operations: policyOps, MaxTTL: 5 * time.Minute}}}
	request := Request{Remote: "GDDavys", Prefix: "", Operations: []string{"system.capabilities"}, TTL: 60 * time.Second}
	token, receipt, err := i.IssueForPeer(peer, request)
	if err != nil || token == "" || receipt.ID == "" || v.calls != 2 {
		t.Fatalf("valid narrower request denied: err=%v calls=%d", err, v.calls)
	}
	if err := store.Authorize(token, identity, "system.capabilities", "GDDavys", ""); err != nil {
		t.Fatalf("approved read denied: %v", err)
	}
	for _, op := range policyOps[1:] {
		if err := store.Authorize(token, identity, op, "GDDavys", ""); err == nil {
			t.Fatalf("grant silently widened to %q", op)
		}
	}
	if err := store.Authorize(token, identity, "system.capabilities", "other", ""); err == nil {
		t.Fatal("wrong remote accepted")
	}
	if err := store.Authorize(token, brokergrant.Identity{UID: identity.UID, ProcessKey: "other-incarnation"}, "system.capabilities", "GDDavys", ""); err == nil {
		t.Fatal("wrong process accepted")
	}
	if !store.Revoke(receipt.ID) || store.Authorize(token, identity, "system.capabilities", "GDDavys", "") == nil {
		t.Fatal("revocation did not invalidate narrowed grant")
	}
	// A multi-operation subset is valid but still excludes all other policy ops.
	request.Operations = []string{"rclone.lsjson", "rclone.size"}
	token, _, err = i.IssueForPeer(peer, request)
	if err != nil || store.Authorize(token, identity, "rclone.lsjson", "GDDavys", "") != nil ||
		store.Authorize(token, identity, "rclone.size", "GDDavys", "") != nil ||
		store.Authorize(token, identity, "rclone.version", "GDDavys", "") == nil {
		t.Fatalf("multi-subset security violated: %v", err)
	}
}

func TestIssueSubsetRejectsDuplicatesUnknownAndInvalidRules(t *testing.T) {
	base := []string{"system.capabilities", "rclone.lsjson", "rclone.version"}
	for _, tc := range []struct {
		name    string
		policy  []string
		request []string
		allowed bool
	}{
		{"equal-policy", base, base, true},
		{"narrower", base, []string{"rclone.version"}, true},
		{"reordered", base, []string{"rclone.version", "system.capabilities"}, true},
		{"empty-request", base, nil, false},
		{"duplicate-request", base, []string{"rclone.lsjson", "rclone.lsjson"}, false},
		{"unknown-write", base, []string{"rclone.rcat"}, false},
		{"mixed-with-write", base, []string{"rclone.version", "rclone.rcat"}, false},
		{"mixed-with-unknown", base, []string{"rclone.version", "missing"}, false},
		{"duplicate-policy", []string{"rclone.version", "rclone.version"}, []string{"rclone.version"}, false},
		{"empty-policy", nil, []string{"rclone.version"}, false},
		{"empty-policy-operation", []string{"", "rclone.version"}, []string{"rclone.version"}, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := operationsWithinRule(tc.policy, tc.request); got != tc.allowed {
				t.Fatalf("got %t, want %t", got, tc.allowed)
			}
		})
	}
	peer := brokeripc.KernelPeer{UID: 0, GID: 0, PID: 45}
	identity := brokergrant.Identity{UID: 0, ProcessKey: "module-seal-incarnation"}
	store := brokergrant.New()
	i := &Issuer{Grants: store, Verifier: &verifier{peer: identity}, Rules: []Rule{{Caller: identity, Remote: "GDDavys", Prefix: "", Operations: base, MaxTTL: time.Minute}}}
	for _, ops := range [][]string{nil, {"rclone.lsjson", "rclone.lsjson"}, {"rclone.version", "rclone.rcat"}, {"rclone.size"}} {
		token, receipt, err := i.IssueForPeer(peer, Request{Remote: "GDDavys", Operations: ops, TTL: time.Second * 30})
		if err == nil || token != "" || receipt.ID != "" {
			t.Fatalf("invalid ops authorized: %v", ops)
		}
	}
}
