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

// Rclone's real cmd/size implementation emits fs and sizeless in addition
// to count and bytes. The earlier fake omitted both, masking a device-only
// decoder rejection. Preserve strict output and unknown-size accounting.
func TestMetadataSizeCanonicalRcloneJSONAndNarrowResponse(t *testing.T) {
	m, f := metadataFixture(t)
	f.size = `{"count":7,"bytes":999,"sizeless":2,"fs":"drive:safe"}`
	raw, e := m.Read(brokeripc.Request{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe"})
	if e != nil {
		t.Fatal(e)
	}
	var output map[string]any
	if e := json.Unmarshal(raw, &output); e != nil {
		t.Fatal(e)
	}
	if !reflect.DeepEqual(output, map[string]any{"count": float64(7), "bytes": float64(999), "sizeless": float64(2)}) {
		t.Fatalf("unexpected sanitized size: %s", raw)
	}
	if strings.Contains(string(raw), "drive") || strings.Contains(string(raw), "fs") {
		t.Fatalf("engine path disclosed: %s", raw)
	}
	// Unknown-size=0 should retain the existing count/bytes result schema.
	f.size = `{"count":7,"bytes":999,"sizeless":0,"fs":"drive:safe"}`
	raw, e = m.Read(brokeripc.Request{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe"})
	if e != nil {
		t.Fatal(e)
	}
	if string(raw) != `{"count":7,"bytes":999}` {
		t.Fatalf("unexpected zero-sizeless payload %s", raw)
	}
	// Remote root is a valid exact target and may be empty.
	f.size = `{"count":0,"bytes":0,"sizeless":0,"fs":"drive:"}`
	if _, e = m.Read(brokeripc.Request{Version: 1, Operation: "rclone.size", Remote: "drive"}); e != nil {
		t.Fatal(e)
	}
}

func TestMetadataSizeRejectsMalformedOrUnexpectedEngineJSON(t *testing.T) {
	m, f := metadataFixture(t)
	for _, bad := range []string{
		`{"bytes":10,"sizeless":0,"fs":"drive:safe"}`,
		`{"count":1,"sizeless":0,"fs":"drive:safe"}`,
		`{"count":null,"bytes":10,"fs":"drive:safe"}`,
		`{"count":1,"bytes":null,"fs":"drive:safe"}`,
		`{"count":-1,"bytes":10,"fs":"drive:safe"}`,
		`{"count":1,"bytes":-1,"fs":"drive:safe"}`,
		`{"count":1,"bytes":10,"sizeless":-1,"fs":"drive:safe"}`,
		`{"count":1,"bytes":10,"sizeless":2,"fs":"drive:safe"}`,
		`{"count":1,"bytes":10,"sizeless":0,"fs":"drive:other"}`,
		`{"count":1,"bytes":10,"sizeless":0,"fs":"other:safe"}`,
		`{"count":1,"bytes":10,"sizeless":0,"fs":null,"token":"secret"}`,
		`{"count":1,"bytes":10,"sizeless":0,"unexpected":1}`,
		`{"count":"1","bytes":10}`, `{"count":1,"bytes":"10"}`,
		`{"count":9223372036854775808,"bytes":0}`,
		`{"count":1,"bytes":10} {"count":1,"bytes":10}`,
		`[]`, `null`, `{`,
	} {
		f.size = bad
		if raw, e := m.Read(brokeripc.Request{Version: 1, Operation: "rclone.size", Remote: "drive", Path: "safe"}); e == nil {
			t.Fatalf("accepted malformed output %q => %s", bad, raw)
		}
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
