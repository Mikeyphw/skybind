package jobs

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/opevents"
	"testing"
	"time"
)

func TestRichRcloneStatisticsStrictAndPrivate(t *testing.T) {
	input := []byte(`{"level":"notice","msg":"DO NOT LEAK remote:secret/path","stats":{"bytes":1024,"totalBytes":4096,"speed":256.5,"eta":12,"transfers":3,"totalTransfers":8,"checks":7,"totalChecks":9,"errors":2,"retryError":true,"transferring":[{"name":"remote:secret/path","bytes":1024}]}}`)
	p, ok := decodeDetailedStats(input)
	if !ok || p.Bytes != 1024 || p.Speed != 256.5 || p.TotalBytes == nil || *p.TotalBytes != 4096 || p.FilesDone == nil || *p.FilesDone != 3 || p.FilesTotal == nil || *p.FilesTotal != 8 || p.ChecksDone == nil || *p.ChecksDone != 7 || p.ChecksTotal == nil || *p.ChecksTotal != 9 || p.Errors == nil || *p.Errors != 2 || p.RetryError == nil || !*p.RetryError || p.TransferRetries != nil {
		t.Fatalf("stats parse mismatch: %+v %v", p, ok)
	}
	b, _ := json.Marshal(p)
	if string(b) == string(input) || containsBytes(b, []byte("secret")) {
		t.Fatal("unsafe data in progress", string(b))
	}
	b2, s, eta, ok := decodeStats(input)
	if !ok || b2 != 1024 || s != 256.5 || eta != 12 {
		t.Fatal("old progress API regressed")
	}
	noTotals, ok := decodeDetailedStats([]byte(`{"stats":{"bytes":0,"speed":13,"eta":null}}`))
	if !ok || noTotals.TotalBytes != nil || noTotals.FilesTotal != nil || noTotals.TransferRetries != nil {
		t.Fatal("fabricated totals", noTotals, ok)
	}
	zeros, ok := decodeDetailedStats([]byte(`{"stats":{"bytes":0,"totalBytes":0,"transfers":0,"totalTransfers":0,"retryError":false}}`))
	if !ok || zeros.FilesDone == nil || zeros.FilesTotal == nil || zeros.RetryError == nil || *zeros.RetryError {
		t.Fatal("known zero fields omitted", zeros, ok)
	}
	for _, line := range []string{
		`{"level":"error","msg":"secret"}`, `{"stats":{"bytes":-1}}`,
		`{"stats":{"bytes":1,"totalBytes":-2}}`, `{"stats":{"bytes":1,"speed":-2}}`,
		`{"stats":{"bytes":1,"errors":-1}}`, `{"stats":{"bytes":1,"transfers":"1"}}`,
		`{"stats":{"bytes":1,"retryError":"true"}}`, `{"stats":{"bytes":1,"transferRetries":-10}}`,
		`{"stats":{"bytes":1,"speed":1e999}}`,
	} {
		if _, ok := decodeDetailedStats([]byte(line)); ok {
			t.Fatalf("bad stats accepted %s", line)
		}
	}
	explicit, ok := decodeDetailedStats([]byte(`{"stats":{"bytes":123,"transferRetries":2}}`))
	if !ok || explicit.TransferRetries == nil || *explicit.TransferRetries != 2 {
		t.Fatal("explicit retries ignored", explicit)
	}
}
func containsBytes(b, pat []byte) bool {
	for i := 0; i+len(pat) <= len(b); i++ {
		if string(b[i:i+len(pat)]) == string(pat) {
			return true
		}
	}
	return false
}

type detailedRunner struct {
	begun   chan struct{}
	release chan struct{}
}

func (r detailedRunner) Execute(ctx context.Context, j Job) error {
	return r.ExecuteWithDetailedProgress(ctx, j, nil)
}
func (r detailedRunner) ExecuteWithDetailedProgress(ctx context.Context, j Job, cb func(DetailedProgress)) error {
	total := int64(4000)
	files := int64(4)
	done := int64(2)
	checksDone := int64(3)
	checksTotal := int64(5)
	errors := int64(1)
	retry := true
	if cb != nil {
		cb(DetailedProgress{Bytes: 1000, Speed: 200, ETA: 15, TotalBytes: &total, FilesDone: &done, FilesTotal: &files, ChecksDone: &checksDone, ChecksTotal: &checksTotal, Errors: &errors, RetryError: &retry})
	}
	close(r.begun)
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-r.release:
		return nil
	}
}
func TestRichProgressDurableJobsAndEvents(t *testing.T) {
	store, _, dir := fixture(t)
	r := detailedRunner{make(chan struct{}), make(chan struct{})}
	store.executor = r
	evDir := filepath.Join(t.TempDir(), "events")
	if e := os.Mkdir(evDir, 0700); e != nil {
		t.Fatal(e)
	}
	events, e := opevents.Open(evDir)
	if e != nil {
		t.Fatal(e)
	}
	store.SetEventObserver(func(ev opevents.Event) {
		if err := events.Append(ev); err != nil {
			t.Errorf("append event: %v", err)
		}
	})
	p, e := store.Preview(registry("copy"))
	if e != nil {
		t.Fatal(e)
	}
	if _, e = store.Apply(registry("copy"), proof(t, p)); e != nil {
		t.Fatal(e)
	}
	p, e = store.RunPreview("Backup")
	if e != nil {
		t.Fatal(e)
	}
	run, e := store.RunManual("Backup", proof(t, p))
	if e != nil {
		t.Fatal(e)
	}
	<-r.begun
	status, e := store.RunStatus(run.ID)
	if e != nil {
		t.Fatal(e)
	}
	if status.Percent == nil || *status.Percent != 25 || status.FilesDone == nil || *status.FilesDone != 2 || status.TotalBytes == nil || *status.TotalBytes != 4000 || status.TransferRetries != nil {
		t.Fatal("rich state wrong", status)
	}
	_, e = store.Cancel(run.ID)
	if e != nil {
		t.Fatal(e)
	}
	deadline := time.Now().Add(2 * time.Second)
	for time.Now().Before(deadline) {
		status, e = store.RunStatus(run.ID)
		if e == nil && status.State == "CANCELLED" {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if status.State != "CANCELLED" {
		t.Fatalf("did not cancel %+v", status)
	}
	reopened, e := Open(dir, r, store.facts)
	if e != nil {
		t.Fatal(e)
	}
	persisted, e := reopened.RunStatus(run.ID)
	if e != nil || persisted.Percent == nil || *persisted.Percent != 25 {
		t.Fatalf("persisted progress: %+v %v", persisted, e)
	}
	ev2, e := opevents.Open(evDir)
	if e != nil {
		t.Fatal(e)
	}
	page, e := ev2.Poll(context.Background(), 0, 64, run.ID, 0)
	if e != nil {
		t.Fatal(e)
	}
	var found bool
	for _, ev := range page.Events {
		if ev.Type == "job.progress" {
			found = true
			if ev.Progress == nil || ev.Progress.Percent == nil || *ev.Progress.Percent != 25 || ev.Progress.TransferRetries != nil {
				t.Fatalf("event fields: %+v", ev)
			}
		}
	}
	if !found {
		t.Fatal("rich progress event absent", page)
	}
}
