package jobs

import (
	"os"
	"path/filepath"
	"testing"
)

func TestAndroidMediaLocalEndpoints(t *testing.T) {
	for _, s := range []string{"/storage/emulated/0/Documents", "/sdcard/Backup", "/mnt/media_rw/XXXX-YYYY/photos", "/data/media/10/Docs", "cloud:path/to/item"} {
		if !validEndpoint(s) {
			t.Errorf("valid job endpoint rejected %q", s)
		}
	}
	for _, s := range []string{"/", "/data/adb/skybind/config", "/etc/shadow", "/proc/self/root", "/storage", "/sdcard", "/sdcard/a/../b", "/sdcard/a//b", "/sdcard/a:evil", "cloud:/etc", "cloud:../../stuff", "cloud:foo//bar", "relative/path", "--delete", "/sdcard/a\\b"} {
		if validEndpoint(s) {
			t.Errorf("unsafe endpoint accepted %q", s)
		}
	}
	_, err := validate(Registry{SchemaVersion: 1, Jobs: []Job{{Name: "nested", Kind: "sync", Source: "/sdcard/Photos", Destination: "/sdcard/Photos/backup"}}})
	if err == nil {
		t.Fatal("nested destructive sync allowed")
	}
	_, err = validate(Registry{SchemaVersion: 1, Jobs: []Job{{Name: "backup", Kind: "copy", Source: "/sdcard/Photos", Destination: "remote:photos"}}})
	if err != nil {
		t.Fatal(err)
	}
}
func TestLocalPathSymlinkEscapeRejected(t *testing.T) {
	// This tests the runtime path gate without relying on Android /sdcard mount.
	// Existing ancestors are checked before executing a root-owned rclone process.
	root := t.TempDir()
	target := filepath.Join(root, "outside")
	if err := os.Mkdir(target, 0700); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(root, "link")
	if err := os.Symlink(target, link); err != nil {
		t.Fatal(err)
	}
	if validEndpoint(link) {
		t.Fatal("nonmedia local directory accepted")
	}
}
