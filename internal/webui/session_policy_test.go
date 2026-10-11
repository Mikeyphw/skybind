package webui

import (
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestConfigurableIdleExpiryAndRefresh(t *testing.T) {
	ttl := 30 * time.Second
	srv, err := NewStandalone(fakeCall, t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	srv.WithIdlePolicy(func() (time.Duration, error) { return ttl, nil })
	host := "127.0.0.1:30191"
	call := func(method, path, body string, cookies []*http.Cookie) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, "http://"+host+path, strings.NewReader(body))
		req.Host = host
		for _, c := range cookies {
			req.AddCookie(c)
		}
		w := httptest.NewRecorder()
		srv.Handler().ServeHTTP(w, req)
		return w
	}
	b := call("POST", "/auth/bootstrap", fmt.Sprintf(`{"token":"%s"}`, srv.bootstrap), nil)
	if b.Code != 200 {
		t.Fatalf("bootstrap %d %s", b.Code, b.Body.String())
	}
	cookies := b.Result().Cookies()
	if len(cookies) != 2 {
		t.Fatal("missing session cookies")
	}
	for _, c := range cookies {
		if c.MaxAge != 30 {
			t.Fatalf("TTL not configured: %s=%d", c.Name, c.MaxAge)
		}
	}
	r := call("GET", "/api/v1/capabilities", "", cookies)
	if r.Code != 200 {
		t.Fatalf("request rejected %d", r.Code)
	}
	if len(r.Result().Cookies()) != 2 {
		t.Fatal("active session cookies not refreshed")
	}
	ttl = 60 * time.Second
	r = call("GET", "/api/v1/capabilities", "", cookies)
	if r.Code != 200 {
		t.Fatalf("setting increase broke session %d", r.Code)
	}
	for _, c := range r.Result().Cookies() {
		if c.MaxAge != 60 {
			t.Fatal("new TTL ignored")
		}
	}
	ttl = 30 * time.Second
	srv.mu.Lock()
	srv.lastActivity = time.Now().Add(-31 * time.Second)
	srv.mu.Unlock()
	r = call("GET", "/api/v1/capabilities", "", cookies)
	if r.Code != 401 {
		t.Fatalf("shortened policy did not expire idle token %d", r.Code)
	}
}
func TestInvalidIdlePolicyFailsClosed(t *testing.T) {
	for _, tt := range []struct {
		ttl time.Duration
		err error
	}{{5 * time.Second, nil}, {time.Hour + time.Second, nil}, {0, errors.New("private state unreadable")}} {
		srv, e := NewStandalone(fakeCall, t.TempDir())
		if e != nil {
			t.Fatal(e)
		}
		srv.WithIdlePolicy(func() (time.Duration, error) { return tt.ttl, tt.err })
		req := httptest.NewRequest("POST", "http://127.0.0.1:30199/auth/bootstrap", strings.NewReader(fmt.Sprintf(`{"token":"%s"}`, srv.bootstrap)))
		req.Host = "127.0.0.1:30199"
		w := httptest.NewRecorder()
		srv.Handler().ServeHTTP(w, req)
		if w.Code != 503 {
			t.Fatalf("unsafe idle policy accepted %d", w.Code)
		}
	}
}

func TestParityModuleIsPublicButArbitraryFilesRemainBlocked(t *testing.T) {
	dir := t.TempDir()
	for name, txt := range map[string]string{"index.html": "login", "parity.js": "export const x=1;", "secret.txt": "never"} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(txt), 0600); err != nil {
			t.Fatal(err)
		}
	}
	srv, err := NewStandalone(fakeCall, dir)
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		path string
		want int
	}{{"/parity.js", 200}, {"/secret.txt", 404}, {"/parity.js/../secret.txt", 404}} {
		req := httptest.NewRequest("GET", "http://127.0.0.1:30191"+tc.path, nil)
		req.Host = "127.0.0.1:30191"
		res := httptest.NewRecorder()
		srv.Handler().ServeHTTP(res, req)
		if res.Code != tc.want {
			t.Fatalf("%s got %d expected %d", tc.path, res.Code, tc.want)
		}
	}
}
