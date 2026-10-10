// Package provider mediates bounded, credential-free rclone discovery and crypt
// provisioning; no generic rclone flags or RC commands cross the RPC boundary.
package provider

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"strings"
	"sync"
	"time"
)

var remoteName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)

type Remote struct {
	Name      string `json:"name"`
	Type      string `json:"type"`
	Encrypted bool   `json:"encrypted"`
}
type Entry struct {
	Path  string `json:"Path"`
	Name  string `json:"Name"`
	Size  int64  `json:"Size"`
	IsDir bool   `json:"IsDir"`
}
type Runner interface {
	Run(ctx context.Context, stdin []byte, argv ...string) ([]byte, error)
}
type commandRunner struct{}

func (commandRunner) Run(ctx context.Context, stdin []byte, argv ...string) ([]byte, error) {
	if len(argv) == 0 {
		return nil, errors.New("missing provider command")
	}
	c := exec.CommandContext(ctx, paths.Engine, argv...)
	c.Env = []string{"PATH=/system/bin:/system/xbin", "HOME=/data/adb/skybind"}
	if stdin != nil {
		c.Stdin = bytes.NewReader(stdin)
	}
	var stdout bytes.Buffer
	c.Stdout = &limitedWriter{w: &stdout, max: 1 << 19}
	c.Stderr = io.Discard
	if err := c.Run(); err != nil {
		return nil, errors.New("provider operation failed")
	}
	return stdout.Bytes(), nil
}

type limitedWriter struct {
	w   io.Writer
	max int
}

func (w *limitedWriter) Write(p []byte) (int, error) {
	if len(p) > w.max {
		return 0, errors.New("provider response exceeds limit")
	}
	n, e := w.w.Write(p)
	w.max -= n
	return n, e
}

type Manager struct {
	mu     sync.Mutex
	dir    string
	runner Runner
	proofs *previewproof.Store
}

