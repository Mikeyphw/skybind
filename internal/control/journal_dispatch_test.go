package control

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"skybind/internal/journal"
	"skybind/internal/protocol"
	"testing"
)

func testJournal(t *testing.T) *journal.Journal {
	t.Helper()
	d := filepath.Join(t.TempDir(), "journal")
	if e := os.Mkdir(d, 0700); e != nil {
		t.Fatal(e)
	}
	j, e := journal.Open(d)
	if e != nil {
		t.Fatal(e)
	}
	return j
}
func TestDurableMutationRecordedBeforeEffects(t *testing.T) {
	j := testJournal(t)
	e := New()
	e.SetJournal(j)
	if err := e.Register("config.apply", protocol.Run, func(_ context.Context, _ json.RawMessage) (any, error) {
		recs, err := j.List()
		if err != nil || len(recs) != 1 || recs[0].State != journal.Running || recs[0].RequestID != "txn-1" || recs[0].Cancellable {
			t.Fatalf("effect preceded durable noncancellable reservation: %+v %v", recs, err)
		}
		return map[string]bool{"applied": true}, nil
	}); err != nil {
		t.Fatal(err)
	}
	res := e.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "txn-1", Operation: "config.apply", Class: protocol.Run})
	if !res.OK {
		t.Fatalf("dispatch %v", res)
	}
	rec, err := j.ByRequest("txn-1")
	if err != nil || rec.State != journal.Succeeded || rec.Stage != "handler_returned" || rec.Cancellable {
		t.Fatalf("incorrect terminal journal %+v %v", rec, err)
	}
	if _, err := j.Cancel(rec.ID); err == nil {
		t.Fatal("synchronous operation falsely cancellable")
	}
}
func TestFailedMutationAndJournalFailClosed(t *testing.T) {
	j := testJournal(t)
	eng := New()
	eng.SetJournal(j)
	effects := 0
	if err := eng.Register("config.rollback", protocol.Run, func(context.Context, json.RawMessage) (any, error) { effects++; return nil, os.ErrPermission }); err != nil {
		t.Fatal(err)
	}
	req := protocol.Request{SchemaVersion: 1, RequestID: "rollback-1", Operation: "config.rollback", Class: protocol.Run}
	res := eng.Dispatch(context.Background(), req)
	if res.OK {
		t.Fatal("handler failure reported success")
	}
	rec, e := j.ByRequest(req.RequestID)
	if e != nil || rec.State != journal.Failed {
		t.Fatalf("missing failed journal %+v %v", rec, e)
	}
	// Fail before a write can succeed: effect must not occur.
	bad := &journal.Journal{}
	eng.SetJournal(bad)
	req.RequestID = "rollback-2"
	res = eng.Dispatch(context.Background(), req)
	if res.OK || res.Error.Code != "journal_unavailable" || effects != 1 {
		t.Fatalf("mutation without durable reservation: %+v effects %d", res, effects)
	}
}
func TestJobClaimIsNotTerminalTransfer(t *testing.T) {
	j := testJournal(t)
	eng := New()
	eng.SetJournal(j)
	if err := eng.Register("job.run", protocol.Run, func(context.Context, json.RawMessage) (any, error) {
		return struct {
			ID    string `json:"id"`
			State string `json:"state"`
		}{"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "RUNNING"}, nil
	}); err != nil {
		t.Fatal(err)
	}
	res := eng.Dispatch(context.Background(), protocol.Request{SchemaVersion: 1, RequestID: "job-1", Operation: "job.run", Class: protocol.Run})
	if !res.OK {
		t.Fatal(res)
	}
	rec, e := j.ByRequest("job-1")
	if e != nil || rec.RunID != "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" || rec.Stage != "job_claimed_not_finished" {
		t.Fatalf("claim not linked: %+v %v", rec, e)
	}
}
