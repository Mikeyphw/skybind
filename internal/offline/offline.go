// Package offline provides explicit, root-private read-only snapshots of complete
// remote files. It does NOT treat rclone's potentially sparse VFS cache as offline.
package offline

import (
	"bytes"
	"context"
	"crypto/md5"
	"crypto/sha1"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/config"
	"skybind/internal/paths"
	"sort"
	"strings"
	"syscall"
	"time"
)

const (
	defaultQuota int64 = 8 << 30
	maxQuota     int64 = 64 << 30
	maxOnePin    int64 = 4 << 30
	maxFiles           = 256
	minFree      int64 = 512 << 20
)

var safeName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)

type RemoteFile struct {
	Path    string            `json:"Path"`
	Size    int64             `json:"Size"`
	ModTime string            `json:"ModTime"`
	IsDir   bool              `json:"IsDir"`
	Hashes  map[string]string `json:"Hashes"`
}
type Pin struct {
	Mount          string `json:"mount"`
	Path           string `json:"path"`
	RemoteIdentity string `json:"remote_identity_sha256"`
	Size           int64  `json:"size"`
	ModTime        string `json:"remote_mod_time"`
	SourceHash     string `json:"source_hash,omitempty"`
	Verification   string `json:"verification"`
	SHA256         string `json:"sha256"`
	VerifiedUnix   int64  `json:"verified_unix"`
}
type Manifest struct {
	Schema     int   `json:"schema"`
	QuotaBytes int64 `json:"quota_bytes"`
	Pins       []Pin `json:"pins"`
}
type envelope struct {
	Manifest Manifest `json:"manifest"`
	SHA256   string   `json:"sha256"`
}
type Status struct {
	State  string `json:"state"`
	Pin    *Pin   `json:"pin,omitempty"`
	Detail string `json:"detail,omitempty"`
}
type Runner interface {
	Run(context.Context, ...string) ([]byte, error)
}
type runner struct{}

func (runner) Run(ctx context.Context, argv ...string) ([]byte, error) {
	// Never pass a user-selected binary or shell. Limit metadata, suppress stderr
	// which may contain remote URLs or credential-bearing backend errors.
	cmd := exec.CommandContext(ctx, paths.Engine, append([]string{"--config", paths.RcloneConfig}, argv...)...)
	cmd.Env = []string{"PATH=/system/bin:/system/xbin", "HOME=/data/adb/skybind"}
	cmd.Stderr = io.Discard
	var b bounded
	cmd.Stdout = &b
	if err := cmd.Run(); err != nil {
		return nil, errors.New("remote transfer/metadata request failed")
	}
	return b.Bytes(), nil
}

type bounded struct{ bytes.Buffer }

func (b *bounded) Write(p []byte) (int, error) {
	if b.Len()+len(p) > 8<<20 {
		return 0, errors.New("metadata response exceeds bound")
	}
	return b.Buffer.Write(p)
}

type Store struct {
	dir string
	r   Runner
	cfg func() (config.Registry, error)
	now func() time.Time
}

func Canonical() *Store {
	return &Store{dir: paths.StateRoot + "/offline", r: runner{}, cfg: func() (config.Registry, error) {
		s, e := config.Open(paths.StateRoot + "/config")
		if e != nil {
			return config.Registry{}, e
		}
		return s.Snapshot()
	}, now: time.Now}
}
func New(dir string, r Runner, cfg func() (config.Registry, error)) *Store {
	return &Store{dir: dir, r: r, cfg: cfg, now: time.Now}
}
func validatePath(s string) error {
	if s == "" || len(s) > 512 || strings.HasPrefix(s, "/") || strings.ContainsAny(s, "\\\x00\r\n\t:") {
		return errors.New("invalid offline relative path")
	}
	for _, v := range strings.Split(s, "/") {
		if v == "" || v == "." || v == ".." || len(v) > 255 {
			return errors.New("invalid offline path segment")
		}
	}
	return nil
}
func (s *Store) prepare() error {
	for _, dir := range []string{s.dir, s.dir + "/objects"} {
		if e := os.Mkdir(dir, 0700); e != nil && !os.IsExist(e) {
			return e
		}
		info, e := os.Lstat(dir)
		if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 || info.Mode().Perm() != 0700 {
			return errors.New("unsafe offline directory")
		}
		fd, e := paths.OpenVerifiedDirectory(dir)
		if e != nil {
			return e
		}
		_ = syscall.Close(fd)
	}
	return nil
}

