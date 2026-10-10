package provider

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestCryptPasswordGenerationsAndRemoteProvenance(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "rclone.conf"), []byte("[main]\ntype = drive\n"), 0600); err != nil {
		t.Fatal(err)
	}
	m := New(dir, &fake{})
	ctx := context.Background()
	if _, err := m.PasswordSet(ctx, "first-password-123456"); err != nil {
		t.Fatal(err)
	}
	spec := CryptSpec{Name: "photos_crypt", Remote: "main:Photos"}
	p, err := m.CryptPreview(spec)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = m.CryptCreate(spec, p.(map[string]any)["proof"].(string)); err != nil {
		t.Fatal(err)
	}
	status := m.RecoveryStatus().(map[string]any)
	if status["password_revision"] != uint64(1) || status["managed_crypt_remotes"] != 1 || status["current_password_remotes"] != 1 || status["provenance_healthy"] != true {
		t.Fatalf("bad initial provenance %#v", status)
	}
	if _, err = m.PasswordSet(ctx, "new-password-654321"); err != nil {
		t.Fatal(err)
	}
	status = m.RecoveryStatus().(map[string]any)
	if status["password_revision"] != uint64(2) || status["older_password_remotes"] != 1 || status["backup_required"] != true {
		t.Fatalf("lost older generation %#v", status)
	}
	md, err := os.ReadFile(filepath.Join(dir, "crypt-metadata-v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(md), "first-password") || strings.Contains(string(md), "new-password") {
		t.Fatal("plaintext password in provenance")
	}
	old, err := m.CryptPreview(CryptSpec{Name: "later", Remote: "main:other"})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = m.PasswordSet(ctx, "third-password-098765"); err != nil {
		t.Fatal(err)
	}
	if _, err = m.CryptCreate(CryptSpec{Name: "later", Remote: "main:other"}, old.(map[string]any)["proof"].(string)); err == nil {
		t.Fatal("password rotation accepted stale preview")
	}
}
func TestCryptUntrackedAndMetadataTamper(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "rclone.conf"), []byte("[drive]\ntype = drive\n[vault]\ntype = crypt\nremote = drive:secure\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "crypt-password.txt"), []byte("obscured_old"), 0600); err != nil {
		t.Fatal(err)
	}
	m := New(dir, &fake{})
	rec := m.RecoveryStatus().(map[string]any)
	if rec["managed_crypt_remotes"] != 0 || rec["unmanaged_crypt_remotes"] != 1 || rec["password_revision"] != nil {
		t.Fatalf("historical state fabricated %#v", rec)
	}
	if _, err := m.PasswordSet(context.Background(), "new-password-123456"); err != nil {
		t.Fatal(err)
	}
	rec = m.RecoveryStatus().(map[string]any)
	if rec["provenance_healthy"] != false {
		t.Fatalf("unknown history hidden %#v", rec)
	}
	if err := os.WriteFile(filepath.Join(dir, "crypt-metadata-v1.json"), []byte(`{"schema_version":1,"password_revision":1,"managed":[{"name":"vault","backing_remote":"drive:secure","password_revision":2,"created_unix":123}]}`), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := m.PasswordSet(context.Background(), "again-password-123456"); err == nil {
		t.Fatal("tampered provenance overwritten")
	}
}
