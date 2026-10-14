package supervisor

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"skybind/internal/mounts/lifecycle"
)

func TestCEStorageDeferNoBudgetAcrossRestart(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "health")
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	f := &q07Engine{desired: true, nowError: lifecycle.ErrAndroidUserStorageDeferred}
	s, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now()
	s.now = func() time.Time { return now }
	for i := 0; i < 15; i++ {
		result, err := s.Reconcile(context.Background())
		if err != nil {
			t.Fatal(err)
		}
		if len(result) != 1 || result[0].Reason != "android_storage_deferred" || result[0].State != "RETRYING" || result[0].Attempts != 0 || result[0].RecoveryProbes != 0 {
			t.Fatalf("unexpected defer %d: %+v", i, result)
		}
		now = now.Add(30 * time.Second)
	}
	if f.starts != 15 {
		t.Fatalf("unexpected starts %d", f.starts)
	}
	next, err := NewPersistent(f, dir)
	if err != nil {
		t.Fatal(err)
	}
	if next.retry["cloud"].attempts != 0 || next.retry["cloud"].probes != 0 {
		t.Fatalf("defer spent retry budget: %+v", next.retry["cloud"])
	}
	next.now = func() time.Time { return now }
	f.nowError = nil
	result, err := next.Reconcile(context.Background())
	if err != nil || result[0].State != "RUNNING" {
		t.Fatalf("failed recovery after CE unlock: %+v %v", result, err)
	}
	if f.starts != 16 {
		t.Fatalf("missing recovery attempt, starts=%d", f.starts)
	}
}

func TestCEStorageDeferDoesNotResetExistingProviderFailures(t *testing.T) {
	f := &q07Engine{desired: true, nowError: errors.New("provider failure")}
	s := New(f)
	now := time.Now()
	s.now = func() time.Time { return now }
	_, err := s.Reconcile(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if s.retry["cloud"].attempts != 1 {
		t.Fatal("provider failure must count")
	}
	now = now.Add(time.Minute)
	f.nowError = lifecycle.ErrAndroidUserStorageDeferred
	r, err := s.Reconcile(context.Background())
	if err != nil || r[0].Attempts != 1 || r[0].Reason != "android_storage_deferred" {
		t.Fatalf("defer changed existing budget: %+v %v", r, err)
	}
	now = now.Add(time.Minute)
	f.nowError = errors.New("provider failure again")
	r, err = s.Reconcile(context.Background())
	if err != nil || r[0].Attempts != 2 {
		t.Fatalf("real failure not charged after unlock: %+v %v", r, err)
	}
}

func TestCEStorageDeferredHonorsExplicitStop(t *testing.T) {
	f := &q07Engine{desired: false, nowError: lifecycle.ErrAndroidUserStorageDeferred}
	s := New(f)
	r, err := s.Reconcile(context.Background())
	if err != nil || f.starts != 0 || len(r) != 1 || r[0].Reason != "explicit_stop" {
		t.Fatalf("unexpected start of stopped mount: %+v %v", r, err)
	}
}
