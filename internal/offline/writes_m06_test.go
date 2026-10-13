package offline

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"skybind/internal/mounts/config"
	"strings"
	"testing"
)

type editRemote struct {
	*fakeRemote
	uploadFails bool
	written     string
}

func (r *editRemote) Run(ctx context.Context, args ...string) ([]byte, error) {
	if len(args) > 0 && args[0] == "copyto" && len(args) > 5 && args[1] == "--immutable" {
		src, dst := args[len(args)-2], args[len(args)-1]
		if !strings.Contains(dst, "/Skybind-Offline-Edits/") || dst == "drive:cloud/report.txt" {
			return nil, errors.New("unsafe upload path")
		}
		body, err := os.ReadFile(src)
		if err != nil {
			return nil, err
		}
		r.written = dst
		if r.uploadFails {
			return nil, errors.New("network dropped")
		}
		if _, exists := r.files[dst]; exists {
			return nil, errors.New("immutable destination exists")
		}
		r.files[dst] = string(body)
		return nil, nil
	}
	return r.fakeRemote.Run(ctx, args...)
}
func editFixture(t *testing.T) (*Store, *editRemote) {
	t.Helper()
	s, f := fixture(t)
	r := &editRemote{fakeRemote: f}
	s.r = r
	base := filepath.Join(t.TempDir(), "Download")
	if err := os.MkdirAll(base, 0700); err != nil {
		t.Fatal(err)
	}
	s.draftBase = base
	if _, err := s.Pin(context.Background(), "drive", "report.txt", false); err != nil {
		t.Fatal(err)
	}
	return s, r
}
func queueEdit(t *testing.T, s *Store) Edit {
	t.Helper()
	dest, err := s.Draft("drive", "report.txt")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(dest, []byte("Edited while offline!"), 0644); err != nil {
		t.Fatal(err)
	}
	e, err := s.Stage("drive", "report.txt")
	if err != nil {
		t.Fatal(err)
	}
	return e
}
func TestM06DraftStageRebootAndSeparateUpload(t *testing.T) {
	s, r := editFixture(t)
	e := queueEdit(t, s)
	if e.State != "QUEUED" || e.BaseSourceHash == "" {
		t.Fatalf("bad entry %+v", e)
	}
	if _, err := s.Stage("drive", "report.txt"); err == nil {
		t.Fatal("duplicated unresolved edit")
	}
	again := New(s.dir, r, s.cfg)
	again.draftBase = s.draftBase
	j, err := again.Edits()
	if err != nil || len(j.Edits) != 1 || j.Edits[0] != e {
		t.Fatalf("reboot queue: %+v %v", j, err)
	}
	check, err := again.CheckEdit(context.Background(), e.ID)
	if err != nil || check.State != "MATCH" {
		t.Fatalf("remote revision: %+v %v", check, err)
	}
	if _, err = again.UploadSeparateCopy(context.Background(), e.ID, "bad"); err == nil {
		t.Fatal("accepted missing ack")
	}
	uploaded, err := again.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy")
	if err != nil || uploaded.State != "UPLOADED_COPY" || uploaded.RemoteVerification != "size-only-unverified" {
		t.Fatalf("upload %+v %v", uploaded, err)
	}
	if r.files["drive:cloud/report.txt"] != "Complete offline contents" {
		t.Fatal("original remote overwritten")
	}
	if r.files[r.written] != "Edited while offline!" {
		t.Fatal("uploaded bytes incorrect")
	}
	if _, err = again.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("allowed upload retry")
	}
	st, err := again.Status(context.Background(), "drive", "report.txt", false)
	if err != nil || st.State != "AVAILABLE_OFFLINE" {
		t.Fatalf("pin changed %+v %v", st, err)
	}
}
func TestM06ConflictUnknownAndTamperFailClosed(t *testing.T) {
	s, r := editFixture(t)
	e := queueEdit(t, s)
	r.changed = true
	c, err := s.CheckEdit(context.Background(), e.ID)
	if err != nil || c.State != "CONFLICT" {
		t.Fatalf("conflict %+v %v", c, err)
	}
	r.changed = false
	r.omitHash = true
	c, err = s.CheckEdit(context.Background(), e.ID)
	if err != nil || c.State != "CONFLICT" {
		t.Fatalf("checksum withdrawn %+v %v", c, err)
	}
	r.omitHash = false
	delete(r.files, "drive:cloud/report.txt")
	c, err = s.CheckEdit(context.Background(), e.ID)
	if err != nil || c.State != "UNKNOWN" {
		t.Fatalf("offline %+v %v", c, err)
	}
	object := s.dir + "/writes/objects/" + e.SHA256
	if err = os.WriteFile(object, []byte("tampered"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("tampered edit uploaded")
	}
}
func TestM06RemoteTimeoutPersistsIndeterminateWithoutRetry(t *testing.T) {
	s, r := editFixture(t)
	e := queueEdit(t, s)
	r.uploadFails = true
	if _, err := s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("expected network failure")
	}
	next := New(s.dir, r, s.cfg)
	j, err := next.Edits()
	if err != nil || len(j.Edits) != 1 || j.Edits[0].State != "UPLOAD_INDETERMINATE" {
		t.Fatalf("crash recovery %+v %v", j, err)
	}
	if _, err = next.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("dangerous retry accepted")
	}
}
func TestM06RejectsSymlinkDraftAndCorruptedJournal(t *testing.T) {
	s, _ := editFixture(t)
	draft, err := s.Draft("drive", "report.txt")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Remove(draft); err != nil {
		t.Fatal(err)
	}
	if err = os.Symlink("/etc/passwd", draft); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Stage("drive", "report.txt"); err == nil {
		t.Fatal("public symlink accepted")
	}
	os.Remove(draft)
	queueEdit(t, s)
	journal := s.dir + "/writes/edits-v1.json"
	b, err := os.ReadFile(journal)
	if err != nil {
		t.Fatal(err)
	}
	var raw map[string]any
	if err = json.Unmarshal(b, &raw); err != nil {
		t.Fatal(err)
	}
	raw["sha256"] = strings.Repeat("0", 64)
	b, err = json.Marshal(raw)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(journal, b, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err = s.Edits(); err == nil {
		t.Fatal("corrupt journal accepted")
	}
}
func TestM06UnchangedAndUnpinnedDraftRejected(t *testing.T) {
	s, _ := editFixture(t)
	if _, err := s.Draft("drive", "../bad"); err == nil {
		t.Fatal("path traversal draft")
	}
	if _, err := s.Draft("drive", "missing.txt"); err == nil {
		t.Fatal("unverified base")
	}
	if _, err := s.Draft("drive", "report.txt"); err != nil {
		t.Fatal(err)
	}
	if _, err := s.Stage("drive", "report.txt"); err == nil {
		t.Fatal("unchanged edit queued")
	}
}
func TestM06VerifiedHashCanBeCompared(t *testing.T) {
	f := filepath.Join(t.TempDir(), "file")
	os.WriteFile(f, []byte("hash me"), 0600)
	sum := sha256.Sum256([]byte("hash me"))
	ok, has := matchFileRemoteHashes(f, map[string]string{"SHA-256": hex.EncodeToString(sum[:])})
	if !ok || !has {
		t.Fatal("sha256 not verified")
	}
	ok, has = matchFileRemoteHashes(f, map[string]string{"SHA-256": strings.Repeat("a", 64)})
	if ok || !has {
		t.Fatal("bad hash accepted")
	}
}

func TestM06RemoteCopyRespectsReadOnlyMount(t *testing.T) {
	s, r := editFixture(t)
	e := queueEdit(t, s)
	oldConfig := s.cfg
	s.cfg = func() (config.Registry, error) {
		reg, err := oldConfig()
		if err != nil {
			return reg, err
		}
		reg.Mounts[0].ReadOnly = true
		return reg, nil
	}
	if _, err := s.UploadSeparateCopy(context.Background(), e.ID, "--acknowledge-separate-copy"); err == nil {
		t.Fatal("read-only upload allowed")
	}
	if r.written != "" {
		t.Fatal("remote side effect on read-only")
	}
	j, err := s.Edits()
	if err != nil || j.Edits[0].State != "QUEUED" {
		t.Fatalf("read-only refusal mutated journal %+v %v", j, err)
	}
}
