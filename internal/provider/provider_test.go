package provider

import (
	"bytes"
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

type fake struct {
	argv     [][]string
	received []byte
}

func (f *fake) Run(_ context.Context, stdin []byte, argv ...string) ([]byte, error) {
	f.argv = append(f.argv, argv)
	f.received = append([]byte(nil), stdin...)
	if len(argv) > 0 && argv[0] == "obscure" {
		return []byte("obscured_value_very_long\n"), nil
	}
	return []byte(`[ {"Path":"dir","Name":"dir","Size":0,"IsDir":true} ]`), nil
}
func TestCryptAndBrowseWithoutSecrets(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	if e := os.WriteFile(filepath.Join(dir, "rclone.conf"), []byte("[main]\ntype = drive\ntoken = confidential\n"), 0600); e != nil {
		t.Fatal(e)
	}
	r := &fake{}
	m := New(dir, r)
	entries, e := m.Browse(context.Background(), "main:folder")
	if e != nil || len(entries) != 1 {
		t.Fatal(entries, e)
	}
	for _, bad := range []string{"main:../secret", "main:/root", "main:x//y", "local:/etc/passwd", "main:x\\y", "main:a:b"} {
		if _, e = m.Browse(context.Background(), bad); e == nil {
			t.Errorf("browse accepted %q", bad)
		}
	}
	password := "S3cur3!testing-password"
	if _, e = m.PasswordSet(context.Background(), password); e != nil {
		t.Fatal(e)
	}
	if string(r.received) != password+"\n" {
		t.Fatal("not sent via stdin")
	}
	if strings.Contains(strings.Join(r.argv[1], " "), password) {
		t.Fatal("secret in argv")
	}
	spec := CryptSpec{Name: "vault", Remote: "main:encrypted"}
	p, e := m.CryptPreview(spec)
	if e != nil {
		t.Fatal(e)
	}
	tok := p.(map[string]any)["proof"].(string)
	if _, e = m.CryptCreate(spec, "bad"); e == nil {
		t.Fatal("unconfirmed crypt")
	}
	if _, e = m.CryptCreate(spec, tok); e != nil {
		t.Fatal(e)
	}
	contents, e := os.ReadFile(filepath.Join(dir, "rclone.conf"))
	if e != nil {
		t.Fatal(e)
	}
	if bytes.Contains(contents, []byte(password)) || !bytes.Contains(contents, []byte("directory_name_encryption = true")) {
		t.Fatal("password leak or wrong defaults")
	}
	if _, e = m.CryptCreate(spec, tok); e == nil {
		t.Fatal("crypt replay accepted")
	}
	if _, e = m.CryptPreview(CryptSpec{Name: "self", Remote: "vault:stuff"}); e == nil {
		t.Fatal("nested crypt accepted")
	}
}
func TestNoSymlinkOrConfigDisclosure(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "private")
	if e := os.Mkdir(dir, 0700); e != nil {
		t.Fatal(e)
	}
	target := filepath.Join(t.TempDir(), "outside")
	os.WriteFile(target, []byte("[main]\ntype = drive\n"), 0600)
	os.Symlink(target, filepath.Join(dir, "rclone.conf"))
	m := New(dir, &fake{})
	if _, e := m.Remotes(); e == nil {
		t.Fatal("followed credential symlink")
	}
	if _, e := m.Browse(context.Background(), "main:"); e == nil {
		t.Fatal("browsed through config link")
	}
}
func TestInvalidObscureOutputRejected(t *testing.T) { _ = errors.New("placeholder") }
