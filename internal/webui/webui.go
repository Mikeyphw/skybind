// Package webui exposes the same typed daemon RPC via restricted loopback HTTP
// and a fixed base64url bridge for root-manager WebViews.
package webui

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"skybind/internal/control"
	"skybind/internal/daemon"
	"skybind/internal/protocol"
	"strings"
	"sync"
	"time"
)

const maxBridge = protocol.MaxEnvelope * 2
const sessionTTL = 15 * time.Minute

var validName = func(s string) bool {
	if len(s) == 0 || len(s) > 90 {
		return false
	}
	for _, r := range s {
		if !(r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '.' || r == '_' || r == '-') {
			return false
		}
	}
	return true
}

type CallFunc func(context.Context, protocol.Request) (protocol.Response, error)

func DaemonCaller(socket string) CallFunc {
	return func(ctx context.Context, r protocol.Request) (protocol.Response, error) {
		return daemon.Call(ctx, socket, r)
	}
}
func newSecret() (string, error) {
	b := make([]byte, 32)
	if _, e := rand.Read(b); e != nil {
		return "", e
	}
	return hex.EncodeToString(b), nil
}
func eq(a, b string) bool {
	if len(a) != len(b) || len(a) == 0 {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

type bridgeRequest struct {
	SchemaVersion int    `json:"schema_version"`
	RequestID     string `json:"request_id"`
	Client        struct {
		Name     string `json:"name"`
		Version  string `json:"version"`
		Protocol struct {
			Min int `json:"min"`
			Max int `json:"max"`
		} `json:"protocol"`
	} `json:"client"`
	Operation struct {
		Name  string          `json:"name"`
		Class protocol.Class  `json:"class"`
		Args  json.RawMessage `json:"args"`
	} `json:"operation"`
}

func DecodeBridge(encoded string) (protocol.Request, error) {
	if len(encoded) == 0 || len(encoded) > maxBridge || strings.ContainsAny(encoded, "=+/ \t\n") {
		return protocol.Request{}, errors.New("invalid base64url request")
	}
	b, e := base64.RawURLEncoding.Strict().DecodeString(encoded)
	if e != nil || len(b) > protocol.MaxEnvelope {
		return protocol.Request{}, errors.New("invalid bridge encoding or size")
	}
	var v bridgeRequest
	if e = protocol.StrictBytes(b, &v); e != nil {
		return protocol.Request{}, e
	}
	if v.SchemaVersion != protocol.Version || v.Client.Protocol.Min > protocol.Version || v.Client.Protocol.Max < protocol.Version || !validName(v.Operation.Name) || !v.Operation.Class.Valid() {
		return protocol.Request{}, errors.New("incompatible typed bridge request")
	}
	if len(v.Client.Name) > 80 || len(v.Client.Version) > 40 {
		return protocol.Request{}, errors.New("invalid bridge client")
	}
	if len(v.Operation.Args) == 0 {
		v.Operation.Args = json.RawMessage(`{}`)
	}
	req := protocol.Request{SchemaVersion: protocol.Version, RequestID: v.RequestID, Operation: v.Operation.Name, Class: v.Operation.Class, Arguments: v.Operation.Args}
	// Round trip via native envelope decoder for exact request-ID semantics.
	raw, _ := json.Marshal(req)
	return protocol.Decode(strings.NewReader(string(raw)))
}
func Embedded(ctx context.Context, encoded string, call CallFunc) (protocol.Response, error) {
	req, e := DecodeBridge(encoded)
	if e != nil {
		return protocol.Response{}, e
	}
	if _, ok := control.Lookup(req.Operation); !ok {
		return protocol.Response{}, errors.New("unknown typed operation")
	}
	return call(ctx, req)
}

// Standalone never binds non-loopback and issues no privileged operation outside the caller.
type Standalone struct {
	mu               sync.Mutex
	call             CallFunc
	assets           string
	listener         net.Listener
	bootstrap        string
	bootstrapExpires time.Time
	session          string
	csrf             string
	sessionExpires   time.Time
	lastActivity     time.Time
	idlePolicy       func() (time.Duration, error)
}

func NewStandalone(call CallFunc, assets string) (*Standalone, error) {
	if call == nil {
		return nil, errors.New("missing typed backend")
	}
	token, e := newSecret()
	if e != nil {
		return nil, e
	}
	return &Standalone{call: call, assets: assets, bootstrap: token, bootstrapExpires: time.Now().Add(3 * time.Minute)}, nil
}

// WithIdlePolicy binds authentication expiry to a private, validated settings reader.
// A nil reader retains the default fifteen-minute idle policy. The callback must
// fail closed on private-state read/validation errors, never return arbitrary TTLs.
func (s *Standalone) WithIdlePolicy(read func() (time.Duration, error)) *Standalone {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.idlePolicy = read
	return s
}
func (s *Standalone) idleDuration() (time.Duration, error) {
	if s.idlePolicy == nil {
		return sessionTTL, nil
	}
	ttl, err := s.idlePolicy()
	if err != nil {
		return 0, err
	}
	if ttl < 30*time.Second || ttl > time.Hour {
		return 0, errors.New("invalid WebUI idle policy")
	}
	return ttl, nil
}
func setSessionCookies(w http.ResponseWriter, session, csrf string, ttl time.Duration) {
	age := int(ttl.Seconds())
	http.SetCookie(w, &http.Cookie{Name: "skybind_session", Value: session, Path: "/", HttpOnly: true, SameSite: http.SameSiteStrictMode, Secure: false, MaxAge: age})
	http.SetCookie(w, &http.Cookie{Name: "skybind_csrf", Value: csrf, Path: "/", SameSite: http.SameSiteStrictMode, Secure: false, MaxAge: age})
}
func (s *Standalone) Listen() (string, string, error) {
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		return "", "", e
	}
	host, _, e := net.SplitHostPort(l.Addr().String())
	if e != nil || host != "127.0.0.1" {
		l.Close()
		return "", "", errors.New("non-loopback WebUI listener")
	}
	s.listener = l
	return "http://" + l.Addr().String(), s.bootstrap, nil
}
func (s *Standalone) Close() error {
	if s.listener == nil {
		return nil
	}
	return s.listener.Close()
}
func (s *Standalone) Serve(ctx context.Context) error {
	if s.listener == nil {
		return errors.New("listener not started")
	}
	server := &http.Server{Handler: s.Handler(), ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 20 * time.Second, WriteTimeout: 20 * time.Second, MaxHeaderBytes: 8192}
	go func() { <-ctx.Done(); _ = server.Close() }()
	err := server.Serve(s.listener)
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}
func strictOrigin(r *http.Request) bool {
	h := r.Host
	if !strings.HasPrefix(h, "127.0.0.1:") {
		return false
	}
	host, port, e := net.SplitHostPort(h)
	if e != nil || host != "127.0.0.1" || port == "" {
		return false
	}
	origin := r.Header.Get("Origin")
	return origin == "" || origin == "http://"+h
}
func secureHeaders(w http.ResponseWriter) {
	h := w.Header()
	h.Set("Cache-Control", "no-store")
	h.Set("X-Content-Type-Options", "nosniff")
	h.Set("Referrer-Policy", "no-referrer")
	h.Set("X-Frame-Options", "DENY")
	h.Set("Content-Security-Policy", "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; connect-src 'self'")
}
func (s *Standalone) authenticated(w http.ResponseWriter, r *http.Request) bool {
	ttl, err := s.idleDuration()
	if err != nil {
		return false
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	c, e := r.Cookie("skybind_session")
	now := time.Now()
	if e != nil || s.session == "" || !eq(c.Value, s.session) || !now.Before(s.sessionExpires) ||
		!now.Before(s.lastActivity.Add(ttl)) {
		return false
	}
	s.lastActivity = now
	s.sessionExpires = now.Add(ttl)
	setSessionCookies(w, s.session, s.csrf, ttl)
	return true
}
func (s *Standalone) csrfOK(r *http.Request) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	c, e := r.Cookie("skybind_csrf")
	return e == nil && eq(c.Value, s.csrf) && eq(r.Header.Get("X-Skybind-CSRF"), s.csrf)
}
func (s *Standalone) Handler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		secureHeaders(w)
		if !strictOrigin(r) {
			http.Error(w, "invalid host/origin", http.StatusForbidden)
			return
		}
		if r.URL.Path == "/api/v1/transport" && r.Method == http.MethodGet {
			writeJSON(w, map[string]any{"schema_version": 1, "transport": "standalone", "typed_backend": true})
			return
		}
		if r.URL.Path == "/auth/bootstrap" && r.Method == http.MethodPost {
			ttl, policyErr := s.idleDuration()
			if policyErr != nil {
				http.Error(w, "private session policy unavailable", http.StatusServiceUnavailable)
				return
			}
			r.Body = http.MaxBytesReader(w, r.Body, 512)
			var payload struct {
				Token string `json:"token"`
			}
			if protocol.StrictBytes(readLimited(r.Body, 513), &payload) != nil {
				http.Error(w, "invalid bootstrap", 400)
				return
			}
			s.mu.Lock()
			good := time.Now().Before(s.bootstrapExpires) && eq(payload.Token, s.bootstrap)
			if good {
				s.bootstrap = ""
				s.bootstrapExpires = time.Time{}
				var e error
				s.session, e = newSecret()
				if e == nil {
					s.csrf, e = newSecret()
				}
				if e == nil {
					s.lastActivity = time.Now()
					s.sessionExpires = s.lastActivity.Add(ttl)
				} else {
					good = false
				}
			}
			session, csrf := s.session, s.csrf
			s.mu.Unlock()
			if !good {
				http.Error(w, "invalid or used bootstrap", 403)
				return
			}
			setSessionCookies(w, session, csrf, ttl)
			writeJSON(w, map[string]any{"authenticated": true})
			return
		}
		// The immutable UI shell must be available before token authentication.
		// API operations remain authenticated below. Otherwise standalone clients
		// cannot display the one-use-token entry form at all.
		if (r.Method == http.MethodGet || r.Method == http.MethodHead) &&
			!strings.HasPrefix(r.URL.Path, "/api/") && r.URL.Path != "/auth/bootstrap" {
			s.serveAsset(w, r)
			return
		}
		if !s.authenticated(w, r) {
			http.Error(w, "authentication required", 401)
			return
		}
		if r.URL.Path == "/api/v1/capabilities" && r.Method == http.MethodGet {
			req := protocol.Request{SchemaVersion: 1, RequestID: "webui-caps", Class: protocol.Query, Operation: "system.capabilities", Arguments: []byte(`{}`)}
			res, err := s.call(r.Context(), req)
			if err != nil || !res.OK || res.SchemaVersion != 1 || res.RequestID != req.RequestID {
				http.Error(w, "capability backend unavailable", http.StatusBadGateway)
				return
			}
			writeJSON(w, res.Result) // Original WebUI requires the direct catalog.
			return
		}
		if strings.HasPrefix(r.URL.Path, "/api/v1/") && r.Method == http.MethodPost {
			if !s.csrfOK(r) {
				http.Error(w, "invalid CSRF", 403)
				return
			}
			if r.Header.Get("Content-Type") != "application/json" {
				http.Error(w, "invalid content type", 415)
				return
			}
			fields := strings.Split(strings.TrimPrefix(r.URL.Path, "/api/v1/"), "/")
			if len(fields) != 2 || !validName(fields[1]) {
				http.NotFound(w, r)
				return
			}
			class := protocol.Class(fields[0])
			if !class.Valid() {
				http.NotFound(w, r)
				return
			}
			item, ok := control.Lookup(fields[1])
			if !ok || item.OperationClass != class {
				http.Error(w, "unknown operation or class", 400)
				return
			}
			id := r.Header.Get("X-Skybind-Request-ID")
			if id == "" {
				http.Error(w, "missing request ID", 400)
				return
			}
			r.Body = http.MaxBytesReader(w, r.Body, protocol.MaxEnvelope)
			body := readLimited(r.Body, protocol.MaxEnvelope+1)
			if len(body) == 0 {
				body = []byte(`{}`)
			}
			req := protocol.Request{SchemaVersion: 1, RequestID: id, Class: class, Operation: fields[1], Arguments: body}
			raw, _ := json.Marshal(req)
			parsed, e := protocol.Decode(strings.NewReader(string(raw)))
			if e != nil {
				http.Error(w, "invalid typed request", 400)
				return
			}
			s.dispatch(w, r, parsed)
			return
		}
		http.NotFound(w, r)
	})
}

