package brokergrant

import (
	"strings"
	"testing"
	"time"
)

func TestDenyAndScopedGrant(t *testing.T) {
	now := time.Date(2026, 10, 16, 0, 0, 0, 0, time.UTC)
	s := NewWithClock(func() time.Time { return now })
	peer := Identity{UID: 10234, ProcessKey: "verified-bkx-apk-signing-and-process-identity"}
	token, r, err := s.Issue(GrantSpec{Caller: peer, Remote: "drive", Prefix: "bkx/repo", Operations: []string{"rclone.lsjson"}, TTL: time.Minute})
	if err != nil || len(token) != 64 || len(r.ID) != 32 {
		t.Fatal(err, r)
	}
	valid := []string{"bkx/repo", "bkx/repo/item", "bkx/repo/folder/file"}
	for _, p := range valid {
		if err := s.Authorize(token, peer, "rclone.lsjson", "drive", p); err != nil {
			t.Fatal(p, err)
		}
	}
	for _, p := range []string{"bkx/repotwo", "bkx", "bkx/repo/../outside", "bkx/repo//x", "bkx/repo/%2e%2e/secret", "/bkx/repo", "bkx/repo?token=secret", "bkx/repo\\outside"} {
		if s.Authorize(token, peer, "rclone.lsjson", "drive", p) == nil {
			t.Fatal("accepted", p)
		}
	}
	for _, attempt := range []struct {
		token            string
		peer             Identity
		op, remote, path string
	}{
		{"", peer, "rclone.lsjson", "drive", "bkx/repo"},
		{strings.Repeat("0", 64), peer, "rclone.lsjson", "drive", "bkx/repo"},
		{token, Identity{UID: 0, ProcessKey: peer.ProcessKey}, "rclone.lsjson", "drive", "bkx/repo"},
		{token, Identity{UID: peer.UID, ProcessKey: "unverified-other-app"}, "rclone.lsjson", "drive", "bkx/repo"},
		{token, peer, "config.snapshot", "drive", "bkx/repo"},
		{token, peer, "rclone.rcat", "drive", "bkx/repo"},
		{token, peer, "rclone.lsjson", "other", "bkx/repo"},
		{token, peer, "rclone.size", "drive", "bkx/repo"},
	} {
		if s.Authorize(attempt.token, attempt.peer, attempt.op, attempt.remote, attempt.path) == nil {
			t.Fatalf("authorized unexpected request: %q", attempt.op)
		}
	}
	if !s.Revoke(r.ID) || s.Authorize(token, peer, "rclone.lsjson", "drive", "bkx/repo") == nil || s.Revoke(r.ID) {
		t.Fatal("revocation not immediate")
	}
}
func TestExpiryAndInvalidGrantDenial(t *testing.T) {
	now := time.Now()
	s := NewWithClock(func() time.Time { return now })
	peer := Identity{UID: 0, ProcessKey: "sealed-chrootctl-root-module"}
	cases := []GrantSpec{{Caller: peer, Remote: "drive", Prefix: "a", Operations: []string{"rclone.deletefile"}, TTL: time.Second},
		{Caller: peer, Remote: "drive", Prefix: "../data", Operations: []string{"rclone.lsjson"}, TTL: time.Second},
		{Caller: peer, Remote: "drive", Prefix: "a", Operations: []string{"rclone.lsjson"}, TTL: 0},
		{Caller: peer, Remote: "drive", Prefix: "a", Operations: []string{"rclone.lsjson"}, TTL: 25 * time.Hour},
		{Caller: Identity{UID: 0}, Remote: "drive", Prefix: "a", Operations: []string{"rclone.lsjson"}, TTL: time.Second},
		{Caller: peer, Remote: "evil:name", Prefix: "a", Operations: []string{"rclone.lsjson"}, TTL: time.Second}}
	for _, v := range cases {
		if _, _, err := s.Issue(v); err == nil {
			t.Fatal("issued invalid grant", v)
		}
	}
	tok, _, err := s.Issue(GrantSpec{Caller: peer, Remote: "drive", Prefix: "", Operations: []string{"rclone.version"}, TTL: time.Second})
	if err != nil {
		t.Fatal(err)
	}
	if err := s.Authorize(tok, peer, "rclone.version", "drive", ""); err != nil {
		t.Fatal(err)
	}
	now = now.Add(time.Second)
	if s.Authorize(tok, peer, "rclone.version", "drive", "") == nil {
		t.Fatal("expired grant accepted")
	}
}
