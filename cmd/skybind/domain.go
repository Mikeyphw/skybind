package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"skybind/internal/control"
	"strings"
)

// domainCommand routes fixed, human-friendly commands to the exact typed backend
// catalog. No arbitrary shell commands, flags or rclone argv are accepted.
func domainCommand(args []string, input io.Reader, invoke func(string, []byte) int) int {
	op, payload, err := translateDomain(args, input)
	if err != nil {
		fmt.Fprintln(os.Stderr, "Skybind command:", err)
		return 2
	}
	if _, ok := control.Lookup(op); !ok {
		return 2
	}
	return invoke(op, payload)
}
func translateDomain(args []string, input io.Reader) (string, []byte, error) {
	if len(args) < 2 {
		return "", nil, errors.New("missing subcommand; use skybind help")
	}
	group, sub := args[0], args[1]
	tail := args[2:]
	empty := func(op string) (string, []byte, error) {
		if len(tail) != 0 {
			return "", nil, errors.New("unexpected arguments")
		}
		return op, []byte(`{}`), nil
	}
	named := func(op string) (string, []byte, error) {
		if len(tail) != 1 || tail[0] == "" || strings.HasPrefix(tail[0], "-") {
			return "", nil, errors.New("expected one name")
		}
		b, _ := json.Marshal(map[string]string{"name": tail[0]})
		return op, b, nil
	}
	inputObj := func(op string) (string, []byte, error) {
		if len(tail) != 1 || tail[0] != "--stdin" {
			return "", nil, errors.New("read bounded JSON object using --stdin")
		}
		raw, err := readBounded(input, 1<<18)
		if err != nil {
			return "", nil, err
		}
		var v map[string]json.RawMessage
		if err = json.Unmarshal(raw, &v); err != nil || v == nil {
			return "", nil, errors.New("expected JSON object on stdin")
		}
		return op, raw, nil
	}
	switch group {
	case "mount":
		switch sub {
		case "list":
			return empty("mount.list")
		case "status":
			return named("mount.status")
		case "health":
			return named("mount.health")
		case "preview":
			return named("mount.start.preview")
		case "start":
			return inputObj("mount.start")
		case "stop":
			return named("mount.stop")
		case "restart":
			return named("mount.restart")
		case "reconcile":
			return empty("mount.reconcile")
		}
	case "jobs":
		switch sub {
		case "list":
			return empty("jobs.snapshot")
		case "status":
			return empty("jobs.status")
		case "preview":
			return inputObj("jobs.preview")
		case "apply":
			return inputObj("jobs.apply")
		}
	case "job":
		switch sub {
		case "preview":
			return named("job.run.preview")
		case "run":
			return inputObj("job.run")
		}
	case "crypt":
		switch sub {
		case "recovery":
			return empty("provider.crypt.recovery.status")
		case "preview":
			return inputObj("provider.crypt.preview")
		case "create":
			return inputObj("provider.crypt.create")
		case "password":
			if len(tail) == 1 && tail[0] == "status" {
				return "provider.crypt.password.status", []byte(`{}`), nil
			}
			if len(tail) != 2 || tail[0] != "set" || tail[1] != "--stdin" {
				return "", nil, errors.New("crypt password status | password set --stdin")
			}
			// Reject interactive tty entry because it could echo secrets to terminal.
			if input == os.Stdin {
				if st, err := os.Stdin.Stat(); err == nil && st.Mode()&os.ModeCharDevice != 0 {
					return "", nil, errors.New("password requires a protected stdin pipe")
				}
			}
			raw, err := readBounded(input, 1025)
			if err != nil {
				return "", nil, err
			}
			pw := strings.TrimSuffix(string(raw), "\n")
			if strings.HasSuffix(pw, "\r") {
				return "", nil, errors.New("password contains a carriage return")
			}
			if len(pw) < 12 || len(pw) > 1024 || strings.ContainsAny(pw, "\x00\r\n") {
				return "", nil, errors.New("invalid password length or encoding")
			}
			b, _ := json.Marshal(map[string]string{"password": pw})
			return "provider.crypt.password.set", b, nil
		}
	case "remotes":
		switch sub {
		case "ls", "stat":
			if len(tail) != 1 || strings.HasPrefix(tail[0], "-") {
				return "", nil, errors.New("expected configured remote:path")
			}
			b, _ := json.Marshal(map[string]string{"endpoint": tail[0]})
			if sub == "ls" {
				return "remote.list", b, nil
			}
			return "remote.stat", b, nil
		case "transfer-preview":
			return inputObj("remote.transfer.preview")
		case "transfer-start":
			return inputObj("remote.transfer.start")
		case "list":
			return empty("provider.remotes")
		case "status":
			return empty("provider.status")
		case "browse":
			if len(tail) != 1 || strings.HasPrefix(tail[0], "-") {
				return "", nil, errors.New("expected remote:path")
			}
			b, _ := json.Marshal(map[string]string{"remote": tail[0]})
			return "provider.browse", b, nil
		}
	case "doctor":
		switch sub {
		case "report":
			return empty("doctor.report")
		case "bundle":
			return empty("doctor.bundle")
		}
	case "platform":
		if sub == "status" {
			return empty("platform.status")
		}
	case "runtime":
		if sub == "status" {
			return empty("runtime.status")
		}
	case "namespace":
		switch sub {
		case "inspect":
			return named("namespace.inspect")
		case "preview":
			return inputObj("namespace.preview")
		case "apply":
			return inputObj("namespace.apply")
		case "rollback-preview":
			return named("namespace.rollback.preview")
		case "rollback":
			return inputObj("namespace.rollback")
		case "reconcile":
			return named("namespace.reconcile")
		}
	case "operations":
		switch sub {
		case "events":
			return inputObj("operation.events")
		case "status":
			return inputObj("operation.status")
		case "cancel":
			return inputObj("operation.cancel")
		case "list":
			return empty("operation.list")
		}
	case "rc":
		if sub == "metrics" {
			return named("rc.metrics")
		}
	}
	return "", nil, errors.New("unknown subcommand")
}
func readBounded(r io.Reader, limit int64) ([]byte, error) {
	b, err := io.ReadAll(io.LimitReader(r, limit+1))
	if err != nil {
		return nil, errors.New("unable to read stdin")
	}
	if len(b) == 0 || int64(len(b)) > limit {
		return nil, errors.New("missing or oversized stdin")
	}
	return b, nil
}
