// Package support writes bounded redacted support bundles to a private owned directory.
package support

import (
	"archive/zip"
	"bytes"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"skybind/internal/diagnostics"
	"sort"
	"syscall"
)

const MaxBundle = 1024 * 1024

var idRx = regexp.MustCompile(`^[0-9a-f]{32}$`)

type Store struct{ dir string }
type Meta struct {
	ID     string `json:"id"`
	Bytes  int    `json:"bytes"`
	SHA256 string `json:"sha256"`
}

func Open(dir string) (*Store, error) {
	st, e := os.Lstat(dir)
	if e != nil {
		return nil, e
	}
	if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm() != 0700 {
		return nil, errors.New("unsafe support root")
	}
	return &Store{dir: dir}, nil
}
func (s *Store) Create(parts map[string]any) (Meta, error) {
	if len(parts) > 12 {
		return Meta{}, errors.New("too many support entries")
	}
	names := make([]string, 0, len(parts))
	for n := range parts {
		if n == "" || len(n) > 64 || filepath.Base(n) != n || n == "manifest.json" {
			return Meta{}, errors.New("invalid support entry")
		}
		names = append(names, n)
	}
	sort.Strings(names)
	var buf bytes.Buffer
	w := zip.NewWriter(&buf)
	manifest := map[string]string{}
	for _, n := range names {
		b, e := json.Marshal(parts[n])
		if e != nil {
			return Meta{}, e
		}
		if len(b) > 64*1024 {
			return Meta{}, errors.New("oversized support entry")
		}
		b = []byte(diagnostics.RedactUnbounded(string(b)))
		if len(b) > 64*1024 {
			return Meta{}, errors.New("oversized support entry")
		}
		h := sha256.Sum256(b)
		manifest[n+".json"] = hex.EncodeToString(h[:])
		out, e := w.Create(n + ".json")
		if e != nil {
			return Meta{}, e
		}
		if _, e = out.Write(b); e != nil {
			return Meta{}, e
		}
	}
	m, _ := json.Marshal(manifest)
	out, e := w.Create("manifest.json")
	if e != nil {
		return Meta{}, e
	}
	if _, e = out.Write(m); e != nil {
		return Meta{}, e
	}
	if e = w.Close(); e != nil {
		return Meta{}, e
	}
	if buf.Len() > MaxBundle {
		return Meta{}, errors.New("support bundle too large")
	}
	token := make([]byte, 16)
	if _, e = rand.Read(token); e != nil {
		return Meta{}, e
	}
	id := hex.EncodeToString(token)
	name := filepath.Join(s.dir, id+".zip")
	f, e := os.OpenFile(name, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return Meta{}, e
	}
	_, e = f.Write(buf.Bytes())
	if e == nil {
		e = f.Sync()
	}
	if ce := f.Close(); e == nil {
		e = ce
	}
	if e != nil {
		_ = os.Remove(name)
		return Meta{}, e
	}
	hash := sha256.Sum256(buf.Bytes())
	return Meta{ID: id, Bytes: buf.Len(), SHA256: hex.EncodeToString(hash[:])}, nil
}
func (s *Store) Read(id string) ([]byte, error) {
	if !idRx.MatchString(id) {
		return nil, errors.New("invalid owned bundle id")
	}
	name := filepath.Join(s.dir, id+".zip")
	st, e := os.Lstat(name)
	if e != nil {
		return nil, e
	}
	if !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Size() > MaxBundle {
		return nil, errors.New("unsafe bundle")
	}
	f, e := os.OpenFile(name, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return nil, e
	}
	defer f.Close()
	b, e := io.ReadAll(io.LimitReader(f, MaxBundle+1))
	if e != nil {
		return nil, e
	}
	if len(b) > MaxBundle {
		return nil, errors.New("bundle overflow")
	}
	zr, e := zip.NewReader(bytes.NewReader(b), int64(len(b)))
	if e != nil {
		return nil, e
	}
	manifest := map[string]string{}
	for _, z := range zr.File {
		if z.Name == "manifest.json" {
			r, e := z.Open()
			if e != nil {
				return nil, e
			}
			mb, e := io.ReadAll(io.LimitReader(r, 4096))
			r.Close()
			if e != nil {
				return nil, e
			}
			if e = json.Unmarshal(mb, &manifest); e != nil {
				return nil, e
			}
		}
	}
	if len(manifest) == 0 {
		return nil, errors.New("missing support manifest")
	}
	for _, z := range zr.File {
		if z.Name == "manifest.json" {
			continue
		}
		r, e := z.Open()
		if e != nil {
			return nil, e
		}
		data, e := io.ReadAll(io.LimitReader(r, 65537))
		r.Close()
		if e != nil || len(data) > 65536 {
			return nil, errors.New("support entry overflow")
		}
		hash := sha256.Sum256(data)
		if manifest[z.Name] != hex.EncodeToString(hash[:]) {
			return nil, fmt.Errorf("support hash mismatch: %s", z.Name)
		}
	}
	return b, nil
}
