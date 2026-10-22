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

func TestBKXAndroidInstrumentationEnvironment(t *testing.T) {
	got := bkxInstrumentationEnv([]string{
		"PATH=/data/data/com.termux/files/usr/bin", "HOME=/data/data/com.termux/files/home",
		"LD_PRELOAD=/data/data/com.termux/lib.so", "CLASSPATH=/bad",
		"ANDROID_ROOT=/evil", "ANDROID_DATA=/evil",
		"ANDROID_RUNTIME_ROOT=/apex/com.android.runtime", "BOOTCLASSPATH=/apex/ok.jar",
		"ANDROID_RUNTIME_ROOT=/evil", "TERMUX_VERSION=invalid",
	})
	joined := strings.Join(got, "\n")
	for _, required := range []string{
		"PATH=/system/bin:/system/xbin", "HOME=/data/adb/skybind",
		"ANDROID_ROOT=/system", "ANDROID_DATA=/data",
		"ANDROID_RUNTIME_ROOT=/apex/com.android.runtime", "BOOTCLASSPATH=/apex/ok.jar",
	} {
		if !strings.Contains(joined, required) {
			t.Fatalf("lost Android variable %q: %v", required, got)
		}
	}
	for _, rejected := range []string{"LD_PRELOAD=", "\nCLASSPATH=", "ANDROID_ROOT=/evil", "TERMUX_VERSION=", "ANDROID_RUNTIME_ROOT=/evil"} {
		if strings.Contains(joined, rejected) {
			t.Fatalf("Termux env contamination %q: %v", rejected, got)
		}
	}
}

func TestBKXInstrumentationTerminalCannotAcceptFailedJUnit(t *testing.T) {
	failed := []byte("INSTRUMENTATION_STATUS_CODE: -2\nFAILURES!!!\nINSTRUMENTATION_CODE: -1\n")
	if bkxInstrumentationTerminalPassed(failed) {
		t.Fatal("Android's -1 falsely qualified a failed JUnit")
	}
	if got := bkxInstrumentationFailureCategory(failed, nil); got != "instrumentation_junit_failed" {
		t.Fatalf("wrong failure class: %s", got)
	}
	if bkxInstrumentationTerminalPassed([]byte("INSTRUMENTATION_CODE: -1")) {
		t.Fatal("missing JUnit pass marker qualified")
	}
	if !bkxInstrumentationTerminalPassed([]byte("Time: 1.0\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n")) {
		t.Fatal("correct JUnit pass not recognized")
	}
	if got := bkxInstrumentationFailureCategory([]byte("java.io.IOException: Connection refused"), nil); got != "instrumentation_socket_connection_refused" {
		t.Fatalf("socket outcome miscategorized: %s", got)
	}
}