// lock prevents two root commands from racing the manifest/quota; normal daemon
// operations never access this isolated subtree. Caller must finish with unlock.
func (s *Store) lock() (func(), error) {
	if err := s.prepare(); err != nil {
		return nil, err
	}
	if fd, err := paths.OpenVerifiedDirectory(s.dir); err != nil {
		return nil, err
	} else {
		_ = syscall.Close(fd)
	} // verified ancestry
	f, e := os.OpenFile(s.dir+"/.lock", os.O_CREATE|os.O_RDWR|syscall.O_NOFOLLOW, 0600)
	if e != nil {
		return nil, e
	}
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 {
		f.Close()
		return nil, errors.New("unsafe offline lock")
	}
	if e = syscall.Flock(int(f.Fd()), syscall.LOCK_EX); e != nil {
		f.Close()
		return nil, e
	}
	return func() { _ = syscall.Flock(int(f.Fd()), syscall.LOCK_UN); _ = f.Close() }, nil
}
func cleanManifest(m Manifest) error {
	if m.Schema != 1 || m.QuotaBytes < 1<<20 || m.QuotaBytes > maxQuota || len(m.Pins) > 4096 {
		return errors.New("invalid offline manifest")
	}
	seen := map[string]bool{}
	for _, p := range m.Pins {
		if !safeName.MatchString(p.Mount) || validatePath(p.Path) != nil || p.Size < 0 || p.Size > maxOnePin || len(p.SHA256) != 64 || len(p.RemoteIdentity) != 64 || p.Verification == "" {
			return errors.New("invalid offline entry")
		}
		if _, e := hex.DecodeString(p.SHA256); e != nil {
			return e
		}
		if _, e := hex.DecodeString(p.RemoteIdentity); e != nil {
			return e
		}
		k := p.Mount + "/" + p.Path
		if seen[k] {
			return errors.New("duplicate offline entry")
		}
		seen[k] = true
	}
	return nil
}
func (s *Store) load() (Manifest, error) {
	b, e := atomicfile.Read(s.dir, "pins-v1.json", 1<<20)
	if errors.Is(e, os.ErrNotExist) {
		return Manifest{Schema: 1, QuotaBytes: defaultQuota, Pins: []Pin{}}, nil
	}
	if e != nil {
		return Manifest{}, e
	}
	var x envelope
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if e = d.Decode(&x); e != nil {
		return Manifest{}, e
	}
	var extra any
	if d.Decode(&extra) != io.EOF {
		return Manifest{}, errors.New("offline manifest has trailing data")
	}
	if e = cleanManifest(x.Manifest); e != nil {
		return Manifest{}, e
	}
	raw, _ := json.Marshal(x.Manifest)
	h := sha256.Sum256(raw)
	if x.SHA256 != hex.EncodeToString(h[:]) {
		return Manifest{}, errors.New("offline manifest checksum mismatch")
	}
	return x.Manifest, nil
}
func (s *Store) save(m Manifest) error {
	sort.Slice(m.Pins, func(i, j int) bool {
		if m.Pins[i].Mount == m.Pins[j].Mount {
			return m.Pins[i].Path < m.Pins[j].Path
		}
		return m.Pins[i].Mount < m.Pins[j].Mount
	})
	if e := cleanManifest(m); e != nil {
		return e
	}
	b, e := json.Marshal(m)
	if e != nil {
		return e
	}
	h := sha256.Sum256(b)
	payload, e := json.Marshal(envelope{m, hex.EncodeToString(h[:])})
	if e != nil {
		return e
	}
	return atomicfile.Write(s.dir, "pins-v1.json", payload)
}
func (s *Store) mount(name string) (config.Mount, error) {
	if !safeName.MatchString(name) {
		return config.Mount{}, errors.New("invalid mount name")
	}
	reg, e := s.cfg()
	if e != nil {
		return config.Mount{}, e
	}
	for _, m := range reg.Mounts {
		if m.Name == name {
			return m, nil
		}
	}
	return config.Mount{}, errors.New("mount not configured")
}
func identity(m config.Mount) string {
	h := sha256.Sum256([]byte(m.Remote))
	return hex.EncodeToString(h[:])
}
func endpoint(m config.Mount, rel string) string {
	return strings.TrimSuffix(m.Remote, "/") + "/" + rel
}
func (s *Store) stat(ctx context.Context, m config.Mount, rel string) (RemoteFile, error) {
	b, e := s.r.Run(ctx, "lsjson", "--stat", "--hash", endpoint(m, rel))
	if e != nil {
		return RemoteFile{}, e
	}
	var f RemoteFile
	if e = json.Unmarshal(b, &f); e != nil {
		return f, errors.New("invalid remote metadata")
	}
	if f.IsDir || f.Size < 0 || f.Size > maxOnePin {
		return f, errors.New("not a supported remote file")
	}
	return f, nil
}
func (s *Store) tree(ctx context.Context, m config.Mount, rel string) ([]RemoteFile, error) {
	b, e := s.r.Run(ctx, "lsjson", "--recursive", "--files-only", "--hash", endpoint(m, rel))
	if e != nil {
		return nil, e
	}
	var fs []RemoteFile
	if e = json.Unmarshal(b, &fs); e != nil {
		return nil, errors.New("invalid remote listing")
	}
	if len(fs) > maxFiles {
		return nil, errors.New("offline directory exceeds file-count bound")
	}
	var size int64
	for _, f := range fs {
		if validatePath(f.Path) != nil || f.IsDir || f.Size < 0 || f.Size > maxOnePin {
			return nil, errors.New("unsafe remote listing")
		}
		size += f.Size
		if size > maxOnePin {
			return nil, errors.New("offline directory exceeds size bound")
		}
	}
	return fs, nil
}
func hashFile(path string) (string, int64, error) {
	f, e := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return "", 0, e
	}
	defer f.Close()
	st, e := f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Sys().(*syscall.Stat_t).Nlink != 1 {
		return "", 0, errors.New("unsafe offline file")
	}
	h := sha256.New()
	n, e := io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), n, e
}

