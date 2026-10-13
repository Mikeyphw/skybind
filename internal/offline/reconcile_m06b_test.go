package offline

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type reviewRemote struct {
	*editRemote
	metadataCalls       int
	copyCalls           int
	fullHash            bool
	metadataUnavailable bool
}

func (r *reviewRemote) Run(ctx context.Context, args ...string) ([]byte, error) {
	if len(args) > 0 && args[0] == "copyto" {
		r.copyCalls++
		return r.editRemote.Run(ctx, args...)
	}
	if len(args) > 0 && args[0] == "lsjson" {
		r.metadataCalls++
		if r.metadataUnavailable {
			return nil, errors.New("offline")
		}
		endpoint := args[len(args)-1]
		if strings.Contains(endpoint, "/Skybind-Offline-Edits/") {
			body, ok := r.files[endpoint]
			if !ok {
				return nil, errors.New("not found")
			}
			hashes := map[string]string{}
			if r.fullHash {
				h := sha256.Sum256([]byte(body))
				hashes["SHA-256"] = hex.EncodeToString(h[:])
			}
			return json.Marshal(RemoteFile{Size: int64(len(body)), Hashes: hashes})
		}
	}
	return r.editRemote.Run(ctx, args...)
}
func reviewFixture(t *testing.T) (*Store, *reviewRemote) {
	t.Helper()
	s, r := editFixture(t)
	v := &reviewRemote{editRemote: r}
	s.r = v
	return s, v
}
func TestM06BReconnectReviewNeverUploadsAndReportsConflict(t *testing.T) {
	s, r := reviewFixture(t)
	e := queueEdit(t, s)
	report, err := s.ReviewQueue(context.Background(), "drive")
	if err != nil || len(report.Items) != 1 || report.Items[0].State != "MATCH" {
		t.Fatalf("review %+v: %v", report, err)
	}
	if r.copyCalls != 0 || r.files["drive:cloud/report.txt"] != "Complete offline contents" {
		t.Fatal("read-only review performed remote write")
	}
	r.changed = true
	report, err = s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "CONFLICT" {
		t.Fatalf("conflict %+v %v", report, err)
	}
	r.changed = false
	r.metadataUnavailable = true
	report, err = s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "UNKNOWN" {
		t.Fatalf("offline %+v %v", report, err)
	}
	state, err := s.ReviewStatus()
	if err != nil || state.Report == nil || state.Report.Items[0].ID != e.ID || state.Report.Items[0].State != "UNKNOWN" {
		t.Fatalf("reboot review %+v %v", state, err)
	}
	next := New(s.dir, r, s.cfg)
	state, err = next.ReviewStatus()
	if err != nil || state.Report == nil || state.Report.Items[0].State != "UNKNOWN" {
		t.Fatalf("restart %+v %v", state, err)
	}
	if r.copyCalls != 0 {
		t.Fatal("silent retry")
	}
}
func TestM06BUncertainCopyOnlyResolvedByVerifiedSeparateHash(t *testing.T) {
	s, r := reviewFixture(t)
	e := queueEdit(t, s)
	r.uploadFails = true
	if _, err := s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("no failed upload")
	}
	// Independently observed same-size destination without SHA-256 is not proof.
	dest := "drive:cloud/Skybind-Offline-Edits/" + e.ID + "/report.txt"
	r.files[dest] = "Edited while offline!"
	report, err := s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "REVIEW_REQUIRED" {
		t.Fatalf("hashless %+v %v", report, err)
	}
	j, err := s.Edits()
	if err != nil || j.Edits[0].State != "UPLOAD_INDETERMINATE" {
		t.Fatal("hashless destination promoted")
	}
	r.fullHash = true
	report, err = s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "VERIFIED_REMOTE_COPY" {
		t.Fatalf("verified %+v %v", report, err)
	}
	j, err = s.Edits()
	if err != nil || j.Edits[0].State != "UPLOADED_COPY" || j.Edits[0].RemoteVerification != "remote-sha256-verified" {
		t.Fatalf("not promoted %+v %v", j, err)
	}
	if r.copyCalls != 1 || r.files["drive:cloud/report.txt"] != "Complete offline contents" {
		t.Fatal("extra upload or original modified")
	}
	if _, err = s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("verified copy reuploaded")
	}
}
func TestM06BIndeterminateRemoteMismatchNeverRetries(t *testing.T) {
	s, r := reviewFixture(t)
	e := queueEdit(t, s)
	r.uploadFails = true
	_, _ = s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy")
	dest := "drive:cloud/Skybind-Offline-Edits/" + e.ID + "/report.txt"
	r.files[dest] = "X"
	r.fullHash = true
	report, err := s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "CONFLICT" {
		t.Fatalf("mismatch %+v %v", report, err)
	}
	j, _ := s.Edits()
	if j.Edits[0].State != "UPLOAD_INDETERMINATE" || r.copyCalls != 1 {
		t.Fatal("retry or promotion after mismatch")
	}
	// Even a checksummed journal cannot redirect read probes to arbitrary paths.
	release, _ := s.editLock()
	j, _ = s.readEdits()
	j.Edits[0].UploadedRemoteCopy = "report.txt"
	if err = s.saveEdits(j); err != nil {
		t.Fatal(err)
	}
	release()
	before := r.metadataCalls
	report, err = s.ReviewQueue(context.Background(), "drive")
	if err != nil || report.Items[0].State != "LOCAL_CONFLICT" || r.metadataCalls != before {
		t.Fatalf("redirect %+v %v", report, err)
	}
}
func TestM06BReviewSettingsOptInTamperFailClosedAndCancellation(t *testing.T) {
	s, r := reviewFixture(t)
	queueEdit(t, s)
	settings, err := s.ReviewSettings()
	if err != nil || settings.AutoOnReconnect {
		t.Fatal("non-default or unreadable settings")
	}
	manager := NewTaskManager(s)
	if manager.OnReconnectHint() {
		t.Fatal("automatic remote read without opt-in")
	}
	if r.metadataCalls != 0 {
		t.Fatal("disabled reconnect made network request")
	}
	_, err = s.SetReviewAuto(true)
	if err != nil {
		t.Fatal(err)
	}
	next := New(s.dir, r, s.cfg)
	got, err := next.ReviewSettings()
	if err != nil || !got.AutoOnReconnect {
		t.Fatal("setting not persisted")
	}
	if !manager.OnReconnectHint() {
		t.Fatal("opt-in review not scheduled")
	}
	limit := time.After(3 * time.Second)
	for manager.Busy() {
		select {
		case <-limit:
			t.Fatal("review task did not complete")
		default:
			time.Sleep(5 * time.Millisecond)
		}
	}
	if manager.OnReconnectHint() {
		t.Fatal("reconnect flood caused repeat review")
	}
	if r.copyCalls != 0 {
		t.Fatal("reconnect unexpectedly uploaded")
	}
	b, err := os.ReadFile(filepath.Join(s.dir, "writes", "review-settings-v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	b[10] ^= 1
	if err = os.WriteFile(filepath.Join(s.dir, "writes", "review-settings-v1.json"), b, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = s.ReviewSettings(); err == nil {
		t.Fatal("tampered settings accepted")
	}
	if manager.OnReconnectHint() {
		t.Fatal("tampered preference enabled automatic review")
	}
	c, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = s.ReviewQueue(c, ""); !errors.Is(err, context.Canceled) {
		t.Fatalf("cancellation %v", err)
	}
}