// serveAsset serves only the fixed, read-only frontend file set. No paths from
// the browser can reach root-private backend state or module installation hooks.
func (s *Standalone) serveAsset(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/")
	if path == "" {
		path = "index.html"
	}
	allowed := map[string]bool{"index.html": true, "app.js": true, "bridge.js": true, "model.js": true, "flow.js": true, "parity.js": true, "style.css": true, "icon.png": true, "config.json": true, "platform.json": true}
	if !allowed[path] || filepath.Base(path) != path {
		http.NotFound(w, r)
		return
	}
	f := filepath.Join(s.assets, path)
	info, e := os.Lstat(f)
	if e != nil || !info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0 {
		http.NotFound(w, r)
		return
	}
	http.ServeFile(w, r, f)
}

func readLimited(r io.Reader, n int64) []byte { b, _ := io.ReadAll(io.LimitReader(r, n)); return b }
func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}
func (s *Standalone) dispatch(w http.ResponseWriter, r *http.Request, req protocol.Request) {
	res, e := s.call(r.Context(), req)
	if e != nil {
		http.Error(w, "backend unavailable", 502)
		return
	}
	if res.SchemaVersion != protocol.Version || res.RequestID != req.RequestID {
		http.Error(w, "backend identity mismatch", 502)
		return
	}
	out, e := protocol.MarshalResponse(res)
	if e != nil {
		http.Error(w, "response too large", 502)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_, _ = w.Write(out)
}

// Capability and request transport share the same daemon caller as the CLI.
func CLIRequest(ctx context.Context, encoded string, socket string) (protocol.Response, error) {
	return Embedded(ctx, encoded, DaemonCaller(socket))
}
func Description() string { return fmt.Sprintf("Skybind WebUI typed transport v%d", protocol.Version) }
