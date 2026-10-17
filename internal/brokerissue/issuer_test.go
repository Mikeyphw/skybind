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
