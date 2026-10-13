package offline

// M6 experimental offline edits. The original FUSE mount and remote objects are
// never modified: local edits are staged privately and any explicit upload goes
// to an independent uniquely named copy requiring manual reconciliation.

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"skybind/internal/atomicfile"
	"skybind/internal/mounts/config"
	"skybind/internal/paths"
	"strings"
	"syscall"
	"time"
)

const maxDraftBytes int64 = 128 << 20
const maxJournalBytes int64 = 1 << 30
const maxDrafts = 64
const draftRoot = "/storage/emulated/0/Download/Skybind-Offline-Drafts"

type Edit struct {
	ID                 string `json:"id"`
	Mount              string `json:"mount"`
	Path               string `json:"path"`
	RemoteIdentity     string `json:"remote_identity_sha256"`
	BaseSize           int64  `json:"base_size"`
	BaseModTime        string `json:"base_mod_time"`
	BaseSourceHash     string `json:"base_source_hash,omitempty"`
	BaseSHA256         string `json:"base_sha256"`
	SHA256             string `json:"sha256"`
	Size               int64  `json:"size"`
	State              string `json:"state"`
	CreatedUnix        int64  `json:"created_unix"`
	UploadedRemoteCopy string `json:"uploaded_remote_copy,omitempty"`
	RemoteVerification string `json:"remote_verification,omitempty"`
}
type EditJournal struct {
	Schema int    `json:"schema"`
	Edits  []Edit `json:"edits"`
}
type editEnvelope struct {
	Journal EditJournal `json:"journal"`
	SHA256  string      `json:"sha256"`
}
type RevisionCheck struct {
	State  string `json:"state"`
	Detail string `json:"detail"`
}

