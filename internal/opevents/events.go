// Package opevents provides a bounded, durable, credential-free operation
// event feed. Event IDs are monotonic across daemon restarts and polls may
// replay missed events. No user-supplied paths, command lines or stderr enter it.
package opevents

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"os"
	"regexp"
	"skybind/internal/atomicfile"
	"sync"
	"time"
)

const fileName = "events-v1.json"
const maxEvents = 512
const maxBytes = 1 << 19

var idRE = regexp.MustCompile(`^[a-f0-9]{32}$`)

// Progress has only numeric, nonsensitive fields. Unknown totals/ETA remain
// absent instead of a made-up completion percentage.
type Progress struct {
	Bytes               int64    `json:"bytes"`
	SpeedBytesPerSecond float64  `json:"speed_bytes_per_second"`
	ETASeconds          int64    `json:"eta_seconds,omitempty"`
	TotalBytes          *int64   `json:"total_bytes,omitempty"`
	Percent             *float64 `json:"percent,omitempty"`
	FilesDone           *int64   `json:"files_done,omitempty"`
	FilesTotal          *int64   `json:"files_total,omitempty"`
	ChecksDone          *int64   `json:"checks_done,omitempty"`
	ChecksTotal         *int64   `json:"checks_total,omitempty"`
	Errors              *int64   `json:"errors,omitempty"`
	RetryError          *bool    `json:"retry_error,omitempty"`
	TransferRetries     *int64   `json:"transfer_retries,omitempty"`
}

type Event struct {
	Sequence    uint64    `json:"sequence"`
	UnixMillis  int64     `json:"unix_millis"`
	OperationID string    `json:"operation_id"`
	RunID       string    `json:"run_id,omitempty"`
	Operation   string    `json:"operation"`
	Type        string    `json:"type"`
	State       string    `json:"state"`
	Phase       string    `json:"phase"`
	Progress    *Progress `json:"progress,omitempty"`
}

type persisted struct {
	SchemaVersion int     `json:"schema_version"`
	LastSequence  uint64  `json:"last_sequence"`
	Events        []Event `json:"events"`
}

type Page struct {
	SchemaVersion int     `json:"schema_version"`
	Events        []Event `json:"events"`
	NextCursor    uint64  `json:"next_cursor"`
	OldestCursor  uint64  `json:"oldest_cursor"`
	LatestCursor  uint64  `json:"latest_cursor"`
	HasMore       bool    `json:"has_more"`
	CursorReset   bool    `json:"cursor_reset"`
	Degraded      bool    `json:"degraded"`
	Gap           bool    `json:"gap"`
}

type Store struct {
	mu       sync.Mutex
	dir      string
	data     persisted
	changed  chan struct{}
	now      func() time.Time
	degraded bool
}

func allowedType(t string) bool {
	switch t {
	case "operation.started", "operation.accepted", "operation.succeeded", "operation.failed", "job.started", "job.progress", "job.cancelling", "job.completed", "job.failed", "job.cancelled", "job.interrupted":
		return true
	}
	return false
}
func safeEvent(e Event) bool {
	if !idRE.MatchString(e.OperationID) || (e.RunID != "" && !idRE.MatchString(e.RunID)) || !allowedType(e.Type) || len(e.Operation) == 0 || len(e.Operation) > 90 || len(e.State) > 20 || len(e.Phase) > 30 {
		return false
	}
	for _, v := range []string{e.Operation, e.State, e.Phase} {
		for _, c := range v {
			if !(c >= 'a' && c <= 'z' || c >= '0' && c <= '9' || c == '_' || c == '.' || c == '-') {
				return false
			}
		}
	}
	if e.Progress != nil {
		p := e.Progress
		if p.Bytes < 0 || p.Bytes > 1<<60 || math.IsNaN(p.SpeedBytesPerSecond) || math.IsInf(p.SpeedBytesPerSecond, 0) || p.SpeedBytesPerSecond < 0 || p.SpeedBytesPerSecond > 1e15 || p.ETASeconds < 0 || p.ETASeconds > 1<<40 {
			return false
		}
		for _, n := range []*int64{p.TotalBytes, p.FilesDone, p.FilesTotal, p.ChecksDone, p.ChecksTotal, p.Errors, p.TransferRetries} {
			if n != nil && (*n < 0 || *n > 1<<60) {
				return false
			}
		}
		if p.Percent != nil && (math.IsNaN(*p.Percent) || math.IsInf(*p.Percent, 0) || *p.Percent < 0 || *p.Percent > 100) {
			return false
		}
	}
	return true
}
func Open(dir string) (*Store, error) {
	s := &Store{dir: dir, changed: make(chan struct{}), now: time.Now, data: persisted{SchemaVersion: 1, Events: []Event{}}}
	b, err := atomicfile.Read(dir, fileName, maxBytes)
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	if err = json.Unmarshal(b, &s.data); err != nil {
		return nil, err
	}
	if s.data.SchemaVersion != 1 || len(s.data.Events) > maxEvents || s.data.LastSequence == 0 && len(s.data.Events) != 0 {
		return nil, errors.New("invalid operation event state")
	}
	var previous uint64
	for i, e := range s.data.Events {
		if !safeEvent(e) || e.Sequence <= previous || e.Sequence > s.data.LastSequence || i > 0 && e.Sequence != previous+1 {
			return nil, errors.New("corrupt operation event sequence")
		}
		previous = e.Sequence
	}
	if len(s.data.Events) > 0 && previous != s.data.LastSequence {
		return nil, errors.New("invalid last event sequence")
	}
	return s, nil
}

