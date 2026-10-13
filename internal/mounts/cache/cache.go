// Package cache offers bounded, proof-protected maintenance of Skybind-owned
// VFS cache trees. It never follows symlinks or accepts a client path.
package cache

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
	"unsafe"
)

type Entry struct {
	Path  string `json:"path"`
	Size  int64  `json:"size"`
	MTime int64  `json:"mtime"`
	Inode uint64 `json:"inode"`
}
type Snapshot struct {
	Name   string `json:"name"`
	Count  int    `json:"count"`
	Bytes  int64  `json:"bytes"`
	Digest string `json:"digest"`
}
type Preview struct {
	Snapshot      Snapshot `json:"snapshot"`
	Action        string   `json:"action"`
	BytesToRemove int64    `json:"bytes_to_remove"`
	Proof         string   `json:"proof"`
}
type Manager struct {
	mu      sync.Mutex
	root    string
	proofs  *previewproof.Store
	running func(string) bool
}

func Canonical(running func(string) bool) *Manager {
	return newManager(filepath.Join(paths.StateRoot, "cache"), running)
}
func newManager(root string, running func(string) bool) *Manager {
	return &Manager{root: root, proofs: previewproof.New(), running: running}
}
func validName(s string) bool {
	if len(s) == 0 || len(s) > 63 || s[0] < 'A' {
		return false
	}
	for _, c := range s {
		if !((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_') {
			return false
		}
	}
	return true
}
func openDir(root string) (int, error) { return paths.OpenVerifiedDirectory(root) }
func subDir(fd int, name string) (int, error) {
	if name == "" || name == "." || name == ".." || strings.ContainsAny(name, "/\\\x00") {
		return -1, errors.New("invalid cache component")
	}
	sub, e := syscall.Openat(fd, name, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		return -1, e
	}
	var st syscall.Stat_t
	if e = syscall.Fstat(sub, &st); e != nil || st.Uid != uint32(os.Geteuid()) || st.Mode&0777 != 0700 {
		syscall.Close(sub)
		return -1, errors.New("unsafe cache directory")
	}
	return sub, nil
}
func names(fd int) ([]string, error) {
	d, e := syscall.Dup(fd)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(d), "cache-dir")
	defer f.Close()
	n, e := f.Readdirnames(-1)
	sort.Strings(n)
	return n, e
}