func (s *Store) prepareWrites() error {
	if err := s.prepare(); err != nil {
		return err
	}
	for _, dir := range []string{s.dir + "/writes", s.dir + "/writes/objects"} {
		if err := os.Mkdir(dir, 0700); err != nil && !errors.Is(err, os.ErrExist) {
			return err
		}
		st, err := os.Lstat(dir)
		if err != nil || !st.IsDir() || st.Mode().Perm() != 0700 || st.Mode()&os.ModeSymlink != 0 {
			return errors.New("unsafe private write directory")
		}
		fd, err := paths.OpenVerifiedDirectory(dir)
		if err != nil {
			return err
		}
		syscall.Close(fd)
	}
	return nil
}
func checkEdit(e Edit) error {
	if len(e.ID) != 32 || !isHex(e.ID) || !safeName.MatchString(e.Mount) || validatePath(e.Path) != nil || len(e.RemoteIdentity) != 64 || !isHex(e.RemoteIdentity) || len(e.BaseSHA256) != 64 || !isHex(e.BaseSHA256) || len(e.SHA256) != 64 || !isHex(e.SHA256) || e.BaseSize < 0 || e.Size < 0 || e.Size > maxDraftBytes || e.CreatedUnix <= 0 {
		return errors.New("invalid write journal item")
	}
	if e.State != "QUEUED" && e.State != "UPLOAD_INDETERMINATE" && e.State != "UPLOADED_COPY" {
		return errors.New("invalid write state")
	}
	if len(e.BaseModTime) > 128 || len(e.BaseSourceHash) > 128 || len(e.UploadedRemoteCopy) > 1024 || len(e.RemoteVerification) > 64 {
		return errors.New("invalid write metadata")
	}
	return nil
}
func (s *Store) readEdits() (EditJournal, error) {
	data, err := atomicfile.Read(s.dir+"/writes", "edits-v1.json", 1<<20)
	if errors.Is(err, os.ErrNotExist) {
		return EditJournal{Schema: 1, Edits: []Edit{}}, nil
	}
	if err != nil {
		return EditJournal{}, err
	}
	var env editEnvelope
	dec := json.NewDecoder(bytes.NewReader(data))
	dec.DisallowUnknownFields()
	if err = dec.Decode(&env); err != nil {
		return EditJournal{}, err
	}
	var other any
	if dec.Decode(&other) != io.EOF {
		return EditJournal{}, errors.New("write journal trailing data")
	}
	if env.Journal.Schema != 1 || len(env.Journal.Edits) > maxDrafts {
		return EditJournal{}, errors.New("invalid write journal")
	}
	seen := map[string]bool{}
	for _, e := range env.Journal.Edits {
		if err = checkEdit(e); err != nil {
			return EditJournal{}, err
		}
		if seen[e.ID] {
			return EditJournal{}, errors.New("duplicate write id")
		}
		seen[e.ID] = true
	}
	canonical, _ := json.Marshal(env.Journal)
	sum := sha256.Sum256(canonical)
	if env.SHA256 != hex.EncodeToString(sum[:]) {
		return EditJournal{}, errors.New("write journal checksum mismatch")
	}
	return env.Journal, nil
}
func (s *Store) saveEdits(j EditJournal) error {
	if j.Schema != 1 || len(j.Edits) > maxDrafts {
		return errors.New("too many queued edits")
	}
	for _, e := range j.Edits {
		if err := checkEdit(e); err != nil {
			return err
		}
	}
	b, err := json.Marshal(j)
	if err != nil {
		return err
	}
	sum := sha256.Sum256(b)
	result, err := json.Marshal(editEnvelope{Journal: j, SHA256: hex.EncodeToString(sum[:])})
	if err != nil {
		return err
	}
	return atomicfile.Write(s.dir+"/writes", "edits-v1.json", result)
}
func (s *Store) editLock() (func(), error) {
	release, err := s.lock()
	if err != nil {
		return nil, err
	}
	if err = s.prepareWrites(); err != nil {
		release()
		return nil, err
	}
	return release, nil
}
func (s *Store) pinForEdit(mount, rel string) (Pin, config.Mount, error) {
	if !safeName.MatchString(mount) || validatePath(rel) != nil {
		return Pin{}, config.Mount{}, errors.New("invalid edit selection")
	}
	m, err := s.mount(mount)
	if err != nil {
		return Pin{}, m, err
	}
	manifest, err := s.load()
	if err != nil {
		return Pin{}, m, err
	}
	for _, p := range manifest.Pins {
		if p.Mount != mount || p.Path != rel {
			continue
		}
		if identity(m) != p.RemoteIdentity {
			return Pin{}, m, errors.New("pin remote identity changed")
		}
		h, n, err := hashFile(s.dir + "/objects/" + p.SHA256)
		if err != nil || n != p.Size || h != p.SHA256 {
			return Pin{}, m, errors.New("pinned base integrity failed")
		}
		return p, m, nil
	}
	return Pin{}, m, errors.New("pin file first; offline edits require verified base")
}
func (s *Store) noFollowPublic(mount, rel string, createDirs bool) (*os.File, error) {
	if !safeName.MatchString(mount) || validatePath(rel) != nil {
		return nil, errors.New("invalid public draft path")
	}
	base := "/storage/emulated/0/Download"
	if s.draftBase != "" {
		base = s.draftBase
	}
	st, err := os.Lstat(base)
	if err != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return nil, errors.New("Android Downloads unavailable")
	}
	fd, err := syscall.Open(base, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	parts := append([]string{"Skybind-Offline-Drafts", mount}, strings.Split(rel, "/")...)
	for _, part := range parts[:len(parts)-1] {
		if createDirs {
			e := syscall.Mkdirat(fd, part, 0777)
			if e != nil && !errors.Is(e, syscall.EEXIST) {
				syscall.Close(fd)
				return nil, e
			}
		}
		next, e := syscall.Openat(fd, part, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
		syscall.Close(fd)
		if e != nil {
			return nil, e
		}
		fd = next
	}
	flags := syscall.O_RDONLY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC
	if createDirs {
		flags = syscall.O_WRONLY | syscall.O_CREAT | syscall.O_EXCL | syscall.O_NOFOLLOW | syscall.O_CLOEXEC
	}
	n, e := syscall.Openat(fd, parts[len(parts)-1], flags, 0666)
	syscall.Close(fd)
	if e != nil {
		return nil, e
	}
	f := os.NewFile(uintptr(n), "offline draft")
	if createDirs {
		_ = f.Chmod(0666)
	} // Public draft: Android editor needs write access when filesystem honors modes
	st, e = f.Stat()
	if e != nil || !st.Mode().IsRegular() || st.Size() > maxDraftBytes || st.Sys().(*syscall.Stat_t).Nlink != 1 {
		f.Close()
		return nil, errors.New("unsafe public draft file")
	}
	return f, nil
}
func randomID() (string, error) {
	var id [16]byte
	_, err := rand.Read(id[:])
	return hex.EncodeToString(id[:]), err
}
func (s *Store) Draft(mount, rel string) (string, error) {
	return s.DraftContext(context.Background(), mount, rel)
}
func (s *Store) DraftContext(ctx context.Context, mount, rel string) (string, error) {
	release, err := s.editLock()
	if err != nil {
		return "", err
	}
	defer release()
	p, _, err := s.pinForEdit(mount, rel)
	if err != nil {
		return "", err
	}
	if p.Size > maxDraftBytes {
		return "", errors.New("base exceeds experimental edit bound")
	}
	out, err := s.noFollowPublic(mount, rel, true)
	if err != nil {
		return "", err
	}
	dst := draftRoot + "/" + mount + "/" + rel
	if s.draftBase != "" {
		dst = s.draftBase + "/Skybind-Offline-Drafts/" + mount + "/" + rel
	}
	success := false
	defer func() {
		if !success {
			_ = os.Remove(dst)
		}
	}()
	in, err := os.OpenFile(s.dir+"/objects/"+p.SHA256, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		out.Close()
		return "", err
	}
	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(out, h), io.LimitReader(cancelableReader{ctx: ctx, r: in}, maxDraftBytes+1))
	in.Close()
	if err == nil {
		err = out.Sync()
	}
	closeErr := out.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil || ctx.Err() != nil || n != p.Size || hex.EncodeToString(h.Sum(nil)) != p.SHA256 {
		return "", errors.New("draft copy integrity mismatch")
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	success = true
	return dst, nil
}
func (s *Store) Stage(mount, rel string) (Edit, error) {
	return s.StageContext(context.Background(), mount, rel)
}
func (s *Store) StageContext(ctx context.Context, mount, rel string) (Edit, error) {
	release, err := s.editLock()
	if err != nil {
		return Edit{}, err
	}
	defer release()
	p, _, err := s.pinForEdit(mount, rel)
	if err != nil {
		return Edit{}, err
	}
	journal, err := s.readEdits()
	if err != nil {
		return Edit{}, err
	}
	if len(journal.Edits) >= maxDrafts {
		return Edit{}, errors.New("write journal full; manual reconciliation required")
	}
	var used int64
	for _, it := range journal.Edits {
		used += it.Size
		if it.Mount == mount && it.Path == rel && it.State != "UPLOADED_COPY" {
			return Edit{}, errors.New("unresolved edit already queued for path")
		}
	}
	src, err := s.noFollowPublic(mount, rel, false)
	if err != nil {
		return Edit{}, err
	}
	defer src.Close()
	info, err := src.Stat()
	if err != nil {
		return Edit{}, err
	}
	if info.Size() > maxDraftBytes || used+info.Size() > maxJournalBytes {
		return Edit{}, errors.New("write journal storage limit reached")
	}
	var disk syscall.Statfs_t
	if err = syscall.Statfs(s.dir, &disk); err != nil {
		return Edit{}, err
	}
	if uint64(info.Size()+minFree) > disk.Bavail*uint64(disk.Bsize) {
		return Edit{}, errors.New("insufficient local space for edit")
	}
	id, err := randomID()
	if err != nil {
		return Edit{}, err
	}
	temp, err := os.CreateTemp(s.dir+"/writes/objects", ".write-")
	if err != nil {
		return Edit{}, err
	}
	tempPath := temp.Name()
	defer os.Remove(tempPath)
	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(temp, h), io.LimitReader(cancelableReader{ctx: ctx, r: src}, maxDraftBytes+1))
	if err == nil {
		err = temp.Sync()
	}
	closeErr := temp.Close()
	if err == nil {
		err = closeErr
	}
	if err != nil || ctx.Err() != nil || n != info.Size() {
		return Edit{}, errors.New("draft changed or failed during stage")
	}
	sum := hex.EncodeToString(h.Sum(nil))
	if sum == p.SHA256 {
		return Edit{}, errors.New("draft has no edits")
	}
	final := s.dir + "/writes/objects/" + sum
	if _, err = os.Lstat(final); errors.Is(err, os.ErrNotExist) {
		if err = os.Rename(tempPath, final); err != nil {
			return Edit{}, err
		}
		fd, e := os.Open(s.dir + "/writes/objects")
		if e != nil {
			return Edit{}, e
		}
		err = fd.Sync()
		fd.Close()
		if err != nil {
			return Edit{}, err
		}
	} else if err != nil {
		return Edit{}, err
	}
	check, size, err := hashFile(final)
	if err != nil || check != sum || size != n {
		return Edit{}, errors.New("queued object integrity failure")
	}
	entry := Edit{ID: id, Mount: mount, Path: rel, RemoteIdentity: p.RemoteIdentity, BaseSize: p.Size, BaseModTime: p.ModTime, BaseSourceHash: p.SourceHash, BaseSHA256: p.SHA256, SHA256: sum, Size: n, State: "QUEUED", CreatedUnix: s.now().Unix()}
	if entry.CreatedUnix <= 0 {
		entry.CreatedUnix = time.Now().Unix()
	}
	if err := ctx.Err(); err != nil {
		return Edit{}, err
	}
	journal.Edits = append(journal.Edits, entry)
	if err = s.saveEdits(journal); err != nil {
		return Edit{}, err
	}
	return entry, nil
}
func (s *Store) Edits() (EditJournal, error) {
	release, err := s.editLock()
	if err != nil {
		return EditJournal{}, err
	}
	defer release()
	return s.readEdits()
}
func getEdit(j EditJournal, id string) (int, error) {
	if len(id) != 32 || !isHex(id) {
		return -1, errors.New("invalid edit ID")
	}
	for i, it := range j.Edits {
		if it.ID == id {
			return i, nil
		}
	}
	return -1, errors.New("edit not found")
}
func (s *Store) verifyQueued(e Edit) (config.Mount, error) {
	m, err := s.mount(e.Mount)
	if err != nil {
		return m, err
	}
	if identity(m) != e.RemoteIdentity {
		return m, errors.New("remote identity changed")
	}
	h, n, err := hashFile(s.dir + "/writes/objects/" + e.SHA256)
	if err != nil || h != e.SHA256 || n != e.Size {
		return m, errors.New("queued edit corrupted or missing")
	}
	return m, nil
}
func (s *Store) compare(ctx context.Context, m config.Mount, e Edit) RevisionCheck {
	meta, err := s.stat(ctx, m, e.Path)
	if err != nil {
		return RevisionCheck{"UNKNOWN", "Remote not reachable or metadata unavailable; no safe overwrite decision"}
	}
	if meta.Size != e.BaseSize || meta.ModTime != e.BaseModTime {
		return RevisionCheck{"CONFLICT", "Remote size or modification time differs from pinned base"}
	}
	if e.BaseSourceHash == "" {
		return RevisionCheck{"UNKNOWN", "Pinned base lacked provider checksum; metadata match is not authoritative"}
	}
	if !sourceHashMatches(e.BaseSourceHash, meta.Hashes) {
		return RevisionCheck{"CONFLICT", "Remote checksum differs or provider no longer supplies the pinned checksum"}
	}
	return RevisionCheck{"MATCH", "Remote still matches the recorded pinned base at the moment of inspection; not an atomic write lock"}
}
func (s *Store) CheckEdit(ctx context.Context, id string) (RevisionCheck, error) {
	release, err := s.editLock()
	if err != nil {
		return RevisionCheck{}, err
	}
	defer release()
	j, err := s.readEdits()
	if err != nil {
		return RevisionCheck{}, err
	}
	idx, err := getEdit(j, id)
	if err != nil {
		return RevisionCheck{}, err
	}
	m, err := s.verifyQueued(j.Edits[idx])
	if err != nil {
		return RevisionCheck{State: "CONFLICT", Detail: "Queue or remote binding is invalid"}, nil
	}
	return s.compare(ctx, m, j.Edits[idx]), nil
}
func (s *Store) UploadSeparateCopy(ctx context.Context, id, ack string) (Edit, error) {
	if ack != "--acknowledge-separate-copy" {
		return Edit{}, errors.New("explicit separate-copy acknowledgment required")
	}
	release, err := s.editLock()
	if err != nil {
		return Edit{}, err
	}
	defer release()
	j, err := s.readEdits()
	if err != nil {
		return Edit{}, err
	}
	idx, err := getEdit(j, id)
	if err != nil {
		return Edit{}, err
	}
	e := j.Edits[idx]
	if e.State != "QUEUED" {
		return Edit{}, errors.New("write not queued; indeterminate or already uploaded state requires manual review")
	}
	m, err := s.verifyQueued(e)
	if err != nil {
		return Edit{}, err
	}
	if m.ReadOnly || m.VFSProfile == "read-only" {
		return Edit{}, errors.New("read-only mount forbids remote copy upload")
	}
	// No write to the original path. Even when the original changes, the edit
	// can only be uploaded as a separate named sibling for manual merging.
	destRel := "Skybind-Offline-Edits/" + e.ID + "/" + filepath.Base(e.Path)
	dest := endpoint(m, destRel)
	// Durable intent BEFORE remote side effect: a crash cannot silently retry.
	e.State = "UPLOAD_INDETERMINATE"
	e.UploadedRemoteCopy = destRel
	j.Edits[idx] = e
	if err = s.saveEdits(j); err != nil {
		return Edit{}, err
	}
	local := s.dir + "/writes/objects/" + e.SHA256
	_, err = s.r.Run(ctx, "copyto", "--immutable", "--retries", "1", local, dest)
	if err != nil {
		return e, errors.New("remote copy failed or uncertain; preserve queued bytes, inspect destination manually before any recovery")
	}
	uploaded, err := s.stat(ctx, m, destRel)
	if err != nil {
		return e, errors.New("upload returned success but independent remote verification unavailable; review destination manually")
	}
	if uploaded.Size != e.Size {
		return e, errors.New("uploaded copy size mismatch; manual review required")
	}
	proof := "size-only-unverified"
	// Local checksum comparison when remote exposes a supported hash.
	if len(uploaded.Hashes) > 0 {
		hashMatched, available := matchFileRemoteHashes(local, uploaded.Hashes)
		if available && !hashMatched {
			return e, errors.New("uploaded copy remote hash mismatch; manual review required")
		}
		if available && hashMatched {
			proof = "remote-hash-verified"
		}
	}
	e.State = "UPLOADED_COPY"
	e.RemoteVerification = proof
	j.Edits[idx] = e
	if err = s.saveEdits(j); err != nil {
		return e, err
	}
	return e, nil
}
func matchFileRemoteHashes(local string, hashes map[string]string) (bool, bool) {
	for _, p := range []struct {
		name string
		make func() (io.Writer, func() string)
	}{
		// Conservative: currently only SHA-256 is accepted as upload proof;
		// many providers return only MD5, in which case status remains size-only.
		{"SHA-256", func() (io.Writer, func() string) {
			h := sha256.New()
			return h, func() string { return hex.EncodeToString(h.Sum(nil)) }
		}},
	} {
		for key, remote := range hashes {
			if strings.EqualFold(key, p.name) && remote != "" {
				f, err := os.OpenFile(local, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
				if err != nil {
					return false, true
				}
				defer f.Close()
				w, sum := p.make()
				if _, err = io.Copy(w, f); err != nil {
					return false, true
				}
				return strings.EqualFold(remote, sum()), true
			}
		}
	}
	return false, false
}
func (s *Store) WriteSummary() string {
	return fmt.Sprintf("Offline experimental edits are stored privately under %s/writes; original remote files are never overwritten", s.dir)
}
