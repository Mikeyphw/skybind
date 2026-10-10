package main

import (
	"encoding/json"
	"testing"
)

func TestFPHotfixCLIHealthAndReconcileSchemas(t *testing.T) {
	for _, tc := range []struct {
		args []string
		op   string
		want map[string]string
	}{
		{[]string{"mount", "health", "photos"}, "mount.health", map[string]string{"name": "photos"}},
		{[]string{"mount", "reconcile"}, "mount.reconcile", map[string]string{}},
		{[]string{"mount", "stop", "photos"}, "mount.stop", map[string]string{"name": "photos"}},
	} {
		op, raw, err := translateDomain(tc.args, nil)
		if err != nil || op != tc.op {
			t.Fatalf("%v: op=%s err=%v", tc.args, op, err)
		}
		var obj map[string]string
		if err := json.Unmarshal(raw, &obj); err != nil || len(obj) != len(tc.want) {
			t.Fatalf("%v produced invalid arguments %s: %v", tc.args, raw, err)
		}
		for k, v := range tc.want {
			if obj[k] != v {
				t.Fatalf("%v: %q=%q want %q", tc.args, k, obj[k], v)
			}
		}
	}
	for _, args := range [][]string{{"mount", "health"}, {"mount", "health", "photos", "extra"}, {"mount", "reconcile", "photos"}} {
		if _, _, err := translateDomain(args, nil); err == nil {
			t.Fatalf("invalid arguments accepted: %v", args)
		}
	}
}
