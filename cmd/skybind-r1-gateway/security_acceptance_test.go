package main

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"skybind/internal/brokerruntime"
)

func TestAcceptanceRemoteScopeAndAlternateNoAlias(t *testing.T) {
	for _, name := range []string{"GDDavys", "A", "remote_test-01", strings.Repeat("A", 63)} {
		if !validAcceptanceRemote(name) {
			t.Fatalf("rejected valid name: %q", name)
		}
		other := alternateRemote(name)
		if other == name || !validAcceptanceRemote(other) {
			t.Fatalf("unsafe wrong-remote probe: %q -> %q", name, other)
		}
	}
	for _, name := range []string{"", "-x", "1foo", "hello.world", "name/evil", "name:evil", strings.Repeat("A", 64), "hello world"} {
		if validAcceptanceRemote(name) {
			t.Fatalf("accepted invalid name: %q", name)
		}
	}
}
func TestAcceptanceResultCannotOverclaimOnMissingAuthorities(t *testing.T) {
	r := runSecurityAcceptance(context.Background(), nil, nil, brokerruntime.Policy{}, "GDDavys")
	if r.State != "BLOCKED" || r.ReleaseQualified || r.ExternalProviderQualified || r.BKXNegativeSocketQualified || r.Cases["precondition"].State != "BLOCKED" {
		t.Fatalf("unsafe report %#v", r)
	}
	raw, e := json.Marshal(r)
	if e != nil || strings.Contains(string(raw), `"token"`) || strings.Contains(string(raw), `"certificate"`) {
		t.Fatalf("secret or invalid receipt: %v", e)
	}
}
func TestAcceptanceStateDoesNotConfuseStoreWithSocket(t *testing.T) {
	for _, bad := range []struct {
		ok   bool
		want string
	}{{false, "BLOCKED"}, {true, "PASS"}} {
		c := acceptanceCaseResult(bad.ok, "attested_installed_chrootctl_production_grant_store", "failed")
		if c.State != bad.want || c.Evidence != "attested_installed_chrootctl_production_grant_store" {
			t.Fatal(c)
		}
	}
}
