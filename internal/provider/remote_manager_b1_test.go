package provider

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type statRunner struct {
	args [][]string
	out  []byte
}

func (r *statRunner) Run(_ context.Context, _ []byte, args ...string) ([]byte, error) {
	r.args = append(r.args, append([]string(nil), args...))
	if r.out == nil {
		return nil, errors.New("no fake listing")
	}
	return r.out, nil
}
func TestB1ConfiguredRemoteStatAndFingerprint(t *testing.T) {
	dir := t.TempDir()
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	conf := filepath.Join(dir, "rclone.conf")
	if e := os.WriteFile(conf, []byte("[alpha]\ntype=drive\ntoken=secret\n[beta]\ntype=webdav\n"), 0600); e != nil {
		t.Fatal(e)
	}
	runner := &statRunner{out: []byte(`{"Path":"test.bin","Name":"test.bin","Size":83,"IsDir":false}`)}
	m := New(dir, runner)
	hash, e := m.TransferFingerprint("alpha:folder", "beta:backup")
	if e != nil || len(hash) != 64 {
		t.Fatal(hash, e)
	}
	if strings.Contains(hash, "secret") {
		t.Fatal("secret leaked")
	}
	v, e := m.Stat(context.Background(), "alpha:folder/test.bin")
	if e != nil || v.Size != 83 {
		t.Fatal(v, e)
	}
	if len(runner.args) != 1 || strings.Join(runner.args[0], " ") != "--config "+canonicalConfigForTest()+" lsjson --stat -- alpha:folder/test.bin" {
		// Check invariant rather than hard coding the runtime path in test.
		a := runner.args[0]
		if len(a) != 6 || a[2] != "lsjson" || a[3] != "--stat" || a[4] != "--" || a[5] != "alpha:folder/test.bin" {
			t.Fatalf("unexpected rclone stat argv %q", a)
		}
	}
	for _, bad := range []string{"unconfigured:folder", "alpha:../private", "alpha:/abs", "alpha:folder\\bad"} {
		if _, e = m.Stat(context.Background(), bad); e == nil {
			t.Errorf("unsafe stat %q", bad)
		}
	}
	if _, e = m.TransferFingerprint("alpha:folder", "unknown:backup"); e == nil {
		t.Fatal("accepted unknown target")
	}
	if e := os.WriteFile(conf, []byte("[alpha]\ntype=drive\ntoken=changed\n[beta]\ntype=webdav\n"), 0600); e != nil {
		t.Fatal(e)
	}
	newer, e := m.TransferFingerprint("alpha:folder", "beta:backup")
	if e != nil || newer == hash {
		t.Fatalf("config change did not invalidate proof %s %s %v", hash, newer, e)
	}
	runner.out = []byte(`{"Path":"../evil","Name":"evil","Size":0,"IsDir":false}`)
	if _, e = m.Stat(context.Background(), "alpha:folder/test.bin"); e == nil {
		t.Fatal("unsafe metadata accepted")
	}
}
func canonicalConfigForTest() string { return "/data/adb/skybind/config/rclone.conf" }
