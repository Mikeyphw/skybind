package rc

import (
	"context"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestPrivateAuthAndMetricAllowlist(t *testing.T) {
	d := filepath.Join(t.TempDir(), "rc")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	m := New(d, func(string) bool { return true })
	args, e := m.Prepare("Alpha")
	if e != nil {
		t.Fatal(e)
	}
	if len(args) != 5 || args[2][:10] != "127.0.0.1:" {
		t.Fatal("non-loopback RC")
	}
	content, e := os.ReadFile(filepath.Join(d, "htpasswd-Alpha"))
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(content), m.sessions["Alpha"].password) {
		t.Fatal("plaintext secret persisted")
	}
	m.Drop("Alpha")
	if _, e = m.Metrics(context.Background(), "Alpha"); e == nil {
		t.Fatal("metric without auth")
	}
	l, e := net.Listen("tcp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer l.Close()
	go http.Serve(l, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		u, p, ok := r.BasicAuth()
		if !ok || u != "skybind" || p != "secret" {
			w.WriteHeader(401)
			return
		}
		io.WriteString(w, `{"bytes":12,"speed":3,"token":"SHOULD_NOT_LEAK","path":"/secret"}`)
	}))
	m.sessions["Alpha"] = session{port: strings.Split(l.Addr().String(), ":")[1], password: "secret"}
	data, e := m.Metrics(context.Background(), "Alpha")
	if e != nil {
		t.Fatal(e)
	}
	b, _ := json.Marshal(data)
	if strings.Contains(string(b), "SHOULD_NOT_LEAK") || strings.Contains(string(b), "/secret") {
		t.Fatal("RC data leak")
	}
}
func TestUnownedMetricsDenied(t *testing.T) {
	m := New(t.TempDir(), func(string) bool { return false })
	_, e := m.Metrics(context.Background(), "Alpha")
	if e == nil {
		t.Fatal("unowned metrics accepted")
	}
}
