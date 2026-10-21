package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

func TestInstalledModuleSealAndActualProcess(t *testing.T) {
	if os.Geteuid() != 0 {
		t.Skip("root-owned fixture needs root")
	}
	d := t.TempDir()
	root := filepath.Join(d, "module")
	proc := filepath.Join(d, "proc")
	for _, rel := range []string{"config/chrootctl", "runtime/arm64-v8a"} {
		if e := os.MkdirAll(filepath.Join(root, rel), 0700); e != nil {
			t.Fatal(e)
		}
	}
	bin := filepath.Join(root, chrootEntry)
	data := []byte(strings.Repeat("ELF-TEST", 128))
	if e := os.WriteFile(bin, data, 0755); e != nil {
		t.Fatal(e)
	}
	hash := sha256.Sum256(data)
	m := map[string]any{"schemaVersion": 1, "moduleId": "chrootctl", "runtimeAbi": "arm64-v8a", "runtimeEntrypoint": "chrootctl", "files": []any{map[string]any{"path": chrootEntry, "size": len(data), "sha256": hex.EncodeToString(hash[:]), "mode": "0755", "executable": true}}}
	raw, _ := json.Marshal(m)
	manifest := filepath.Join(root, chrootManifest)
	if e := os.WriteFile(manifest, raw, 0644); e != nil {
		t.Fatal(e)
	}
	seal := sha256.Sum256(raw)
	pin := ModulePin{Name: "chrootctl", ModuleSealSHA256: hex.EncodeToString(seal[:]), SELinuxContext: "u:r:su:s0"}
	const pid = 732
	if e := os.MkdirAll(filepath.Join(proc, strconv.Itoa(pid)), 0700); e != nil {
		t.Fatal(e)
	}
	link := filepath.Join(proc, strconv.Itoa(pid), "exe")
	if e := os.Symlink(bin, link); e != nil {
		t.Fatal(e)
	}
	att := InstalledModuleAttestor{Root: root, ProcRoot: proc}
	if e := att.VerifyModuleProcess(context.Background(), pid, pin); e != nil {
		t.Fatal("valid approved module rejected", e)
	}
	for _, tc := range []struct {
		name    string
		breakIt func()
		restore func()
	}{
		{"pin-revoked", func() { pin.ModuleSealSHA256 = strings.Repeat("0", 64) }, func() { pin.ModuleSealSHA256 = hex.EncodeToString(seal[:]) }},
		{"binary-modified", func() { _ = os.WriteFile(bin, []byte("tampered"), 0755) }, func() { _ = os.WriteFile(bin, data, 0755) }},
		{"manifest-modified", func() { _ = os.WriteFile(manifest, []byte("{}"), 0644) }, func() { _ = os.WriteFile(manifest, raw, 0644) }},
		{"other-executable", func() { _ = os.Remove(link); _ = os.Symlink(manifest, link) }, func() { _ = os.Remove(link); _ = os.Symlink(bin, link) }},
		{"untrusted-mode", func() { _ = os.Chmod(bin, 0777) }, func() { _ = os.Chmod(bin, 0755) }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			tc.breakIt()
			if att.VerifyModuleProcess(context.Background(), pid, pin) == nil {
				t.Fatal("unapproved process accepted")
			}
			tc.restore()
		})
	}
	if att.VerifyModuleProcess(context.Background(), pid, pin) != nil {
		t.Fatal("failed to restore")
	}
}
