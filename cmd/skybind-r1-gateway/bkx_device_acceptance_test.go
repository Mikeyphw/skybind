package main

import (
	"skybind/internal/brokerruntime"
	"strings"
	"testing"
)

func bkxTestPolicy() brokerruntime.Policy {
	return brokerruntime.Policy{Rules: []brokerruntime.Rule{{Consumer: "bkx", Remote: "GDDavys", Prefix: "", Operations: []string{"system.capabilities", "rclone.version", "rclone.listremotes", "rclone.lsjson", "rclone.size"}}}}
}
func TestBKXAcceptanceScopeAndFixedOperations(t *testing.T) {
	p := bkxTestPolicy()
	for _, path := range []string{"", "small", "small/child"} {
		prefix, e := bkxPolicyScope(p, "GDDavys", path)
		if e != nil || prefix != "" {
			t.Fatalf("legitimate path denied %q: %v", path, e)
		}
	}
	for _, tc := range []struct{ remote, path string }{{"BADREMOTE", ""}, {"GDDavys", "../escape"}, {"GDDavys", "a//b"}, {"GDDavys", "/absolute"}, {"GDDavys", "a:b"}, {"GDDavys", "a\\b"}} {
		if _, e := bkxPolicyScope(p, tc.remote, tc.path); e == nil {
			t.Fatalf("unsafe or unapproved acceptance scope: %+v", tc)
		}
	}
	p.Rules[0].Operations = []string{"system.capabilities"}
	if _, e := bkxPolicyScope(p, "GDDavys", ""); e == nil {
		t.Fatal("missing operation approved acceptance")
	}
}
func TestBKXAcceptanceOrderAndNoArbitraryGrant(t *testing.T) {
	if len(bkxCaseOrder) != 12 {
		t.Fatalf("case coverage changed: %v", bkxCaseOrder)
	}
	seen := map[string]bool{}
	for _, name := range bkxCaseOrder {
		if seen[name] {
			t.Fatalf("duplicate case %s", name)
		}
		seen[name] = true
		op := bkxCaseOperation(name)
		if name == "no_token" {
			if op != "" {
				t.Fatal("no-token phase must never issue a grant")
			}
			continue
		}
		if !strings.HasPrefix(op, "system.") && !strings.HasPrefix(op, "rclone.") {
			t.Fatalf("unknown case scope: %s %q", name, op)
		}
	}
	for _, needed := range []string{"wrong_operation", "wrong_remote", "wrong_path", "revocation", "expiry", "positive_list", "positive_size"} {
		if !seen[needed] {
			t.Fatalf("missing security case %s", needed)
		}
	}
	if op := bkxCaseOperation("any_client_selected_operation"); op != "" {
		t.Fatal("client-controlled operation admitted")
	}
}
