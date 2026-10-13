package rc

import (
	"context"
	"encoding/json"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestPrivateRCWritebackRedaction(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		user, pass, ok := r.BasicAuth()
		if !ok || user != "skybind" || pass != "secret" {
			t.Error("missing authenticated RC request")
			w.WriteHeader(401)
			return
		}
		if r.Method != "POST" {
			t.Error("not POST")
		}
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/vfs/stats" {
			_, _ = w.Write([]byte(`{"fs":"my-secret-remote:","inUse":1,"diskCache":{"uploadsQueued":0,"uploadsInProgress":0,"erroredFiles":0,"path":"/private/secret"},"opt":{"Password":"secret"}}`))
		} else if r.URL.Path == "/core/stats" {
			_, _ = w.Write([]byte(`{"bytes":1024,"sensitive":"secret"}`))
		} else {
			w.WriteHeader(404)
		}
	}))
	defer server.Close()
	_, port, err := net.SplitHostPort(strings.TrimPrefix(server.URL, "http://"))
	if err != nil {
		t.Fatal(err)
	}
	m := New(t.TempDir(), func(name string) bool { return name == "cloud" })
	m.sessions["cloud"] = session{port: port, password: "secret"}
	wb, err := m.Writeback(context.Background(), "cloud")
	if err != nil || !wb.Safe() {
		t.Fatalf("writeback %+v %v", wb, err)
	}
	raw, err := m.Metrics(context.Background(), "cloud")
	if err != nil {
		t.Fatal(err)
	}
	buf, _ := json.Marshal(raw)
	if strings.Contains(string(buf), "/private") || strings.Contains(string(buf), "Password") || strings.Contains(string(buf), "my-secret") {
		t.Fatal("RC metadata leak")
	}
	if !strings.Contains(string(buf), `"state":"idle"`) {
		t.Fatalf("sanitized status unavailable %s", buf)
	}
	if _, err := m.Writeback(context.Background(), "other"); err == nil {
		t.Fatal("non-owned mount accepted")
	}
}
