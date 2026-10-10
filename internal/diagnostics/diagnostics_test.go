package diagnostics

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func newLog(t *testing.T) *Store {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "logs")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	s, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func TestRedactionAndFilters(t *testing.T) {
	s := newLog(t)
	if e := s.Write("WARN", "rc", "AUTH_FAIL", "Authorization: Bearer supersecret token=mycanary password=hunter2"); e != nil {
		t.Fatal(e)
	}
	logs, e := s.Query(Filter{Level: "WARN", Source: "rc", Search: "NOT_FOUND", Limit: 20})
	if e != nil {
		t.Fatal(e)
	}
	if len(logs) != 0 {
		t.Fatal("search must apply to message")
	}
	logs, e = s.Query(Filter{Level: "WARN", Source: "rc", Limit: 20})
	if e != nil || len(logs) != 1 {
		t.Fatal(e, logs)
	}
	if strings.Contains(strings.ToLower(logs[0].Message), "hunter2") || strings.Contains(logs[0].Message, "mycanary") || strings.Contains(logs[0].Message, "supersecret") {
		t.Fatal("secret leaked:", logs[0].Message)
	}
	b, e := os.ReadFile(s.path)
	if e != nil || strings.Contains(string(b), "hunter2") {
		t.Fatal("log at rest leaked")
	}
}
func TestBoundedAndSymlink(t *testing.T) {
	s := newLog(t)
	if _, e := s.Query(Filter{Limit: 201}); e == nil {
		t.Fatal("unbounded query")
	}
	if e := s.Write("TRACE", "x", "y", "text"); e == nil {
		t.Fatal("unknown level")
	}
	if e := os.Symlink("elsewhere", s.path); e != nil {
		t.Fatal(e)
	}
	if e := s.Write("INFO", "test", "code", "ok"); e == nil {
		t.Fatal("followed malicious log symlink")
	}
}
func TestWeakRootRejected(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "logs")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.Chmod(dir, 0755); e != nil {
		t.Fatal(e)
	}
	if _, e := Open(dir); e == nil {
		t.Fatal("accepted public logs")
	}
}