// statAt uses an O_PATH descriptor so a symlink can be identified without
// following it. This works on Android/Linux without a third-party dependency.
func statAt(parent int, name string, st *syscall.Stat_t) error {
	fd, err := syscall.Openat(parent, name, 0x200000|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	return syscall.Fstat(fd, st)
}
func walk(fd int, relative string, depth int, out *[]Entry) error {
	if depth > 24 || len(*out) > 50000 {
		return errors.New("cache traversal limit")
	}
	list, err := names(fd)
	if err != nil {
		return err
	}
	for _, name := range list {
		if name == "." || name == ".." || strings.ContainsAny(name, "/\\\x00") {
			return errors.New("invalid cache directory entry")
		}
		var st syscall.Stat_t
		if err := statAt(fd, name, &st); err != nil {
			return err
		}
		path := name
		if relative != "" {
			path = relative + "/" + name
		}
		switch st.Mode & syscall.S_IFMT {
		case syscall.S_IFDIR:
			sub, e := subDir(fd, name)
			if e != nil {
				return e
			}
			e = walk(sub, path, depth+1, out)
			syscall.Close(sub)
			if e != nil {
				return e
			}
		case syscall.S_IFREG:
			if st.Nlink != 1 || st.Uid != uint32(os.Geteuid()) {
				return errors.New("cache file not exclusively owned")
			}
			*out = append(*out, Entry{Path: path, Size: st.Size, MTime: st.Mtim.Sec, Inode: st.Ino})
		default:
			return errors.New("unsafe cache entry type")
		}
	}
	return nil
}
func (m *Manager) entries(name string) ([]Entry, error) {
	if !validName(name) {
		return nil, errors.New("invalid mount name")
	}
	fd, e := openDir(m.root)
	if e != nil {
		return nil, e
	}
	defer syscall.Close(fd)
	sub, e := subDir(fd, name)
	if e != nil {
		return nil, e
	}
	defer syscall.Close(sub)
	out := []Entry{}
	e = walk(sub, "", 0, &out)
	return out, e
}
func snapshot(name string, rows []Entry) Snapshot {
	h := sha256.New()
	v := Snapshot{Name: name, Count: len(rows)}
	for _, r := range rows {
		v.Bytes += r.Size
		fmt.Fprintf(h, "%s:%d:%d:%d\n", r.Path, r.Size, r.MTime, r.Inode)
	}
	v.Digest = hex.EncodeToString(h.Sum(nil))
	return v
}
func (m *Manager) Status(name string) (Snapshot, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	rows, e := m.entries(name)
	if e != nil {
		return Snapshot{}, e
	}
	return snapshot(name, rows), nil
}
func (m *Manager) Preview(name, action string, targetBytes int64) (Preview, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if action != "clear" && action != "prune" && action != "forget" {
		return Preview{}, errors.New("unknown cache action")
	}
	if m.running != nil && m.running(name) {
		return Preview{}, errors.New("cannot modify running mount cache")
	}
	if targetBytes < 0 {
		return Preview{}, errors.New("invalid prune target")
	}
	rows, e := m.entries(name)
	if e != nil {
		return Preview{}, e
	}
	s := snapshot(name, rows)
	if s.Count > 0 {
		return Preview{}, errors.New("cache preserved: stopped VFS may contain pending uploads; clean state cannot be proven")
	}
	amount := s.Bytes
	if action == "prune" {
		if targetBytes >= s.Bytes {
			amount = 0
		} else {
			amount = s.Bytes - targetBytes
		}
	}
	p, e := m.proofs.Issue(previewproof.Binding{Action: "cache." + action, Subject: name, Digest: s.Digest + ":" + strconv.FormatInt(targetBytes, 10)}, 2*time.Minute)
	return Preview{Snapshot: s, Action: action, BytesToRemove: amount, Proof: p}, e
}
func (m *Manager) Apply(name, action, proof string, targetBytes int64) (Snapshot, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if action != "clear" && action != "prune" && action != "forget" {
		return Snapshot{}, errors.New("unknown cache action")
	}
	if m.running != nil && m.running(name) {
		return Snapshot{}, errors.New("cannot modify running mount cache")
	}
	if targetBytes < 0 {
		return Snapshot{}, errors.New("invalid target")
	}
	rows, e := m.entries(name)
	if e != nil {
		return Snapshot{}, e
	}
	s := snapshot(name, rows)
	if s.Count > 0 {
		return Snapshot{}, errors.New("cache preserved: persistent writeback status unverified")
	}
	if e = m.proofs.Consume(proof, previewproof.Binding{Action: "cache." + action, Subject: name, Digest: s.Digest + ":" + strconv.FormatInt(targetBytes, 10)}); e != nil {
		return Snapshot{}, e
	}
	if action == "prune" {
		sort.Slice(rows, func(i, j int) bool { return rows[i].MTime < rows[j].MTime })
	}
	remove := int64(0)
	for _, r := range rows {
		if action == "prune" && s.Bytes-remove <= targetBytes {
			break
		}
		if e = removeOwned(m.root, name, r.Path, r.Inode); e != nil {
			return Snapshot{}, e
		}
		remove += r.Size
	}
	if action == "forget" {
		if e = removeEmptyDirs(m.root, name); e != nil {
			return Snapshot{}, e
		}
	}
	next, e := m.entries(name)
	if e != nil {
		return Snapshot{}, e
	}
	return snapshot(name, next), nil
}
func removeOwned(root, name, rel string, inode uint64) error {
	if !validName(name) {
		return errors.New("invalid name")
	}
	fd, e := openDir(root)
	if e != nil {
		return e
	}
	defer syscall.Close(fd)
	sub, e := subDir(fd, name)
	if e != nil {
		return e
	}
	parts := strings.Split(rel, "/")
	for _, component := range parts[:len(parts)-1] {
		next, err := subDir(sub, component)
		if err != nil {
			return err
		}
		syscall.Close(sub)
		sub = next
	}
	defer func() { _ = syscall.Close(sub) }()
	leaf := parts[len(parts)-1]
	if leaf == "" || leaf == "." || leaf == ".." {
		return errors.New("unsafe leaf")
	}
	var st syscall.Stat_t
	if e = statAt(sub, leaf, &st); e != nil {
		return e
	}
	if st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Ino != inode || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 {
		return errors.New("cache object changed since preview")
	}
	return syscall.Unlinkat(sub, leaf)
}

// EnsureCanonical creates only the configured mount's cache leaf under the
// already root-private cache directory. No client path is accepted.
func EnsureCanonical(name string) error {
	if !validName(name) {
		return errors.New("invalid cache owner name")
	}
	parent, err := openDir(filepath.Join(paths.StateRoot, "cache"))
	if err != nil {
		return err
	}
	defer syscall.Close(parent)
	err = syscall.Mkdirat(parent, name, 0700)
	if err != nil && !errors.Is(err, syscall.EEXIST) {
		return err
	}
	child, err := subDir(parent, name)
	if err != nil {
		return err
	}
	return syscall.Close(child)
}

// AutoPruneStopped enforces high/low-water bounds only when the mount is not
// active. It deliberately does not evict an open VFS cache entry.
func (m *Manager) AutoPruneStopped(name string, maxBytes int64, high, low int) (Snapshot, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	if maxBytes <= 0 || high <= 0 || high > 100 || low < 0 || low >= high {
		return Snapshot{}, errors.New("invalid cache water marks")
	}
	if m.running != nil && m.running(name) {
		return Snapshot{}, errors.New("cache active; defer automatic prune")
	}
	rows, err := m.entries(name)
	if err != nil {
		return Snapshot{}, err
	}
	before := snapshot(name, rows)
	if before.Count > 0 {
		return before, errors.New("auto-prune disabled: persistent dirty-cache state unknown")
	}
	if before.Bytes <= maxBytes*int64(high)/100 {
		return before, nil
	}
	target := maxBytes * int64(low) / 100
	sort.Slice(rows, func(i, j int) bool { return rows[i].MTime < rows[j].MTime })
	removed := int64(0)
	for _, row := range rows {
		if before.Bytes-removed <= target {
			break
		}
		if e := removeOwned(m.root, name, row.Path, row.Inode); e != nil {
			return Snapshot{}, e
		}
		removed += row.Size
	}
	remaining, e := m.entries(name)
	if e != nil {
		return Snapshot{}, e
	}
	return snapshot(name, remaining), nil
}

const linuxAtRemovedir = 0x200

func unlinkDirectoryAt(parent int, name string) error {
	p, err := syscall.BytePtrFromString(name)
	if err != nil {
		return err
	}
	_, _, errno := syscall.Syscall(syscall.SYS_UNLINKAT, uintptr(parent), uintptr(unsafe.Pointer(p)), uintptr(linuxAtRemovedir))
	if errno != 0 {
		return errno
	}
	return nil
}

// removeEmptyDirs acts on live directory descriptors and never follows links.
func removeEmptyDirs(root, name string) error {
	fd, e := openDir(root)
	if e != nil {
		return e
	}
	defer syscall.Close(fd)
	mount, e := subDir(fd, name)
	if e != nil {
		return e
	}
	defer syscall.Close(mount)
	return removeEmptyChildDirs(mount, 0)
}
func removeEmptyChildDirs(dir, depth int) error {
	if depth > 24 {
		return errors.New("cache depth exceeded")
	}
	list, e := names(dir)
	if e != nil {
		return e
	}
	for _, name := range list {
		var st syscall.Stat_t
		if e = statAt(dir, name, &st); e != nil {
			return e
		}
		if st.Mode&syscall.S_IFMT != syscall.S_IFDIR {
			return errors.New("cache contains unexpected item during forget")
		}
		fd, err := subDir(dir, name)
		if err != nil {
			return err
		}
		err = removeEmptyChildDirs(fd, depth+1)
		syscall.Close(fd)
		if err != nil {
			return err
		}
		if err = unlinkDirectoryAt(dir, name); err != nil {
			return err
		}
	}
	return nil
}
