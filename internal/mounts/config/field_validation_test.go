package config

import (
	"errors"
	"strings"
	"testing"
)

func TestTypedFieldErrorsDoNotExposeInputValues(t *testing.T) {
	original := Mount{Name: "alpha", Remote: "cloud:/", Mountpoint: "/mnt/skybind/alpha", CacheMode: "full"}
	cases := []struct {
		name, field, code string
		change            func(*Mount)
	}{
		{"name", "name", "INVALID_OR_DUPLICATE", func(m *Mount) { m.Name = "bad/../name" }},
		{"remote", "remote", "INVALID_REMOTE", func(m *Mount) { m.Remote = "secret-token" }},
		{"mountpoint", "mountpoint", "OUTSIDE_SUPPORTED_STORAGE", func(m *Mount) { m.Mountpoint = "/data/private-secret" }},
		{"policy", "cache_mode", "INVALID_CHOICE", func(m *Mount) { m.CacheMode = "unsafe-value" }},
		{"cache", "cache_max_bytes", "OUT_OF_RANGE", func(m *Mount) { m.CacheMaxBytes = -2 }},
		{"percent", "cache_low_percent", "EXCEEDS_HIGH_WATERMARK", func(m *Mount) { m.CacheLowPercent = 90; m.CacheHighPercent = 65 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			r := Empty()
			m := original
			tc.change(&m)
			r.Mounts = []Mount{m}
			_, err := Validate(raw(r))
			var typed *FieldValidationError
			if !errors.As(err, &typed) {
				t.Fatalf("missing typed field validation: %T %v", err, err)
			}
			if typed.Issue.Index != 0 || typed.Issue.Field != tc.field || typed.Issue.Code != tc.code {
				t.Fatalf("wrong bounded field error %+v", typed.Issue)
			}
			for _, leak := range []string{"secret-token", "private-secret", "unsafe-value"} {
				if strings.Contains(err.Error(), leak) {
					t.Fatalf("leaked raw input in error")
				}
			}
		})
	}
}
func TestOverlapReportsLaterMountField(t *testing.T) {
	r := Empty()
	r.Mounts = []Mount{
		{Name: "alpha", Remote: "cloud:/", Mountpoint: "/mnt/skybind/alpha"},
		{Name: "beta", Remote: "cloud:/", Mountpoint: "/mnt/skybind/alpha/sub"},
	}
	_, err := Validate(raw(r))
	var typed *FieldValidationError
	if !errors.As(err, &typed) || typed.Issue.Index != 1 || typed.Issue.Field != "mountpoint" || typed.Issue.Code != "OVERLAPPING_DESTINATION" {
		t.Fatalf("overlap not attributed: %v", err)
	}
}
func TestRollbackPrepareFailurePreservesCurrentRegistry(t *testing.T) {
	s := fixture(t)
	r := Empty()
	r.Mounts = []Mount{{Name: "alpha", Remote: "cloud:/", Mountpoint: "/mnt/skybind/alpha"}}
	plan, err := s.Preview(raw(r))
	if err != nil {
		t.Fatal(err)
	}
	before, err := s.Apply(raw(r), plan.Token)
	if err != nil {
		t.Fatal(err)
	}
	rp, err := s.RollbackPreview()
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.RollbackWithPrepare(rp.Token, func(_, _ Registry) error {
		return errors.New("writeback_busy_must_not_rollback")
	}); err == nil {
		t.Fatal("rollback bypassed busy writeback guard")
	}
	current, err := s.Snapshot()
	if err != nil || current.Revision != before.Revision || len(current.Mounts) != 1 {
		t.Fatalf("failed rollback mutated current registry: %+v, %v", current, err)
	}
	if _, err = s.Rollback(rp.Token); err == nil {
		t.Fatal("replayed rollback token after rejected transaction")
	}
}
