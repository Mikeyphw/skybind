// Package journal durably records operation lifecycle before side effects.
package journal

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"skybind/internal/atomicfile"
	"sort"
	"sync"
	"time"
)

type State string

const (
	Running     State = "running"
	Succeeded   State = "succeeded"
	Failed      State = "failed"
	Interrupted State = "interrupted"
	Cancelled   State = "cancelled"
)

type Record struct {
	ID          string `json:"id"`
	Action      string `json:"action"`
	RequestID   string `json:"request_id,omitempty"`
	RunID       string `json:"run_id,omitempty"`
	Owner       uint32 `json:"owner"`
	PID         int    `json:"pid"`
	Started     string `json:"started"`
	Finished    string `json:"finished,omitempty"`
	State       State  `json:"state"`
	Stage       string `json:"stage"`
	Cancellable bool   `json:"cancellable"`
	ErrorCode   string `json:"error_code,omitempty"`
}
type Journal struct {
	mu  sync.Mutex
	dir string
}

func Open(dir string) (*Journal, error) {
	j := &Journal{dir: dir}
	if _, err := os.ReadDir(dir); err != nil {
		return nil, err
	}
	if e := j.interrupt(); e != nil {
		return nil, e
	}
	return j, nil
}
func (j *Journal) write(r Record) error {
	b, e := json.Marshal(r)
	if e != nil {
		return e
	}
	return atomicfile.Write(j.dir, r.ID+".json", b)
}
func (j *Journal) Start(action string) (Record, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	if action == "" {
		return Record{}, errors.New("empty operation")
	}
	id := make([]byte, 16)
	if _, e := rand.Read(id); e != nil {
		return Record{}, e
	}
	r := Record{ID: hex.EncodeToString(id), Action: action, Owner: uint32(os.Geteuid()), PID: os.Getpid(), Started: time.Now().UTC().Format(time.RFC3339Nano), State: Running, Stage: "reserved", Cancellable: true}
	return r, j.write(r)
}

// StartRequest reserves a durable mutation record before any handler side effect.
// Synchronous handlers have no genuine asynchronous cancellation mechanism;
// advertising one would permit a false cancelled state while work continues.
func (j *Journal) StartRequest(action, requestID string) (Record, error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	if action == "" || requestID == "" || len(requestID) > 80 {
		return Record{}, errors.New("invalid mutation identity")
	}
	for _, c := range requestID {
		if !(c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || c == '_' || c == '-') {
			return Record{}, errors.New("invalid request identity")
		}
	}
	id := make([]byte, 16)
	if _, e := rand.Read(id); e != nil {
		return Record{}, e
	}
	r := Record{ID: hex.EncodeToString(id), Action: action, RequestID: requestID, Owner: uint32(os.Geteuid()), PID: os.Getpid(), Started: time.Now().UTC().Format(time.RFC3339Nano), State: Running, Stage: "reserved", Cancellable: false}
	return r, j.write(r)
}

func (j *Journal) Update(r Record) error {
	j.mu.Lock()
	defer j.mu.Unlock()
	old, e := j.read(r.ID)
	if e != nil {
		return e
	}
	if old.State != Running || old.Owner != r.Owner || old.Action != r.Action || old.Started != r.Started || old.RequestID != r.RequestID || old.RunID != r.RunID && old.RunID != "" {
		return errors.New("operation owner/state mismatch")
	}
	if r.State != Running && r.State != Succeeded && r.State != Failed && r.State != Cancelled {
		return errors.New("invalid transition")
	}
	if !r.Cancellable && r.State == Cancelled {
		return errors.New("cannot cancel committed span")
	}
	if r.State != Running {
		r.Finished = time.Now().UTC().Format(time.RFC3339Nano)
	}
	return j.write(r)
}
func (j *Journal) read(id string) (Record, error) {
	if len(id) != 32 {
		return Record{}, errors.New("invalid id")
	}
	b, e := atomicfile.Read(j.dir, id+".json", 8192)
	if e != nil {
		return Record{}, e
	}
	var r Record
	if e = json.Unmarshal(b, &r); e != nil {
		return Record{}, e
	}
	if r.ID != id {
		return Record{}, errors.New("record identity mismatch")
	}
	return r, nil
}
func (j *Journal) Get(id string) (Record, error) { j.mu.Lock(); defer j.mu.Unlock(); return j.read(id) }

// ByRequest resolves the public request identity to a private journal record.
// Requests are bounded by the same 10k-entry ceiling as List.
func (j *Journal) ByRequest(requestID string) (Record, error) {
	if requestID == "" || len(requestID) > 80 {
		return Record{}, errors.New("invalid request id")
	}
	records, e := j.List()
	if e != nil {
		return Record{}, e
	}
	for _, rec := range records {
		if rec.RequestID == requestID {
			return rec, nil
		}
	}
	return Record{}, os.ErrNotExist
}
func (j *Journal) List() (out []Record, err error) {
	j.mu.Lock()
	defer j.mu.Unlock()
	names, e := os.ReadDir(j.dir)
	if e != nil {
		return nil, e
	}
	if len(names) > 10000 {
		return nil, errors.New("journal overflow")
	}
	for _, f := range names {
		n := f.Name()
		if !f.Type().IsRegular() || len(n) != 37 || n[32:] != ".json" {
			continue
		}
		r, e := j.read(n[:32])
		if e != nil {
			return nil, e
		}
		out = append(out, r)
	}
	sort.Slice(out, func(i, k int) bool { return out[i].Started > out[k].Started })
	return out, nil
}
func (j *Journal) interrupt() error {
	a, e := j.List()
	if e != nil {
		return e
	}
	for _, r := range a {
		if r.State == Running {
			r.State = Interrupted
			r.Stage = "recovered_after_exit"
			r.Cancellable = false
			r.Finished = time.Now().UTC().Format(time.RFC3339Nano)
			if e = j.write(r); e != nil {
				return e
			}
		}
	}
	return nil
}
