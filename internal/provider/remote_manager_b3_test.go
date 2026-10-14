package provider

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/paths"
	"strings"
	"testing"
)

type b3Runner struct {
	size   int64
	mkdirs int
	args   [][]string
	list   []Entry
}

func (r *b3Runner) Run(ctx context.Context, input []byte, argv ...string) ([]byte, error) {
	r.args = append(r.args, append([]string(nil), argv...))
	if len(argv) < 5 || argv[0] != "--config" || argv[1] != paths.RcloneConfig {
		return nil, os.ErrInvalid
	}
	switch argv[2] {
	case "lsjson":
		if argv[3] == "--stat" {
			return json.Marshal(Entry{Path: "photo.jpg", Name: "photo.jpg", Size: r.size})
		}
		if argv[3] == "--max-depth" {
			return json.Marshal(r.list)
		}
	case "mkdir":
		r.mkdirs++
		return []byte{}, nil
	}
	return nil, os.ErrInvalid
}
func TestB3MkdirProofReplayAndConfigDrift(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	r := &b3Runner{size: 19}
	if err := os.WriteFile(filepath.Join(root, "rclone.conf"), []byte("[alpha]\ntype=drive\n"), 0600); err != nil {
		t.Fatal(err)
	}
	m := New(root, r)
	v := DirectoryCreate{Endpoint: "alpha:folder/new"}
	prev, err := m.MkdirPreview(ctx, v)
	if err != nil {
		t.Fatal(err)
	}
	proof := prev.(map[string]any)["proof"].(string)
	if _, err = m.MkdirRun(ctx, v, proof); err != nil {
		t.Fatal(err)
	}
	if r.mkdirs != 1 {
		t.Fatalf("mkdir count %d", r.mkdirs)
	}
	args := strings.Join(r.args[len(r.args)-1], " ")
	if !strings.Contains(args, "mkdir -- alpha:folder/new") {
		t.Fatalf("unsafe mkdir argv %s", args)
	}
	if _, err = m.MkdirRun(ctx, v, proof); err == nil {
		t.Fatal("replayed folder proof")
	}
	prev, err = m.MkdirPreview(ctx, v)
	if err != nil {
		t.Fatal(err)
	}
	proof = prev.(map[string]any)["proof"].(string)
	if err = os.WriteFile(filepath.Join(root, "rclone.conf"), []byte("[alpha]\ntype=drive\ntoken=new\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = m.MkdirRun(ctx, v, proof); err == nil {
		t.Fatal("config-drifted folder creation")
	}
	r.list = []Entry{{Name: "new", Path: "new", IsDir: true}}
	if _, err = m.MkdirPreview(ctx, v); err == nil {
		t.Fatal("mkdir target collision not rejected")
	}
	for _, bad := range []string{"unknown:folder/new", "alpha:", "alpha:/etc", "alpha:parent/../new"} {
		if _, err = m.MkdirPreview(ctx, DirectoryCreate{Endpoint: bad}); err == nil {
			t.Errorf("unsafe mkdir target %q", bad)
		}
	}
}
func TestB3MoveFileOnlyAndDestinationCollision(t *testing.T) {
	ctx := context.Background()
	root := t.TempDir()
	if err := os.Chmod(root, 0700); err != nil {
		t.Fatal(err)
	}
	r := &b3Runner{size: 100}
	if err := os.WriteFile(filepath.Join(root, "rclone.conf"), []byte("[alpha]\ntype=drive\n[beta]\ntype=drive\n"), 0600); err != nil {
		t.Fatal(err)
	}
	m := New(root, r)
	fp, err := m.ValidFileMove(ctx, "alpha:original/photo.jpg", "alpha:target/photo.jpg")
	if err != nil || len(fp) != 64 {
		t.Fatal(fp, err)
	}
	r.size = 101
	fp2, err := m.ValidFileMove(ctx, "alpha:original/photo.jpg", "alpha:target/photo.jpg")
	if err != nil || fp2 == fp {
		t.Fatal("file size not proof bound")
	}
	r.list = []Entry{{Name: "photo.jpg", Path: "photo.jpg", IsDir: false}}
	if _, err = m.ValidFileMove(ctx, "alpha:original/photo.jpg", "alpha:target/photo.jpg"); err == nil {
		t.Fatal("existing destination accepted")
	}
	r.list = nil
	if _, err = m.ValidFileMove(ctx, "alpha:original/photo.jpg", "beta:target/photo.jpg"); err == nil {
		t.Fatal("cross-remote move accepted")
	}
}
