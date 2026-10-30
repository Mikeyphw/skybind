package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestRootCLIStaleRecoveryExplicitShape(t *testing.T) {
	op, body, err := translateDomain([]string{"mount", "stale-preview", "safegdrive"}, strings.NewReader(""))
	if err != nil || op != "mount.stale.preview" {
		t.Fatal(op, err)
	}
	var first map[string]any
	if err = json.Unmarshal(body, &first); err != nil || first["name"] != "safegdrive" {
		t.Fatal(first, err)
	}
	for _, args := range [][]string{
		{"mount", "stale-recover", "safegdrive"},
		{"mount", "stale-recover", "safegdrive", "--operator-approve"},
		{"mount", "stale-recover", "--shell"},
		{"mount", "stale-preview", "--unsafe"},
	} {
		if _, _, err = translateDomain(args, strings.NewReader("")); err == nil {
			t.Fatalf("unreviewed CLI accepted: %v", args)
		}
	}
	payload := `{"name":"safegdrive","proof":"example","operator_approve":true}`
	op, body, err = translateDomain([]string{"mount", "stale-recover", "--stdin"}, strings.NewReader(payload))
	if err != nil || op != "mount.stale.recover" || string(body) != payload {
		t.Fatal(op, err)
	}
}
