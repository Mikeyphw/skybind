package webui

import (
	"bytes"
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"skybind/internal/protocol"
	"strings"
	"testing"
	"time"
)

func fakeCall(_ context.Context, r protocol.Request) (protocol.Response, error) {
	return protocol.Success(r.RequestID, map[string]string{"operation": r.Operation}), nil
}
func bridgeEncoded(name string) string {
	b, _ := json.Marshal(map[string]any{"schema_version": 1, "request_id": "req_123", "client": map[string]any{"name": "skybind-webui", "version": "1", "protocol": map[string]int{"min": 1, "max": 1}}, "operation": map[string]any{"name": name, "class": "query", "args": map[string]any{}}})
	return base64.RawURLEncoding.EncodeToString(b)
}
func TestBridgeParsesAndRoutes(t *testing.T) {
	res, e := Embedded(context.Background(), bridgeEncoded("runtime.status"), fakeCall)
	if e != nil || res.RequestID != "req_123" || !res.OK {
		t.Fatal(res, e)
	}
	for _, v := range []string{"../../bin/bash", "", "abc/123", base64.RawURLEncoding.EncodeToString([]byte(`{"foo":1}`))} {
		if _, e := DecodeBridge(v); e == nil {
			t.Fatal("unsafe bridge request", v)
		}
	}
}
func TestStandaloneSessionCSRFAndOrigin(t *testing.T) {
	s, e := NewStandalone(fakeCall, t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	s.bootstrapExpires = time.Now().Add(time.Minute)
	base := "http://127.0.0.1:30271"
	h := s.Handler()
	request := func(method, path, body, origin string, cookies []*http.Cookie, headers map[string]string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(method, base+path, strings.NewReader(body))
		req.Host = "127.0.0.1:30271"
		if origin != "" {
			req.Header.Set("Origin", origin)
		}
		for _, c := range cookies {
			req.AddCookie(c)
		}
		for k, v := range headers {
			req.Header.Set(k, v)
		}
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		return w
	}
	if w := request("GET", "/api/v1/capabilities", "", "", nil, nil); w.Code != 401 {
		t.Fatal(w.Code)
	}
	if w := request("POST", "/auth/bootstrap", fmt.Sprintf(`{"token":"%s"}`, s.bootstrap), "http://evil.example", nil, nil); w.Code != 403 {
		t.Fatal("bad origin succeeded")
	}
	w := request("POST", "/auth/bootstrap", fmt.Sprintf(`{"token":"%s"}`, s.bootstrap), "", nil, nil)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	cookies := w.Result().Cookies()
	if len(cookies) != 2 {
		t.Fatal(cookies)
	}
	var csrf string
	for _, c := range cookies {
		if c.Name == "skybind_csrf" {
			csrf = c.Value
		}
		if c.Name == "skybind_session" && !c.HttpOnly {
			t.Fatal("session not httpOnly")
		}
	}
	if w = request("POST", "/auth/bootstrap", `{"token":"repeat"}`, "", nil, nil); w.Code == 200 {
		t.Fatal("bootstrap replay")
	}
	if w = request("POST", "/api/v1/query/runtime.status", "{}", "", cookies, map[string]string{"Content-Type": "application/json", "X-Skybind-Request-ID": "xyz"}); w.Code != 403 {
		t.Fatal("CSRF accepted")
	}
	headers := map[string]string{"Content-Type": "application/json", "X-Skybind-CSRF": csrf, "X-Skybind-Request-ID": "req_33"}
	if w = request("POST", "/api/v1/query/runtime.status", "{}", "http://evil.example", cookies, headers); w.Code != 403 {
		t.Fatal("cross-origin accepted")
	}
	w = request("POST", "/api/v1/query/runtime.status", "{}", "", cookies, headers)
	if w.Code != 200 || !bytes.Contains(w.Body.Bytes(), []byte(`"request_id":"req_33"`)) {
		t.Fatal(w.Code, w.Body.String())
	}
	if w = request("POST", "/api/v1/query/unknown.command", "{}", "", cookies, headers); w.Code == 200 {
		t.Fatal("generic command accepted")
	}
	s.mu.Lock()
	s.sessionExpires = time.Now().Add(-time.Second)
	s.mu.Unlock()
	if w = request("GET", "/api/v1/capabilities", "", "", cookies, nil); w.Code != 401 {
		t.Fatal("expired session accepted")
	}
}
func TestLoopbackOnly(t *testing.T) {
	s, e := NewStandalone(fakeCall, t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	url, token, e := s.Listen()
	if e != nil {
		t.Skip("loopback listener unavailable:", e)
	}
	defer s.Close()
	if !strings.HasPrefix(url, "http://127.0.0.1:") || strings.Contains(url, token) {
		t.Fatal("unsafe listener URL")
	}
	if _, e := os.Stat("/tmp/skybind-nonexistent-static"); e == nil {
		t.Fatal("unexpected fixture")
	}
}

func TestEmbeddedAndStandaloneParity(t *testing.T) {
	s, e := NewStandalone(fakeCall, t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	// This test compares the operation result and identity across both transports,
	// not just their HTTP status codes.
	_, token, e := s.Listen()
	if e != nil {
		t.Skip("network unavailable:", e)
	}
	defer s.Close()
	host := s.listener.Addr().String()
	boot := httptest.NewRequest("POST", "http://"+host+"/auth/bootstrap", strings.NewReader(fmt.Sprintf(`{"token":"%s"}`, token)))
	boot.Host = host
	bw := httptest.NewRecorder()
	s.Handler().ServeHTTP(bw, boot)
	if bw.Code != 200 {
		t.Fatal(bw.Code)
	}
	cookie := bw.Result().Cookies()
	var csrf string
	for _, c := range cookie {
		if c.Name == "skybind_csrf" {
			csrf = c.Value
		}
	}
	req := httptest.NewRequest("POST", "http://"+host+"/api/v1/query/runtime.status", strings.NewReader(`{}`))
	req.Host = host
	for _, c := range cookie {
		req.AddCookie(c)
	}
	req.Header.Set("X-Skybind-CSRF", csrf)
	req.Header.Set("X-Skybind-Request-ID", "req_123")
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	s.Handler().ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	var standalone protocol.Response
	if e := json.Unmarshal(w.Body.Bytes(), &standalone); e != nil {
		t.Fatal(e)
	}
	embedded, e := Embedded(context.Background(), bridgeEncoded("runtime.status"), fakeCall)
	if e != nil {
		t.Fatal(e)
	}
	a, _ := json.Marshal(standalone)
	b, _ := json.Marshal(embedded)
	if !bytes.Equal(a, b) {
		t.Fatalf("typed transport drift: HTTP=%s embedded=%s", a, b)
	}
}

// C05 makes the immutable login shell reachable before token exchange, not
// privileged API routes or arbitrary files in the module/root-private state.
func TestPublicShellRestrictedFilesAndPrivateAPI(t *testing.T) {
	dir := t.TempDir()
	for name, content := range map[string]string{
		"index.html": "Skybind UI entry", "app.js": "export const x=1;",
		"secret.txt": "do-not-serve", "config.json": "{}",
	} {
		if err := os.WriteFile(filepath.Join(dir, name), []byte(content), 0600); err != nil {
			t.Fatal(err)
		}
	}
	if err := os.Symlink("secret.txt", filepath.Join(dir, "model.js")); err != nil {
		t.Fatal(err)
	}
	s, err := NewStandalone(fakeCall, dir)
	if err != nil {
		t.Fatal(err)
	}
	h := s.Handler()
	ask := func(path, host string) *httptest.ResponseRecorder {
		req := httptest.NewRequest(http.MethodGet, "http://127.0.0.1:30001"+path, nil)
		req.Host = host
		w := httptest.NewRecorder()
		h.ServeHTTP(w, req)
		return w
	}
	if w := ask("/", "127.0.0.1:30001"); w.Code != 200 || !strings.Contains(w.Body.String(), "Skybind UI entry") {
		t.Fatalf("entry denied: %v %q", w.Code, w.Body.String())
	}
	if w := ask("/app.js", "127.0.0.1:30001"); w.Code != 200 {
		t.Fatalf("script denied: %v", w.Code)
	}
	if w := ask("/api/v1/capabilities", "127.0.0.1:30001"); w.Code != 401 {
		t.Fatalf("private API public: %v", w.Code)
	}
	for _, p := range []string{"/secret.txt", "/model.js", "/.git/config", "/internal/daemon/wiring.go"} {
		if w := ask(p, "127.0.0.1:30001"); w.Code != 404 {
			t.Fatalf("served unsafe %q: %v", p, w.Code)
		}
	}
	if w := ask("/", "evil.example:30001"); w.Code != 403 {
		t.Fatalf("unsafe host accepted: %v", w.Code)
	}
}
