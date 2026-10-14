package main

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestDomainCLIHasFixedOperations(t *testing.T) {
	cases := []struct {
		args []string
		op   string
	}{
		{[]string{"mount", "list"}, "mount.list"},
		{[]string{"mount", "status", "photos"}, "mount.status"},
		{[]string{"jobs", "list"}, "jobs.snapshot"},
		{[]string{"job", "preview", "backup"}, "job.run.preview"},
		{[]string{"remotes", "browse", "drive:foo"}, "provider.browse"},
		{[]string{"remotes", "ls", "drive:foo"}, "remote.list"},
		{[]string{"remotes", "stat", "drive:foo/item"}, "remote.stat"},
		{[]string{"crypt", "recovery"}, "provider.crypt.recovery.status"},
		{[]string{"doctor", "report"}, "doctor.report"},
		{[]string{"platform", "status"}, "platform.status"},
		{[]string{"namespace", "inspect", "photos"}, "namespace.inspect"},
	}
	for _, v := range cases {
		var captured string
		status := domainCommand(v.args, strings.NewReader(""), func(op string, payload []byte) int {
			captured = op
			if !json.Valid(payload) {
				t.Error("invalid JSON")
			}
			return 0
		})
		if status != 0 || captured != v.op {
			t.Fatalf("%v -> %v %s", v.args, status, captured)
		}
	}
	for _, args := range [][]string{{"crypt", "password", "set", "secret-in-argv"}, {"mount", "stop", "--everything"}, {"jobs", "apply", "{}"}, {"mount", "restart"}, {"crypt", "create", "--exec"}} {
		if domainCommand(args, bytes.NewReader(nil), func(_ string, _ []byte) int { t.Fatal("bad request dispatched"); return 0 }) != 2 {
			t.Fatal("invalid command allowed", args)
		}
	}
	if run([]string{"rpc", "provider.crypt.password.set", "run", `{"password":"plain-in-process-args"}`}) != 2 {
		t.Fatal("generic RPC exposed password")
	}
	if run([]string{"operation", "provider.crypt.password.set", `{"password":"plain-in-process-args"}`}) != 2 {
		t.Fatal("generic operation exposed password")
	}
}
func TestSecretOnlyFromBoundedStdin(t *testing.T) {
	const secret = "very-private-password-0123"
	op, body, err := translateDomain([]string{"crypt", "password", "set", "--stdin"}, strings.NewReader(secret+"\n"))
	if err != nil || op != "provider.crypt.password.set" {
		t.Fatal(err, op)
	}
	var p map[string]string
	if err = json.Unmarshal(body, &p); err != nil || p["password"] != secret {
		t.Fatal("stdin secret lost")
	}
	for _, password := range []string{"short", strings.Repeat("x", 1030), "secret\nextra\n", "abcd\r123456789"} {
		if _, _, err = translateDomain([]string{"crypt", "password", "set", "--stdin"}, strings.NewReader(password)); err == nil {
			t.Fatal("unsafe stdin accepted")
		}
	}
}

func TestB1RemoteTransferCLIUsesBoundedJSON(t *testing.T) {
	payload := `{"kind":"copy","source":"alpha:src","destination":"beta:dst"}`
	for _, tc := range []struct {
		args []string
		op   string
	}{
		{[]string{"remotes", "transfer-preview", "--stdin"}, "remote.transfer.preview"},
		{[]string{"remotes", "transfer-start", "--stdin"}, "remote.transfer.start"},
	} {
		name, raw, err := translateDomain(tc.args, strings.NewReader(payload))
		if err != nil || name != tc.op || string(raw) != payload {
			t.Fatalf("bad B1 command: %q %v", name, err)
		}
	}
	for _, v := range [][]string{{"remotes", "transfer-start", "--exec"}, {"remotes", "ls", "--flag"}, {"remotes", "stat"}} {
		if _, _, err := translateDomain(v, strings.NewReader("")); err == nil {
			t.Fatalf("accepted unknown flags %v", v)
		}
	}
}
