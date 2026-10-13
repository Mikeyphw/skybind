package offline

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"sync"
	"time"
)

// TaskManager executes a single bounded offline copy/export outside the RPC's
// 15-second response deadline. The persistent manifest remains the source of
// truth after a crash. Task status is ephemeral, small and contains no secrets.
// This is NOT a general-purpose shell/job executor.
type TaskManager struct {
	mu     sync.Mutex
	store  *Store
	tasks  []TaskStatus
	active string
	cancel context.CancelFunc
}
type TaskStatus struct {
	ID           string `json:"id"`
	Kind         string `json:"kind"`
	Mount        string `json:"mount"`
	Path         string `json:"path"`
	State        string `json:"state"`
	Started      int64  `json:"started_unix"`
	Finished     int64  `json:"finished_unix,omitempty"`
	Pinned       int    `json:"pinned_count,omitempty"`
	Detail       string `json:"detail,omitempty"`
	ExportedPath string `json:"exported_path,omitempty"`
}

func NewTaskManager(store *Store) *TaskManager { return &TaskManager{store: store} }
func (m *TaskManager) Busy() bool              { m.mu.Lock(); defer m.mu.Unlock(); return m.active != "" }
func (m *TaskManager) Tasks() []TaskStatus {
	m.mu.Lock()
	defer m.mu.Unlock()
	result := make([]TaskStatus, len(m.tasks))
	copy(result, m.tasks)
	return result
}
func (m *TaskManager) Start(kind, mount, rel string) (TaskStatus, error) {
	if kind != "pin" && kind != "pin-dir" && kind != "export" && kind != "view" {
		return TaskStatus{}, errors.New("offline_invalid_action")
	}
	if !safeName.MatchString(mount) || (kind != "view" && validatePath(rel) != nil) || (kind == "view" && rel != "") {
		return TaskStatus{}, errors.New("offline_invalid_selection")
	}
	if m.store == nil {
		return TaskStatus{}, errors.New("offline_unavailable")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.active != "" {
		return TaskStatus{}, errors.New("offline_busy")
	}
	var b [16]byte
	if _, err := rand.Read(b[:]); err != nil {
		return TaskStatus{}, errors.New("offline_unavailable")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	id := hex.EncodeToString(b[:])
	t := TaskStatus{ID: id, Kind: kind, Mount: mount, Path: rel, State: "RUNNING", Started: time.Now().Unix()}
	m.tasks = append(m.tasks, t)
	if len(m.tasks) > 8 {
		m.tasks = append([]TaskStatus(nil), m.tasks[len(m.tasks)-8:]...)
	}
	m.active = id
	m.cancel = cancel
	go m.run(ctx, cancel, id, kind, mount, rel)
	return t, nil
}
func (m *TaskManager) run(ctx context.Context, cancel context.CancelFunc, id, kind, mount, rel string) {
	defer cancel()
	var count int
	var dest string
	var err error
	if kind == "export" {
		dest, err = m.store.ExportContext(ctx, mount, rel)
	} else if kind == "view" {
		dest, err = m.store.PublishView(ctx, mount)
	} else {
		count, err = m.store.Pin(ctx, mount, rel, kind == "pin-dir")
	}
	m.mu.Lock()
	defer m.mu.Unlock()
	for i := range m.tasks {
		if m.tasks[i].ID != id {
			continue
		}
		t := &m.tasks[i]
		t.Finished = time.Now().Unix()
		t.Pinned = count
		if ctx.Err() != nil {
			t.State = "CANCELLED"
			t.Detail = "Operation cancelled or timed out; already verified pins remain saved"
		} else if err != nil {
			t.State = "FAILED"
			t.Detail = "Offline operation failed; private pins remain untouched"
		} else {
			t.State = "SUCCEEDED"
			t.ExportedPath = dest
		}
		break
	}
	if m.active == id {
		m.active = ""
		m.cancel = nil
	}
}
func (m *TaskManager) Cancel(id string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if m.active != id || m.cancel == nil {
		return errors.New("offline_task_not_running")
	}
	m.cancel()
	return nil
}
