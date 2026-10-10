package main

import "testing"

func TestFoundationCommands(t *testing.T) {
	for _, args := range [][]string{{"version"}, {"--version"}, {"paths"}} {
		if run(args) != 0 {
			t.Errorf("failure: %v", args)
		}
	}
	for _, args := range [][]string{{}, {"stop"}, {"mount"}, {"version", "oops"}} {
		if run(args) == 0 {
			t.Errorf("unimplemented operation succeeded: %v", args)
		}
	}
}
