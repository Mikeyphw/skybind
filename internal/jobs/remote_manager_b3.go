package jobs

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"skybind/internal/previewproof"
	"strings"
	"time"
)

// ExchangeRoot is the only directory from which the privileged B3 API may
// upload, or into which it may download. The daemon never accepts raw local
// absolute paths through this API.
const ExchangeRoot = "/storage/emulated/0/Download/Skybind-Transfers"

type RemoteMedia struct {
	Direction string `json:"direction"`
	Remote    string `json:"remote"`
	Local     string `json:"local"`
}
type RemoteFileMove struct {
	Source      string `json:"source"`
	Destination string `json:"destination"`
}

func MediaPath(relative string) (string, error) { return mediaPathUnder(ExchangeRoot, relative) }

// mediaPathUnder has an unexported root argument to exercise boundary and
// symlink attacks in host tests; all API call sites use ExchangeRoot.
func mediaPathUnder(root, relative string) (string, error) {
	if relative == "" || len(relative) > 384 || strings.ContainsAny(relative, "\\:\x00\r\n\t") || strings.HasPrefix(relative, "/") {
		return "", errors.New("invalid exchange subfolder")
	}
	for _, segment := range strings.Split(relative, "/") {
		if segment == "" || segment == "." || segment == ".." {
			return "", errors.New("invalid exchange subfolder")
		}
	}
	path := filepath.Join(root, filepath.FromSlash(relative))
	if !strings.HasPrefix(path, root+"/") {
		return "", errors.New("unsafe exchange path")
	}
	if root == ExchangeRoot && (!validLocalEndpoint(path) || validateLocalExisting(path) != nil) {
		return "", errors.New("unsafe Android media path")
	}
	info, err := os.Lstat(root)
	if err != nil || !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("exchange folder must exist")
	}
	at := root
	for _, segment := range strings.Split(relative, "/") {
		at = filepath.Join(at, segment)
		info, err = os.Lstat(at)
		if errors.Is(err, os.ErrNotExist) {
			break
		}
		if err != nil || info.Mode()&os.ModeSymlink != 0 {
			return "", errors.New("exchange path inaccessible or symlinked")
		}
	}
	return path, nil
}

func validMedia(v RemoteMedia) (string, error) {
	if v.Direction != "upload" && v.Direction != "download" {
		return "", errors.New("invalid transfer direction")
	}
	if !validEndpoint(v.Remote) || strings.HasPrefix(v.Remote, "/") || strings.HasSuffix(v.Remote, ":") {
		return "", errors.New("invalid remote folder")
	}
	path, err := MediaPath(v.Local)
	if err != nil {
		return "", err
	}
	if v.Direction == "upload" {
		info, e := os.Stat(path)
		if e != nil || !info.IsDir() {
			return "", errors.New("upload source folder is unavailable")
		}
	}
	return path, nil
}
func bindingB3(action string, v any, fingerprint string) previewproof.Binding {
	b, _ := json.Marshal(v)
	return previewproof.Binding{Action: action, Subject: "b3_mountless", Digest: previewproof.Digest(append(b, fingerprint...))}
}
func (s *Store) RemoteMediaPreview(v RemoteMedia, fingerprint string) (any, error) {
	if _, err := validMedia(v); err != nil {
		return nil, err
	}
	if len(fingerprint) != 64 {
		return nil, errors.New("missing configuration fingerprint")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	proof, err := s.proofs.Issue(bindingB3("remote.media.start", v, fingerprint), 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"proof": proof, "direction": v.Direction, "remote": v.Remote, "local": v.Local, "expires_seconds": 120, "skip_existing": true, "exchange_root": "Downloads/Skybind-Transfers"}, nil
}
func (s *Store) RemoteMediaStart(v RemoteMedia, fingerprint, proof string) (Run, error) {
	path, err := validMedia(v)
	if err != nil {
		return Run{}, err
	}
	if len(fingerprint) != 64 {
		return Run{}, errors.New("missing configuration fingerprint")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.proofs.Consume(proof, bindingB3("remote.media.start", v, fingerprint)); err != nil {
		return Run{}, err
	}
	if err := s.canRun(Job{NetworkMode: "any"}); err != nil {
		return Run{}, err
	}
	name := make([]byte, 8)
	if _, err := rand.Read(name); err != nil {
		return Run{}, err
	}
	job := Job{Name: "Media" + hex.EncodeToString(name), Kind: "copy", IgnoreExisting: true, NetworkMode: "any", Enabled: true}
	if v.Direction == "upload" {
		job.Source = path
		job.Destination = v.Remote
	} else {
		job.Source = v.Remote
		job.Destination = path
	}
	return s.claim(job)
}
func validFileMove(v RemoteFileMove) error {
	if !validEndpoint(v.Source) || !validEndpoint(v.Destination) || strings.HasPrefix(v.Source, "/") || strings.HasPrefix(v.Destination, "/") || v.Source == v.Destination {
		return errors.New("invalid move endpoints")
	}
	src := strings.SplitN(v.Source, ":", 2)
	dst := strings.SplitN(v.Destination, ":", 2)
	if src[0] != dst[0] || src[1] == "" || dst[1] == "" || strings.HasSuffix(src[1], "/") || strings.HasSuffix(dst[1], "/") {
		return errors.New("file move requires two paths on one configured remote")
	}
	return nil
}
func (s *Store) RemoteFileMovePreview(v RemoteFileMove, fingerprint string) (any, error) {
	if err := validFileMove(v); err != nil {
		return nil, err
	}
	if len(fingerprint) != 64 {
		return nil, errors.New("missing configuration fingerprint")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	proof, err := s.proofs.Issue(bindingB3("remote.file.move.start", v, fingerprint), 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"proof": proof, "source": v.Source, "destination": v.Destination, "expires_seconds": 120, "file_only": true, "skip_existing": true, "source_deleted_after_success": true}, nil
}
func (s *Store) RemoteFileMoveStart(v RemoteFileMove, fingerprint, proof string) (Run, error) {
	if err := validFileMove(v); err != nil {
		return Run{}, err
	}
	if len(fingerprint) != 64 {
		return Run{}, errors.New("missing configuration fingerprint")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if err := s.proofs.Consume(proof, bindingB3("remote.file.move.start", v, fingerprint)); err != nil {
		return Run{}, err
	}
	if err := s.canRun(Job{NetworkMode: "any"}); err != nil {
		return Run{}, err
	}
	name := make([]byte, 8)
	if _, err := rand.Read(name); err != nil {
		return Run{}, err
	}
	return s.claim(Job{Name: "Move" + hex.EncodeToString(name), Kind: "moveto", Source: v.Source, Destination: v.Destination, IgnoreExisting: true, Enabled: true, NetworkMode: "any"})
}

func execMoveGuard(j Job) error {
	if j.Kind != "moveto" || !j.IgnoreExisting || validFileMove(RemoteFileMove{Source: j.Source, Destination: j.Destination}) != nil {
		return errors.New("unsafe move execution")
	}
	return nil
}
