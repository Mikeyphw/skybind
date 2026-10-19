package provider

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

// A deliberately static fake; test never invokes rclone or a live remote.
type unknownDirectorySizeRunner struct{ listing []Entry }

func (r unknownDirectorySizeRunner) Run(_ context.Context, _ []byte, argv ...string) ([]byte, error) {
	if len(argv) != 7 || argv[2] != "lsjson" || argv[6] != "fixture:" {
		panic("provider browse unexpectedly changed the bounded lsjson command")
	}
	return json.Marshal(r.listing)
}

func browseSizeFixture(t *testing.T, entries []Entry) ([]Entry, error) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "private")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "rclone.conf"), []byte("[fixture]\ntype = local\n"), 0600); err != nil {
		t.Fatal(err)
	}
	return New(dir, unknownDirectorySizeRunner{entries}).Browse(context.Background(), "fixture:")
}

func TestBrowseAcceptsRcloneUnknownDirectorySize(t *testing.T) {
	// Real device evidence 2026-10-19: 23 items, seven directories with Size=-1.
	fixture := make([]Entry, 0, 23)
	for i := 0; i < 23; i++ {
		name := "item"
		if i < 7 {
			name = "dir"
		}
		name += string(rune('A' + i))
		directory, size := i < 7, int64(2048)
		if directory {
			size = -1
		}
		fixture = append(fixture, Entry{Path: name, Name: name, IsDir: directory, Size: size})
	}
	got, err := browseSizeFixture(t, fixture)
	if err != nil || len(got) != 23 {
		t.Fatalf("valid bounded listing rejected: count=%d error=%v", len(got), err)
	}
	for i := 0; i < 7; i++ {
		if !got[i].IsDir || got[i].Size != -1 {
			t.Fatalf("directory unknown-size marker changed: %+v", got[i])
		}
	}
}

func TestBrowseRejectsInvalidNegativeSizes(t *testing.T) {
	cases := []struct {
		name    string
		dir     bool
		size    int64
		allowed bool
	}{
		{"file negative one", false, -1, false},
		{"file negative two", false, -2, false},
		{"directory negative two", true, -2, false},
		{"directory unknown one", true, -1, true},
		{"directory zero", true, 0, true},
		{"file zero", false, 0, true},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			entries, err := browseSizeFixture(t, []Entry{{Path: "entry", Name: "entry", Size: tc.size, IsDir: tc.dir}})
			if tc.allowed && (err != nil || len(entries) != 1) {
				t.Fatalf("valid size rejected: %v", err)
			}
			if !tc.allowed && err == nil {
				t.Fatal("invalid negative size accepted")
			}
		})
	}
}
