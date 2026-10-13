package offline

// M6B: opt-in, bounded reconnect review of the durable M6 write journal.
// A review may issue READ-ONLY provider metadata requests and can recognize an
// independently SHA-256-verified separate upload; it never uploads, deletes,
// retries, merges, or writes to an original remote file.

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"skybind/internal/atomicfile"
)

const reviewItemTimeout = 8 * time.Second

type ReviewSettings struct {
	Schema          int  `json:"schema"`
	AutoOnReconnect bool `json:"auto_on_reconnect"`
}
type ReviewItem struct {
	ID         string `json:"id"`
	Mount      string `json:"mount"`
	Path       string `json:"path"`
	QueueState string `json:"queue_state"`
	State      string `json:"state"`
	Detail     string `json:"detail"`
}
type ReviewReport struct {
	Schema      int          `json:"schema"`
	CheckedUnix int64        `json:"checked_unix"`
	Mount       string       `json:"mount,omitempty"`
	Items       []ReviewItem `json:"items"`
}
type reviewEnvelope[T any] struct {
	Value  T      `json:"value"`
	SHA256 string `json:"sha256"`
}
type ReviewStatus struct {
	Settings ReviewSettings `json:"settings"`
	Report   *ReviewReport  `json:"report,omitempty"`
}

func sealReview[T any](v T) ([]byte, error) {
	body, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	h := sha256.Sum256(body)
	return json.Marshal(reviewEnvelope[T]{Value: v, SHA256: hex.EncodeToString(h[:])})
}
func openReview[T any](data []byte, value *T) error {
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	var env reviewEnvelope[T]
	if err := dec.Decode(&env); err != nil {
		return err
	}
	var trailing any
	if dec.Decode(&trailing) != io.EOF {
		return errors.New("review trailing or invalid data")
	}
	b, err := json.Marshal(env.Value)
	if err != nil {
		return err
	}
	h := sha256.Sum256(b)
	if !strings.EqualFold(env.SHA256, hex.EncodeToString(h[:])) {
		return errors.New("review state checksum mismatch")
	}
	*value = env.Value
	return nil
}
func (s *Store) reviewSettingsLocked() (ReviewSettings, error) {
	b, err := atomicfile.Read(s.dir+"/writes", "review-settings-v1.json", 2048)
	if errors.Is(err, os.ErrNotExist) {
		return ReviewSettings{Schema: 1}, nil
	}
	if err != nil {
		return ReviewSettings{}, err
	}
	var setting ReviewSettings
	if err = openReview(b, &setting); err != nil {
		return setting, err
	}
	if setting.Schema != 1 {
		return ReviewSettings{}, errors.New("invalid review settings schema")
	}
	return setting, nil
}
func (s *Store) ReviewSettings() (ReviewSettings, error) {
	release, err := s.editLock()
	if err != nil {
		return ReviewSettings{}, err
	}
	defer release()
	return s.reviewSettingsLocked()
}
func (s *Store) SetReviewAuto(enabled bool) (ReviewSettings, error) {
	release, err := s.editLock()
	if err != nil {
		return ReviewSettings{}, err
	}
	defer release()
	if _, err = s.reviewSettingsLocked(); err != nil {
		return ReviewSettings{}, err
	}
	value := ReviewSettings{Schema: 1, AutoOnReconnect: enabled}
	b, err := sealReview(value)
	if err != nil {
		return ReviewSettings{}, err
	}
	if err = atomicfile.Write(s.dir+"/writes", "review-settings-v1.json", b); err != nil {
		return ReviewSettings{}, err
	}
	return value, nil
}
func (s *Store) ReviewStatus() (ReviewStatus, error) {
	release, err := s.editLock()
	if err != nil {
		return ReviewStatus{}, err
	}
	defer release()
	settings, err := s.reviewSettingsLocked()
	if err != nil {
		return ReviewStatus{}, err
	}
	result := ReviewStatus{Settings: settings}
	b, err := atomicfile.Read(s.dir+"/writes", "review-v1.json", 1<<20)
	if errors.Is(err, os.ErrNotExist) {
		return result, nil
	}
	if err != nil {
		return ReviewStatus{}, err
	}
	var report ReviewReport
	if err = openReview(b, &report); err != nil {
		return ReviewStatus{}, err
	}
	if report.Schema != 1 || report.CheckedUnix <= 0 || len(report.Items) > maxDrafts || (report.Mount != "" && !safeName.MatchString(report.Mount)) {
		return ReviewStatus{}, errors.New("invalid review report")
	}
	for _, item := range report.Items {
		if len(item.ID) != 32 || !isHex(item.ID) || !safeName.MatchString(item.Mount) || validatePath(item.Path) != nil {
			return ReviewStatus{}, errors.New("invalid review entry")
		}
	}
	result.Report = &report
	return result, nil
}
func (s *Store) ReviewQueue(ctx context.Context, mount string) (ReviewReport, error) {
	if mount != "" && !safeName.MatchString(mount) {
		return ReviewReport{}, errors.New("invalid review mount")
	}
	release, err := s.editLock()
	if err != nil {
		return ReviewReport{}, err
	}
	journal, err := s.readEdits()
	release()
	if err != nil {
		return ReviewReport{}, err
	}
	report := ReviewReport{Schema: 1, Mount: mount, Items: []ReviewItem{}}
	promotions := make(map[string]Edit)
	for _, edit := range journal.Edits {
		if mount != "" && edit.Mount != mount {
			continue
		}
		if err = ctx.Err(); err != nil {
			return ReviewReport{}, err
		}
		item := ReviewItem{ID: edit.ID, Mount: edit.Mount, Path: edit.Path, QueueState: edit.State, State: "REVIEW_REQUIRED", Detail: "No remote files were modified"}
		switch edit.State {
		case "UPLOADED_COPY":
			item.State = "COPY_RECORDED"
			item.Detail = "Separate remote copy previously recorded; no automatic overwrite or retry"
		case "QUEUED", "UPLOAD_INDETERMINATE":
			checkedCtx, cancel := context.WithTimeout(ctx, reviewItemTimeout)
			m, verifyErr := s.verifyQueued(edit)
			if verifyErr != nil {
				item.State = "LOCAL_CONFLICT"
				item.Detail = "Private edit missing, corrupted, or remote identity changed"
			} else if edit.State == "QUEUED" {
				check := s.compare(checkedCtx, m, edit)
				item.State = check.State
				item.Detail = check.Detail
			} else {
				// Read ONLY the unique immutable destination derived from the edit ID.
				// Never trust a path from the journal as an arbitrary probe target.
				expected := "Skybind-Offline-Edits/" + edit.ID + "/" + filepath.Base(edit.Path)
				if edit.UploadedRemoteCopy != expected {
					item.State = "LOCAL_CONFLICT"
					item.Detail = "Recorded destination identity mismatch; manual review required"
				} else {
					meta, statErr := s.stat(checkedCtx, m, expected)
					if statErr != nil {
						item.State = "UNKNOWN"
						item.Detail = "Remote copy not inspectable; absence is not proven and retry is forbidden"
					} else if meta.Size != edit.Size {
						item.State = "CONFLICT"
						item.Detail = "Separate remote copy size differs; manual review required"
					} else if remoteSHA, ok := remoteSHA256(meta.Hashes); !ok {
						item.State = "REVIEW_REQUIRED"
						item.Detail = "Remote copy size matches but no SHA-256; manual verification required"
					} else if !strings.EqualFold(remoteSHA, edit.SHA256) {
						item.State = "CONFLICT"
						item.Detail = "Remote copy SHA-256 differs; manual review required"
					} else {
						item.State = "VERIFIED_REMOTE_COPY"
						item.Detail = "Separate destination SHA-256 verified; original was not targeted"
						promotions[edit.ID] = edit
					}
				}
			}
			cancel()
		default:
			return ReviewReport{}, errors.New("invalid write state")
		}
		if err = ctx.Err(); err != nil {
			return ReviewReport{}, err
		}
		report.Items = append(report.Items, item)
	}
	if err = ctx.Err(); err != nil {
		return ReviewReport{}, err
	}
	// All remote probing is finished; reacquire the private lock before committing.
	// Accept a promotion only if the full original journal item is still identical.
	release, err = s.editLock()
	if err != nil {
		return ReviewReport{}, err
	}
	defer release()
	latest, err := s.readEdits()
	if err != nil {
		return ReviewReport{}, err
	}
	changed := false
	for i, e := range latest.Edits {
		old, ok := promotions[e.ID]
		if !ok || e != old || e.State != "UPLOAD_INDETERMINATE" {
			continue
		}
		e.State = "UPLOADED_COPY"
		e.RemoteVerification = "remote-sha256-verified"
		latest.Edits[i] = e
		changed = true
	}
	if changed {
		if err = s.saveEdits(latest); err != nil {
			return ReviewReport{}, err
		}
	}
	report.CheckedUnix = time.Now().Unix()
	if report.CheckedUnix <= 0 {
		return ReviewReport{}, fmt.Errorf("invalid review clock")
	}
	b, err := sealReview(report)
	if err != nil {
		return ReviewReport{}, err
	}
	if err = atomicfile.Write(s.dir+"/writes", "review-v1.json", b); err != nil {
		return ReviewReport{}, err
	}
	return report, nil
}
func remoteSHA256(hashes map[string]string) (string, bool) {
	for key, value := range hashes {
		if strings.EqualFold(key, "SHA-256") && len(value) == 64 && isHex(value) {
			return value, true
		}
	}
	return "", false
}