func Canonical() *Manager { return New(paths.StateRoot+"/config", commandRunner{}) }
func New(dir string, runner Runner) *Manager {
	return &Manager{dir: dir, runner: runner, proofs: previewproof.New()}
}
func validPath(s string) bool {
	if len(s) > 512 || strings.ContainsAny(s, "\\\x00\r\n") || strings.HasPrefix(s, "/") {
		return false
	}
	if s == "" {
		return true
	}
	for _, p := range strings.Split(s, "/") {
		if p == "" || p == "." || p == ".." || strings.Contains(p, ":") {
			return false
		}
	}
	return true
}
func splitEndpoint(v string) (string, string, error) {
	p := strings.SplitN(v, ":", 2)
	if len(p) != 2 || !remoteName.MatchString(p[0]) || !validPath(p[1]) {
		return "", "", errors.New("invalid remote endpoint")
	}
	return p[0], p[1], nil
}
func parse(data []byte) ([]Remote, error) {
	if len(data) > 1<<18 {
		return nil, errors.New("rclone config oversized")
	}
	var out []Remote
	seen := map[string]bool{}
	current := -1
	for _, line := range strings.Split(string(data), "\n") {
		l := strings.TrimSpace(line)
		if l == "" || strings.HasPrefix(l, "#") || strings.HasPrefix(l, ";") {
			continue
		}
		if strings.HasPrefix(l, "[") && strings.HasSuffix(l, "]") {
			name := strings.TrimSuffix(strings.TrimPrefix(l, "["), "]")
			if !remoteName.MatchString(name) || seen[name] {
				return nil, errors.New("invalid or duplicate remote section")
			}
			seen[name] = true
			out = append(out, Remote{Name: name})
			current = len(out) - 1
			continue
		}
		if current < 0 {
			return nil, errors.New("setting outside remote section")
		}
		parts := strings.SplitN(l, "=", 2)
		if len(parts) != 2 {
			return nil, errors.New("malformed rclone config")
		}
		if strings.TrimSpace(parts[0]) == "type" {
			out[current].Type = strings.TrimSpace(parts[1])
			out[current].Encrypted = out[current].Type == "crypt"
		}
	}
	for _, r := range out {
		if r.Type == "" {
			return nil, errors.New("missing remote type")
		}
	}
	return out, nil
}
func (m *Manager) config() ([]byte, []Remote, error) {
	data, err := atomicfile.Read(m.dir, "rclone.conf", 1<<18)
	if errors.Is(err, os.ErrNotExist) {
		return nil, []Remote{}, nil
	}
	if err != nil {
		return nil, nil, err
	}
	list, err := parse(data)
	return data, list, err
}
func (m *Manager) Status() (any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	_, rs, e := m.config()
	if e != nil {
		return nil, e
	}
	return map[string]any{"ready": true, "remote_count": len(rs), "config_path_redacted": true}, nil
}
func (m *Manager) Remotes() ([]Remote, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	_, rs, e := m.config()
	return rs, e
}
func (m *Manager) Browse(ctx context.Context, endpoint string) ([]Entry, error) {
	n, p, e := splitEndpoint(endpoint)
	if e != nil {
		return nil, e
	}
	m.mu.Lock()
	_, rs, e := m.config()
	m.mu.Unlock()
	if e != nil {
		return nil, e
	}
	found := false
	for _, r := range rs {
		if r.Name == n {
			found = true
		}
	}
	if !found {
		return nil, errors.New("unknown remote")
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	out, e := m.runner.Run(ctx, nil, "--config", paths.RcloneConfig, "lsjson", "--max-depth", "1", "--", n+":"+p)
	if e != nil {
		return nil, e
	}
	if len(out) > 1<<18 {
		return nil, errors.New("listing oversized")
	}
	var entries []Entry
	if e = json.Unmarshal(out, &entries); e != nil {
		return nil, errors.New("invalid listing")
	}
	if len(entries) > 500 {
		return nil, errors.New("too many entries")
	}
	for _, entry := range entries {
		if !validPath(entry.Path) || entry.Name == "" || strings.ContainsAny(entry.Name, "/\\\x00\r\n") || entry.Size < 0 {
			return nil, errors.New("unsafe listing entry")
		}
	}
	return entries, nil
}
func (m *Manager) PasswordStatus() (any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	_, err := atomicfile.Read(m.dir, "crypt-password.txt", 4096)
	if errors.Is(err, os.ErrNotExist) {
		return map[string]bool{"configured": false}, nil
	}
	if err != nil {
		return nil, err
	}
	return map[string]bool{"configured": true}, nil
}
func (m *Manager) PasswordSet(ctx context.Context, password string) (any, error) {
	if len(password) < 12 || len(password) > 1024 || strings.ContainsAny(password, "\r\n\x00") {
		return nil, errors.New("invalid password length or encoding")
	}
	ctx, cancel := context.WithTimeout(ctx, 15*time.Second)
	defer cancel()
	obscured, e := m.runner.Run(ctx, []byte(password+"\n"), "obscure", "-")
	if e != nil {
		return nil, e
	}
	token := strings.TrimSpace(string(obscured))
	if len(token) < 12 || len(token) > 4096 || strings.ContainsAny(token, " \t\r\n:") {
		return nil, errors.New("invalid provider-obscured result")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if e = atomicfile.Write(m.dir, "crypt-password.txt", []byte(token)); e != nil {
		return nil, e
	}
	return map[string]bool{"configured": true}, nil
}
func (m *Manager) RecoveryStatus() any {
	return map[string]any{"password_recoverable": false, "explanation": "Save your own password securely. Rclone obscuring is not encryption; no plaintext recovery is offered."}
}

type CryptSpec struct {
	Name         string `json:"name"`
	Remote       string `json:"remote"`
	FilenameMode string `json:"filename_mode"`
	DirNames     *bool  `json:"directory_names,omitempty"`
	Encoding     string `json:"encoding"`
}

func normalizeCrypt(s CryptSpec) (CryptSpec, error) {
	if !remoteName.MatchString(s.Name) {
		return s, errors.New("invalid crypt name")
	}
	if _, _, e := splitEndpoint(s.Remote); e != nil {
		return s, e
	}
	if s.DirNames == nil {
		yes := true
		s.DirNames = &yes
	}
	if s.FilenameMode == "" {
		s.FilenameMode = "standard"
	}
	if s.Encoding == "" {
		s.Encoding = "base32"
	}
	if s.FilenameMode != "standard" && s.FilenameMode != "obfuscate" && s.FilenameMode != "off" {
		return s, errors.New("invalid filename mode")
	}
	if s.Encoding != "base32" && s.Encoding != "base64" && s.Encoding != "base32768" {
		return s, errors.New("invalid encoding")
	}
	return s, nil
}
func (m *Manager) cryptBase(s CryptSpec) (CryptSpec, []byte, []Remote, string, error) {
	s, e := normalizeCrypt(s)
	if e != nil {
		return s, nil, nil, "", e
	}
	data, remotes, e := m.config()
	if e != nil {
		return s, nil, nil, "", e
	}
	source, _, _ := splitEndpoint(s.Remote)
	if s.Name == source {
		return s, nil, nil, "", errors.New("self crypt")
	}
	present := false
	for _, r := range remotes {
		if r.Name == s.Name {
			return s, nil, nil, "", errors.New("crypt name exists")
		}
		if r.Name == source {
			present = true
			if r.Encrypted {
				return s, nil, nil, "", errors.New("nested crypt disallowed")
			}
		}
	}
	if !present {
		return s, nil, nil, "", errors.New("source remote missing")
	}
	pw, e := atomicfile.Read(m.dir, "crypt-password.txt", 4096)
	if e != nil {
		return s, nil, nil, "", errors.New("password not configured or inaccessible")
	}
	return s, data, remotes, strings.TrimSpace(string(pw)), nil
}
func (m *Manager) CryptPreview(s CryptSpec) (any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, conf, _, _, e := m.cryptBase(s)
	if e != nil {
		return nil, e
	}
	b, _ := json.Marshal(s)
	proof, e := m.proofs.Issue(previewproof.Binding{Action: "crypt.create", Subject: s.Name, Revision: 0, Digest: previewproof.Digest(append(append([]byte{}, conf...), b...))}, 2*time.Minute)
	if e != nil {
		return nil, e
	}
	return map[string]any{"proof": proof, "name": s.Name, "source": s.Remote, "filename_mode": s.FilenameMode, "encoding": s.Encoding, "directory_names": s.DirNames, "password_redacted": true}, nil
}
func (m *Manager) CryptCreate(s CryptSpec, proof string) (any, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	s, conf, _, pw, e := m.cryptBase(s)
	if e != nil {
		return nil, e
	}
	b, _ := json.Marshal(s)
	if e = m.proofs.Consume(proof, previewproof.Binding{Action: "crypt.create", Subject: s.Name, Revision: 0, Digest: previewproof.Digest(append(append([]byte{}, conf...), b...))}); e != nil {
		return nil, e
	}
	// Only append a validated stanza after a fresh proof. Full document is published
	// atomically through the verified private directory, never half configured.
	var out bytes.Buffer
	out.Write(conf)
	if len(conf) > 0 && conf[len(conf)-1] != '\n' {
		out.WriteByte('\n')
	}
	fmt.Fprintf(&out, "\n[%s]\ntype = crypt\nremote = %s\nfilename_encryption = %s\ndirectory_name_encryption = %t\nfilename_encoding = %s\npassword = %s\n", s.Name, s.Remote, s.FilenameMode, *s.DirNames, s.Encoding, pw)
	if out.Len() > 1<<18 {
		return nil, errors.New("config exceeds limit")
	}
	if _, e = parse(out.Bytes()); e != nil {
		return nil, e
	}
	if e = atomicfile.Write(m.dir, "rclone.conf", out.Bytes()); e != nil {
		return nil, e
	}
	return map[string]any{"created": s.Name, "encrypted": true}, nil
}