// Count all content-addressed objects including crash-preserved orphans.
// Unpinned objects still consume space until an explicit gc command.
func (s *Store) physicalBytes() (int64, error) {
	entries, e := os.ReadDir(s.dir + "/objects")
	if e != nil {
		return 0, e
	}
	var total int64
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, ".download-") {
			return 0, errors.New("incomplete offline download needs recovery")
		}
		if len(name) != 64 || !isHex(name) {
			return 0, errors.New("unknown offline store entry")
		}
		st, e := os.Lstat(s.dir + "/objects/" + name)
		if e != nil || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Sys().(*syscall.Stat_t).Nlink != 1 {
			return 0, errors.New("unsafe offline content entry")
		}
		total += st.Size()
	}
	return total, nil
}
func verifyHash(path string, f RemoteFile) (string, error) {
	if f.Hashes == nil {
		return "metadata+sha256", nil
	}
	for _, pair := range []struct {
		name     string
		makeHash func() (io.Writer, func() string)
	}{
		{"MD5", func() (io.Writer, func() string) {
			h := md5.New()
			return h, func() string { return hex.EncodeToString(h.Sum(nil)) }
		}},
		{"SHA-1", func() (io.Writer, func() string) {
			h := sha1.New()
			return h, func() string { return hex.EncodeToString(h.Sum(nil)) }
		}},
		{"SHA-256", func() (io.Writer, func() string) {
			h := sha256.New()
			return h, func() string { return hex.EncodeToString(h.Sum(nil)) }
		}},
	} {
		var remote string
		for key, v := range f.Hashes {
			if strings.EqualFold(key, pair.name) {
				remote = v
				break
			}
		}
		if remote == "" {
			continue
		}
		file, e := os.OpenFile(path, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
		if e != nil {
			return "", e
		}
		sink, sum := pair.makeHash()
		_, e = io.Copy(sink, file)
		_ = file.Close()
		if e != nil {
			return "", e
		}
		if !strings.EqualFold(sum(), remote) {
			return "", errors.New("source checksum mismatch")
		}
		return "remote-hash+sha256", nil
	}
	return "metadata+sha256", nil
}
func (s *Store) pinOne(ctx context.Context, m config.Mount, rel string, f RemoteFile, current *Manifest) error {
	if e := validatePath(rel); e != nil {
		return e
	}
	if f.Size > maxOnePin {
		return errors.New("file too large")
	}
	used, err := s.physicalBytes()
	if err != nil {
		return err
	}
	if used+f.Size > current.QuotaBytes {
		return errors.New("offline quota exceeded")
	}
	var disk syscall.Statfs_t
	if e := syscall.Statfs(s.dir, &disk); e != nil {
		return e
	}
	if uint64(f.Size+minFree) > disk.Bavail*uint64(disk.Bsize) {
		return errors.New("insufficient free space for offline pin")
	}
	temp, e := os.CreateTemp(s.dir+"/objects", ".download-")
	if e != nil {
		return e
	}
	tempPath := temp.Name()
	_ = temp.Close()
	defer os.Remove(tempPath)
	// copyto writes an explicit complete file; this is not a sparse VFS read.
	if _, e = s.r.Run(ctx, "copyto", "--retries", "1", endpoint(m, rel), tempPath); e != nil {
		return e
	}
	if e = os.Chmod(tempPath, 0600); e != nil {
		return e
	}
	h, n, e := hashFile(tempPath)
	if e != nil {
		return e
	}
	if n != f.Size {
		return errors.New("downloaded size differs from remote metadata")
	}
	verification, e := verifyHash(tempPath, f)
	if e != nil {
		return e
	}
	fresh, e := s.stat(ctx, m, rel)
	if e != nil {
		return errors.New("cannot recheck remote revision")
	}
	if fresh.Size != f.Size || fresh.ModTime != f.ModTime || !sameHashes(f.Hashes, fresh.Hashes) {
		return errors.New("remote revision changed during pin")
	}
	dst := s.dir + "/objects/" + h
	if _, e = os.Lstat(dst); errors.Is(e, os.ErrNotExist) {
		fd, e := os.OpenFile(tempPath, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
		if e != nil {
			return e
		}
		e = fd.Sync()
		_ = fd.Close()
		if e != nil {
			return e
		}
		if e = os.Rename(tempPath, dst); e != nil {
			return e
		}
		dirFD, de := os.Open(s.dir + "/objects")
		if de == nil {
			de = dirFD.Sync()
			_ = dirFD.Close()
		}
		if de != nil {
			return de
		}
	} else if e != nil {
		return e
	}
	diskHash, size, e := hashFile(dst)
	if e != nil || diskHash != h || size != n {
		return errors.New("stored offline object integrity mismatch")
	}
	np := Pin{Mount: m.Name, Path: rel, RemoteIdentity: identity(m), Size: n, ModTime: f.ModTime, SHA256: h, Verification: verification, VerifiedUnix: s.now().Unix()}
	for k, v := range f.Hashes {
		if strings.EqualFold(k, "SHA-256") && v != "" {
			np.SourceHash = "SHA-256:" + v
			break
		}
		if strings.EqualFold(k, "MD5") && v != "" {
			np.SourceHash = "MD5:" + v
		}
	}

	for i, p := range current.Pins {
		if p.Mount == m.Name && p.Path == rel {
			current.Pins[i] = np
			return s.save(*current)
		}
	}
	current.Pins = append(current.Pins, np)
	return s.save(*current)
}
func sourceHashMatches(stored string, current map[string]string) bool {
	pair := strings.SplitN(stored, ":", 2)
	if len(pair) != 2 {
		return false
	}
	for name, v := range current {
		if strings.EqualFold(name, pair[0]) && strings.EqualFold(v, pair[1]) {
			return true
		}
	}
	return false
}
func sameHashes(a, b map[string]string) bool {
	for k, v := range a {
		if b[k] != v {
			return false
		}
	}
	return true
}

// Pin selects a named configured mount and a strictly relative file or folder.
// Recursive pins have bounded file/byte counts; each file is durable independently.
func (s *Store) Pin(ctx context.Context, mount, rel string, recursive bool) (int, error) {
	release, e := s.lock()
	if e != nil {
		return 0, e
	}
	defer release()
	if e = validatePath(rel); e != nil {
		return 0, e
	}
	m, e := s.mount(mount)
	if e != nil {
		return 0, e
	}
	manifest, e := s.load()
	if e != nil {
		return 0, e
	}
	files := []RemoteFile{}
	names := []string{}
	if recursive {
		files, e = s.tree(ctx, m, rel)
		if e != nil {
			return 0, e
		}
		for _, f := range files {
			names = append(names, rel+"/"+f.Path)
		}
	} else {
		f, err := s.stat(ctx, m, rel)
		if err != nil {
			return 0, err
		}
		files = append(files, f)
		names = append(names, rel)
	}
	count := 0
	for i, f := range files {
		if recursive {
			var fresh RemoteFile
			fresh, e = s.stat(ctx, m, names[i])
			if e != nil {
				return count, e
			}
			if fresh.Size != f.Size {
				return count, errors.New("directory listing changed during pin")
			}
			f = fresh
		}
		if e := s.pinOne(ctx, m, names[i], f, &manifest); e != nil {
			return count, e
		}
		count++
	}
	return count, nil
}
func (s *Store) List() (Manifest, error) {
	release, e := s.lock()
	if e != nil {
		return Manifest{}, e
	}
	defer release()
	return s.load()
}
func (s *Store) Quota(bytes int64) error {
	if bytes < 1<<20 || bytes > maxQuota {
		return errors.New("invalid offline quota")
	}
	release, e := s.lock()
	if e != nil {
		return e
	}
	defer release()
	m, e := s.load()
	if e != nil {
		return e
	}
	used, e := s.physicalBytes()
	if e != nil {
		return e
	}
	if used > bytes {
		return errors.New("new quota smaller than retained offline objects")
	}
	m.QuotaBytes = bytes
	return s.save(m)
}
func (s *Store) Status(ctx context.Context, mount, rel string, checkRemote bool) (Status, error) {
	release, e := s.lock()
	if e != nil {
		return Status{}, e
	}
	defer release()
	m, e := s.load()
	if e != nil {
		return Status{}, e
	}
	if e = validatePath(rel); e != nil {
		return Status{}, e
	}
	for _, p := range m.Pins {
		if p.Mount != mount || p.Path != rel {
			continue
		}
		h, n, e := hashFile(s.dir + "/objects/" + p.SHA256)
		if e != nil || h != p.SHA256 || n != p.Size {
			return Status{State: "CONFLICT", Pin: &p, Detail: "local offline object missing or checksum mismatch"}, nil
		}
		configured, e := s.mount(mount)
		if e != nil || identity(configured) != p.RemoteIdentity {
			return Status{State: "STALE", Pin: &p, Detail: "mount removed or remote identity changed"}, nil
		}
		if checkRemote {
			f, e := s.stat(ctx, configured, rel)
			if e != nil {
				return Status{State: "AVAILABLE_OFFLINE", Pin: &p, Detail: "remote status unknown (local content verified)"}, nil
			}
			if f.Size != p.Size || f.ModTime != p.ModTime || (p.SourceHash != "" && !sourceHashMatches(p.SourceHash, f.Hashes)) {
				return Status{State: "STALE", Pin: &p, Detail: "remote metadata changed"}, nil
			}
		}
		return Status{State: "AVAILABLE_OFFLINE", Pin: &p}, nil
	}
	return Status{State: "UNAVAILABLE"}, nil
}

// Export copies a verified immutable snapshot to a fixed Android Downloads tree.
// This is intentionally an explicit public copy, NOT a writable offline-sync view.
func (s *Store) Export(mount, rel string) (string, error) {
	release, e := s.lock()
	if e != nil {
		return "", e
	}
	defer release()
	if !safeName.MatchString(mount) || validatePath(rel) != nil {
		return "", errors.New("invalid export selection")
	}
	m, e := s.load()
	if e != nil {
		return "", e
	}
	for _, p := range m.Pins {
		if p.Mount != mount || p.Path != rel {
			continue
		}
		h, n, e := hashFile(s.dir + "/objects/" + p.SHA256)
		if e != nil || h != p.SHA256 || n != p.Size {
			return "", errors.New("offline file not verified")
		}
		d := "/storage/emulated/0/Download/Skybind-Offline/" + mount
		for _, seg := range strings.Split(filepath.Dir(rel), "/") {
			if seg == "." {
				continue
			}
			d += "/" + seg
		}
		// Parent is a fixed Android media root; disallow symlink replacements beneath
		// the exported tree and never follow an attacker-controlled export leaf.
		if e = ensureExportParent(d); e != nil {
			return "", e
		}
		dst := d + "/" + filepath.Base(rel)
		if _, e = os.Lstat(dst); e == nil {
			return "", errors.New("export destination already exists; do not overwrite")
		}
		if !errors.Is(e, os.ErrNotExist) {
			return "", e
		}
		src, e := os.OpenFile(s.dir+"/objects/"+p.SHA256, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
		if e != nil {
			return "", e
		}
		defer src.Close()
		out, e := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0644)
		if e != nil {
			return "", e
		}
		copied, e := io.Copy(out, src)
		if e == nil {
			e = out.Sync()
		}
		ce := out.Close()
		if e == nil {
			e = ce
		}
		if e != nil || copied != p.Size {
			_ = os.Remove(dst)
			return "", errors.New("offline export copy failed")
		}
		return dst, nil
	}
	return "", errors.New("file not pinned")
}
func ensureExportParent(dest string) error {
	base := "/storage/emulated/0/Download"
	if dest != base && !strings.HasPrefix(dest, base+"/") {
		return errors.New("bad media destination")
	}
	st, e := os.Lstat(base)
	if e != nil || !st.IsDir() {
		return errors.New("Android Downloads unavailable")
	}
	cur := base
	for _, part := range strings.Split(strings.TrimPrefix(dest, base+"/"), "/") {
		if part == "" {
			continue
		}
		cur += "/" + part
		info, e := os.Lstat(cur)
		if errors.Is(e, os.ErrNotExist) {
			if e = os.Mkdir(cur, 0700); e != nil {
				return e
			}
			info, e = os.Lstat(cur)
		}
		if e != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
			return errors.New("unsafe export directory")
		}
	}
	return nil
}
func (s *Store) Unpin(mount, rel string) error {
	release, e := s.lock()
	if e != nil {
		return e
	}
	defer release()
	if !safeName.MatchString(mount) || validatePath(rel) != nil {
		return errors.New("invalid pin selection")
	}
	m, e := s.load()
	if e != nil {
		return e
	}
	next := m.Pins[:0]
	found := false
	for _, p := range m.Pins {
		if p.Mount == mount && p.Path == rel {
			found = true
			continue
		}
		next = append(next, p)
	}
	if !found {
		return errors.New("file not pinned")
	}
	m.Pins = next
	return s.save(m)
}

// GC is explicit: remove ONLY orphaned SHA-named offline objects, never VFS files.
func (s *Store) GC() (int, error) {
	release, e := s.lock()
	if e != nil {
		return 0, e
	}
	defer release()
	m, e := s.load()
	if e != nil {
		return 0, e
	}
	active := map[string]bool{}
	for _, p := range m.Pins {
		active[p.SHA256] = true
	}
	entries, e := os.ReadDir(s.dir + "/objects")
	if e != nil {
		return 0, e
	}
	deleted := 0
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, ".download-") {
			path := s.dir + "/objects/" + name
			st, e := os.Lstat(path)
			if e != nil || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 {
				return deleted, errors.New("unsafe incomplete download")
			}
			if e = os.Remove(path); e != nil {
				return deleted, e
			}
			deleted++
			continue
		}
		if active[name] || len(name) != 64 || !isHex(name) {
			continue
		}
		f := s.dir + "/objects/" + name
		h, _, e := hashFile(f)
		if e != nil || h != name {
			return deleted, errors.New("orphan integrity unavailable: refuse cleanup")
		}
		if e = os.Remove(f); e != nil {
			return deleted, e
		}
		deleted++
	}
	return deleted, nil
}
func isHex(s string) bool { _, e := hex.DecodeString(s); return e == nil }
func (s *Store) InspectObject(mount, rel string) (string, error) {
	// Returns a private path only to a root CLI caller after checking integrity.
	st, e := s.Status(context.Background(), mount, rel, false)
	if e != nil {
		return "", e
	}
	if st.State != "AVAILABLE_OFFLINE" {
		return "", errors.New("offline object unavailable")
	}
	return filepath.Join(s.dir, "objects", st.Pin.SHA256), nil
}
func (s *Store) String() string { return fmt.Sprintf("Skybind offline private store: %s", s.dir) }
