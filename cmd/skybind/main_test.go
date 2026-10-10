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
