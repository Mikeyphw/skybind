package main

import (
	"testing"
)

func TestCLIRejectsUntrustedOperation(t *testing.T) {
	if run([]string{"rpc", "runtime.status", "file", "{}"}) != 2 {
		t.Fatal("arbitrary class allowed")
	}
	if run([]string{"rpc", "shell.exec", "run", "{"}) != 2 {
		t.Fatal("malformed JSON allowed")
	}
}
func TestOperationShorthandRefusesUnregisteredOrMismatched(t *testing.T) {
	if run([]string{"operation", "shell.exec", "{}"}) != 2 {
		t.Fatal("arbitrary operation allowed")
	}
	if run([]string{"rpc", "mount.start", "query", "{}"}) != 2 {
		t.Fatal("wrong registered class allowed")
	}
	if run([]string{"rpc", "config.apply", "run", "{"}) != 2 {
		t.Fatal("malformed candidate payload allowed")
	}
}
