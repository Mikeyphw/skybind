package opevents

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func openFixture(t *testing.T) (*Store, string) {
	t.Helper()
	dir := filepath.Join(t.TempDir(), "events")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	s, err := Open(dir)
	if err != nil {
		t.Fatal(err)
	}
	return s, dir
}

const id = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

func sample(i int) Event {
	return Event{OperationID: id, RunID: id, Operation: "job.run", Type: "job.progress", State: "running", Phase: "transferring", Progress: &Progress{Bytes: int64(i), SpeedBytesPerSecond: 42}}
}
func TestDurabilityReplayGapAndFiltering(t *testing.T) {
	s, dir := openFixture(t)
	for i := 0; i < 520; i++ {
		if err := s.Append(sample(i)); err != nil {
			t.Fatal(err)
		}
	}
	s2, e := Open(dir)
	if e != nil {
		t.Fatal(e)
	}
	p, e := s2.Poll(context.Background(), 0, 64, "", 0)
	if e != nil {
		t.Fatal(e)
	}
	if !p.Gap || p.OldestCursor != 9 || !p.HasMore || len(p.Events) != 64 || p.Events[0].Sequence != 9 {
		t.Fatalf("unexpected gap page: %+v", p)
	}
	seq := p.NextCursor
	total := len(p.Events)
	for {
		p, e = s2.Poll(context.Background(), seq, 64, "", 0)
		if e != nil {
			t.Fatal(e)
		}
		total += len(p.Events)
		seq = p.NextCursor
		if !p.HasMore {
			break
		}
	}
	if total != 512 || seq != 520 {
		t.Fatalf("replay %d last %d", total, seq)
	}
	p, e = s2.Poll(context.Background(), 520, 64, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", 0)
	if e != nil || len(p.Events) != 0 {
		t.Fatalf("filter failed %v %+v", e, p)
	}
	if e = s2.Append(Event{OperationID: id, Operation: "job.run", Type: "job.failed", State: "failed", Phase: "executor_failed"}); e != nil {
		t.Fatal(e)
	}
	p, e = s2.Poll(context.Background(), 520, 64, "", 0)
	if e != nil || len(p.Events) != 1 || p.Events[0].Sequence != 521 {
		t.Fatalf("restart continuity: %+v %v", p, e)
	}
}
func TestSafetyWaitAndPoisoning(t *testing.T) {
	s, dir := openFixture(t)
	if err := s.Append(Event{OperationID: id, Operation: "job.run", Type: "job.failed", State: "failed", Phase: "/secret/password"}); err == nil {
		t.Fatal("unsafe path entered event log")
	}
	if err := s.Append(sample(1)); err != nil {
		t.Fatal(err)
	}
	b, e := os.ReadFile(filepath.Join(dir, fileName))
	if e != nil {
		t.Fatal(e)
	}
	if strings.Contains(string(b), "/secret") {
		t.Fatal("leaked")
	}
	go func() { time.Sleep(25 * time.Millisecond); _ = s.Append(sample(2)) }()
	p, e := s.Poll(context.Background(), 1, 32, "", time.Second)
	if e != nil || len(p.Events) != 1 || p.Events[0].Sequence != 2 {
		t.Fatalf("long poll failed %v %+v", e, p)
	}
	if _, e = s.Poll(context.Background(), 0, 0, "", 6*time.Second); e == nil {
		t.Fatal("unbounded wait accepted")
	}
	if _, e = s.Poll(context.Background(), 0, 32, "../leak", 0); e == nil {
		t.Fatal("untrusted filter accepted")
	}
}
