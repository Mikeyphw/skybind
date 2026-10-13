package daemon

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/backup"
	"skybind/internal/control"
	"skybind/internal/mounts/config"
	"skybind/internal/offline"
	"skybind/internal/protocol"
	"skybind/internal/uisettings"
	"testing"
)

func TestM07BackupProofReplayAndSafeImport(t *testing.T) {
	d := t.TempDir()
	mk := func(name string) string {
		p := filepath.Join(d, name)
		if err := os.Mkdir(p, 0700); err != nil {
			t.Fatal(err)
		}
		return p
	}
	cs, err := config.Open(mk("config"))
	if err != nil {
		t.Fatal(err)
	}
	us, err := uisettings.Open(mk("ui"))
	if err != nil {
		t.Fatal(err)
	}
	store := offline.New(mk("offline"), nil, nil)
	e := control.New()
	if err = RegisterBackup(e, cs, us, store, cs.Apply); err != nil {
		t.Fatal(err)
	}
	dispatch := func(op string, class protocol.Class, arg any) protocol.Response {
		b, _ := json.Marshal(arg)
		return e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "m07", Operation: op, Class: class, Arguments: b})
	}
	if dispatch("backup.save", protocol.Run, map[string]bool{"acknowledge_public": false}).OK {
		t.Fatal("unchecked public export")
	}
	if dispatch("backup.restore", protocol.Run, map[string]any{"proof": "forged", "acknowledge_disabled": true}).OK {
		t.Fatal("accepted empty restore")
	}
	reg := config.Empty()
	reg.Mounts = []config.Mount{{Name: "drive", Remote: "drive:Docs", Mountpoint: "/mnt/drive", Enabled: true}}
	doc, err := backup.Build(reg, us.Snapshot(), offline.Manifest{Schema: 1, QuotaBytes: 8 << 30})
	if err != nil {
		t.Fatal(err)
	}
	response := dispatch("backup.preview", protocol.Preview, map[string]any{"document": doc})
	if !response.OK {
		t.Fatalf("preview: %+v", response.Error)
	}
	data, _ := json.Marshal(response.Result)
	var previewed struct {
		Plan              config.Plan `json:"plan"`
		AllMountsDisabled bool        `json:"all_mounts_disabled"`
	}
	_ = json.Unmarshal(data, &previewed)
	if !previewed.AllMountsDisabled || previewed.Plan.Token == "" {
		t.Fatal("backup did not require safe preview")
	}
	args := map[string]any{"document": doc, "proof": previewed.Plan.Token, "acknowledge_disabled": true}
	if dispatch("backup.restore", protocol.Query, args).OK {
		t.Fatal("wrong class accepted")
	}
	if dispatch("backup.restore", protocol.Run, map[string]any{"document": doc, "proof": previewed.Plan.Token, "acknowledge_disabled": false}).OK {
		t.Fatal("missing explicit consent accepted")
	}
	if !dispatch("backup.restore", protocol.Run, args).OK {
		t.Fatal("restoration failed")
	}
	got, err := cs.Snapshot()
	if err != nil || len(got.Mounts) != 1 || got.Mounts[0].Enabled || got.Revision != 1 {
		t.Fatalf("unsafe restore %+v %v", got, err)
	}
	if dispatch("backup.restore", protocol.Run, args).OK {
		t.Fatal("replayed proof")
	}
	previous, err := cs.Previous()
	if err != nil || previous.Revision != 0 {
		t.Fatalf("previous known good lost %+v %v", previous, err)
	}
	tampered := doc
	tampered.SHA256 = "deadbeef"
	if dispatch("backup.preview", protocol.Preview, map[string]any{"document": tampered}).OK {
		t.Fatal("tampered backup accepted")
	}
	if dispatch("backup.preview", protocol.Preview, map[string]any{"document": doc, "file": "/etc/shadow"}).OK {
		t.Fatal("unknown file argument accepted")
	}
	if dispatch("backup.exec", protocol.Run, map[string]any{}).OK {
		t.Fatal("arbitrary operation accepted")
	}
}
