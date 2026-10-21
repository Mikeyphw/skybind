package brokerruntime

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"skybind/internal/brokeripc"
	"skybind/internal/paths"
	"skybind/internal/provider"
	"strings"
	"testing"
)

type metaFakeRunner struct {
	argv [][]string
	size string
	fail bool
}

func (f *metaFakeRunner) Run(_ context.Context, _ []byte, argv ...string) ([]byte, error) {
	f.argv = append(f.argv, append([]string{}, argv...))
	if f.fail {
		return nil, errors.New("backend unavailable")
	}
	switch {
	case len(argv) > 0 && argv[0] == "version":
		return []byte("rclone v1.72.0\n- os/version\n"), nil
	case len(argv) > 2 && argv[2] == "size":
		return []byte(f.size), nil
	case len(argv) > 2 && argv[2] == "lsjson":
		return []byte(`[ {"Path":"dir","Name":"dir","Size":-1,"IsDir":true} ]`), nil
	default:
		return nil, errors.New("bad typed command")
	}
}
func metadataFixture(t *testing.T) (*Metadata, *metaFakeRunner) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "config")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, "rclone.conf"), []byte("[drive]\ntype = drive\ntoken = SUPERSECRET\n[private]\ntype = crypt\nremote = drive:secret\npassword = ENCRYPTEDSECRET\n"), 0600); e != nil {
		t.Fatal(e)
	}
	f := &metaFakeRunner{size: `{"count":7,"bytes":999}`}
	return &Metadata{Provider: provider.New(dir, f), Runner: f}, f
}
func TestMetadataOperationsReadOnlyAndSanitized(t *testing.T) {
	m, f := metadataFixture(t)
	for _, tc := range []struct {
		op, path string
		expected string
	}{
		{"system.capabilities", "", "read_only"}, {"rclone.listremotes", "", "drive"}, {"rclone.version", "", "rclone v1.72.0"}, {"rclone.lsjson", "safe", "dir"}, {"rclone.size", "safe/file", "999"},
	} {
		t.Run(tc.op, func(t *testing.T) {
			raw, e := m.Read(brokeripc.Request{Version: 1, Operation: tc.op, Remote: "drive", Path: tc.path})
			if e != nil {
				t.Fatal(e)
			}
			if !json.Valid(raw) || !strings.Contains(string(raw), tc.expected) || strings.Contains(string(raw), "SECRET") || strings.Contains(string(raw), "token") || (tc.op == "rclone.listremotes" && strings.Contains(string(raw), "private")) {
				t.Fatalf("unsafe result: %s", raw)
			}
		})
	}
	if !reflect.DeepEqual(f.argv[len(f.argv)-1], []string{"--config", paths.RcloneConfig, "size", "--json", "--", "drive:safe/file"}) {
		t.Fatalf("unapproved size invocation: %v", f.argv)
	}
}
func TestMetadataRefusesUnsafePathsOperationsAndRemote(t *testing.T) {
	m, f := metadataFixture(t)
	for _, r := range []brokeripc.Request{
		{Version: 1, Operation: "rclone.rcat", Remote: "drive", Path: "safe"},
		{Version: 1, Operation: "rclone.deletefile", Remote: "drive", Path: "safe"},
		{Version: 1, Operation: "rclone.lsjson", Remote: "drive", Path: "../private"},
		{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe/../../secret"},
		{Version: 1, Operation: "rclone.size", Remote: "--config", Path: "secret"},
		{Version: 1, Operation: "rclone.size", Remote: "unknown", Path: "secret"},
		{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe:evil"},
		{Version: 2, Operation: "rclone.version", Remote: "drive", Path: ""},
	} {
		if _, e := m.Read(r); e == nil {
			t.Fatalf("accepted unsafe operation %#v", r)
		}
	}
	if len(f.argv) != 0 {
		t.Fatalf("rejected requests invoked provider: %#v", f.argv)
	}
}
func TestMetadataBadSizesAndBackendError(t *testing.T) {
	m, f := metadataFixture(t)
	for _, bad := range []string{`{"count":-1,"bytes":4}`, `{"count":4,"bytes":-1}`, `{"count":2,"bytes":4,"secret":"X"}`, `{"count":2,"bytes":4} {}`, `{`, `[]`} {
		f.size = bad
		if _, e := m.Read(brokeripc.Request{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe"}); e == nil {
			t.Fatalf("accepted bad size %q", bad)
		}
	}
	f.fail = true
	if _, e := m.Read(brokeripc.Request{Version: 1, Operation: "rclone.version", Remote: "drive"}); e == nil {
		t.Fatal("accepted failed engine")
	}
}