// Append commits before notifying readers. Failed persistence never advances
// a sequence or emits an event that would disappear after daemon restart.
func (s *Store) Append(e Event) (result error) {
	if !safeEvent(e) {
		return errors.New("invalid sanitized event")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	defer func() { s.degraded = result != nil }()
	if s.data.LastSequence == ^uint64(0) {
		return errors.New("event counter exhausted")
	}
	e.Sequence = s.data.LastSequence + 1
	e.UnixMillis = s.now().UnixMilli()
	next := persisted{SchemaVersion: 1, LastSequence: e.Sequence, Events: append(append([]Event(nil), s.data.Events...), e)}
	if len(next.Events) > maxEvents {
		next.Events = next.Events[len(next.Events)-maxEvents:]
	}
	b, err := json.Marshal(next)
	if err != nil {
		return err
	}
	if len(b) > maxBytes {
		return errors.New("event state oversized")
	}
	if err = atomicfile.Write(s.dir, fileName, b); err != nil {
		return err
	}
	s.data = next
	close(s.changed)
	s.changed = make(chan struct{})
	return nil
}
func (s *Store) page(cursor uint64, limit int, filter string) Page {
	p := Page{SchemaVersion: 1, Events: []Event{}, NextCursor: cursor, LatestCursor: s.data.LastSequence, Degraded: s.degraded}
	if cursor > s.data.LastSequence {
		p.CursorReset = true
		p.NextCursor = s.data.LastSequence
		cursor = s.data.LastSequence
	}
	if len(s.data.Events) == 0 {
		return p
	}
	oldest := s.data.Events[0].Sequence
	p.OldestCursor = oldest
	if cursor < oldest-1 {
		p.Gap = true
		cursor = oldest - 1
		p.NextCursor = cursor
	}
	// Iterate ordered events; skip nonmatching events while advancing cursor.
	for _, e := range s.data.Events {
		if e.Sequence <= cursor {
			continue
		}
		if filter != "" && e.OperationID != filter && e.RunID != filter {
			p.NextCursor = e.Sequence
			continue
		}
		if len(p.Events) >= limit {
			p.HasMore = true
			break
		}
		p.Events = append(p.Events, e)
		p.NextCursor = e.Sequence
	}
	return p
}

// Poll supports a short bounded wait that is safe for both Unix RPC and the
// callback-oriented embedded WebUI. A cursor gap is always explicit.
func (s *Store) Poll(ctx context.Context, cursor uint64, limit int, filter string, wait time.Duration) (Page, error) {
	if limit < 1 || limit > 64 || wait < 0 || wait > 5*time.Second || (filter != "" && !idRE.MatchString(filter)) {
		return Page{}, errors.New("invalid event query")
	}
	s.mu.Lock()
	p := s.page(cursor, limit, filter)
	if len(p.Events) > 0 || p.Gap || p.HasMore || p.CursorReset || wait == 0 {
		s.mu.Unlock()
		return p, nil
	}
	ch := s.changed
	s.mu.Unlock()
	timer := time.NewTimer(wait)
	defer timer.Stop()
	select {
	case <-ch:
	case <-timer.C:
	case <-ctx.Done():
		return Page{}, ctx.Err()
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.page(cursor, limit, filter), nil
}
