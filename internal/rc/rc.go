// Package rc exposes only whitelisted metrics from per-mount authenticated
// loopback endpoints. It deliberately contains no generic RC proxy.
package rc

import (
	"context"
	"crypto/rand"
	"crypto/sha1"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/paths"
	"strings"
	"sync"
	"time"
)

var safe = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)

type session struct {
	port     string
	password string
}
type Manager struct {
	mu       sync.Mutex
	dir      string
	sessions map[string]session
	client   *http.Client
	owned    func(string) bool
}

func New(dir string, owned func(string) bool) *Manager {
	return &Manager{dir: dir, sessions: map[string]session{}, owned: owned, client: &http.Client{Timeout: 3 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return errors.New("redirect denied") }}}
}
func Canonical(owned func(string) bool) *Manager {
	return New(filepath.Join(paths.StateRoot, "rc"), owned)
}

// Prepare creates an owner-only htpasswd record. No plaintext password is ever
// present in argv, response JSON, the htpasswd file, or persistent state.
func (m *Manager) Prepare(name string) ([]string, error) {
	if !safe.MatchString(name) {
		return nil, errors.New("invalid RC mount")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	// A freshly launched replacement mount must receive fresh credentials. A
	// healthy mount never calls Prepare twice because lifecycle.Start checks its
	// verified RUNNING state before reaching the launch boundary.
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		return nil, e
	}
	addr := l.Addr().(*net.TCPAddr)
	port := fmt.Sprint(addr.Port)
	l.Close()
	secret := make([]byte, 32)
	if _, e = rand.Read(secret); e != nil {
		return nil, e
	}
	pass := base64.RawURLEncoding.EncodeToString(secret)
	sum := sha1.Sum([]byte(pass))
	record := "skybind:{SHA}" + base64.StdEncoding.EncodeToString(sum[:]) + "\n"
	if e = atomicfile.Write(m.dir, "htpasswd-"+name, []byte(record)); e != nil {
		return nil, e
	}
	m.sessions[name] = session{port: port, password: pass}
	return []string{"--rc", "--rc-addr", "127.0.0.1:" + port, "--rc-htpasswd", filepath.Join(m.dir, "htpasswd-"+name)}, nil
}
func (m *Manager) Drop(name string) {
	m.mu.Lock()
	delete(m.sessions, name)
	m.mu.Unlock()
	if safe.MatchString(name) {
		_ = os.Remove(filepath.Join(m.dir, "htpasswd-"+name))
	}
}
func (m *Manager) Metrics(ctx context.Context, name string) (any, error) {
	if !safe.MatchString(name) {
		return nil, errors.New("invalid mount")
	}
	if m.owned == nil || !m.owned(name) {
		return nil, errors.New("owned running mount required")
	}
	m.mu.Lock()
	s, ok := m.sessions[name]
	m.mu.Unlock()
	if !ok {
		return nil, errors.New("RC credentials unavailable (restart required)")
	}
	// HTTP transport never honors environment proxies or forwards credentials.
	client := *m.client
	client.Transport = &http.Transport{Proxy: nil, DialContext: func(ctx context.Context, network, address string) (net.Conn, error) {
		return (&net.Dialer{Timeout: 2 * time.Second}).DialContext(ctx, "tcp4", "127.0.0.1:"+s.port)
	}}
	output := map[string]any{"mount": name, "authenticated": true}
	for _, endpoint := range []string{"core/stats", "vfs/stats"} {
		req, e := http.NewRequestWithContext(ctx, "POST", "http://127.0.0.1:"+s.port+"/"+endpoint, strings.NewReader("{}"))
		if e != nil {
			return nil, e
		}
		req.SetBasicAuth("skybind", s.password)
		req.Header.Set("Content-Type", "application/json")
		res, e := client.Do(req)
		if e != nil {
			return nil, errors.New("RC endpoint unavailable")
		}
		body, e := io.ReadAll(io.LimitReader(res.Body, 65537))
		res.Body.Close()
		if e != nil || len(body) > 65536 || res.StatusCode != 200 {
			return nil, errors.New("RC telemetry rejected")
		}
		var stats map[string]any
		if e = json.Unmarshal(body, &stats); e != nil {
			return nil, errors.New("invalid RC metrics")
		}
		safeStats := map[string]any{}
		// Never return remote names, credentials, paths, or RC configuration.
		allow := []string{"bytes", "speed", "errors", "checks", "transfers", "elapsedTime", "totalBytes", "used", "inUse", "uploads", "downloads", "diskCache", "maxAge", "maxSize"}
		for _, k := range allow {
			if v, ok := stats[k]; ok {
				switch v.(type) {
				case float64, bool:
					safeStats[k] = v
				}
			}
		}
		if endpoint == "core/stats" {
			output["transfers"] = safeStats
		} else {
			output["vfs"] = safeStats
		}
	}
	return output, nil
}
