package support

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"syscall"
)

// androidDownloads is a canonical public user-accessible destination, not a
// caller-supplied path. Private diagnostics remain private unless exported.
const androidDownloads = "/storage/emulated/0/Download"

var digestRx = regexp.MustCompile(`^[0-9a-f]{64}$`)

// ExportToDownloads exports only a previously verified Skybind-owned support
// archive to Android Downloads. There is no generic filesystem write endpoint.
func (s *Store) ExportToDownloads(id, expectedSHA256 string) (string, error) {
	if os.Geteuid() != 0 {
		return "", errors.New("support export requires root")
	}
	return s.exportToDir(id, expectedSHA256, androidDownloads)
}

func (s *Store) exportToDir(id, expectedSHA256, dir string) (string, error) {
	if !idRx.MatchString(id) || !digestRx.MatchString(expectedSHA256) {
		return "", errors.New("invalid support export identity")
	}
	// Read validates the private archive, its entry hashes, and its size bound.
	data, err := s.Read(id)
	if err != nil {
		return "", err
	}
	hash := sha256.Sum256(data)
	want, _ := hex.DecodeString(expectedSHA256)
	if subtle.ConstantTimeCompare(hash[:], want) != 1 {
		return "", errors.New("support archive SHA-256 mismatch")
	}
	st, err := os.Lstat(dir)
	if err != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("Android Downloads directory is unavailable")
	}
	destination := filepath.Join(dir, "skybind-support-"+id+".zip")
	f, err := os.OpenFile(destination, os.O_WRONLY|os.O_CREATE|os.O_EXCL|syscall.O_NOFOLLOW, 0644)
	if errors.Is(err, os.ErrExist) {
		// Retrying an already completed export must not overwrite an existing
		// public file. Only return success for identical, ordinary files.
		return existingIdentical(destination, hash, len(data))
	}
	if err != nil {
		return "", fmt.Errorf("open Android Downloads export: %w", err)
	}
	_, err = f.Write(data)
	if err == nil {
		err = f.Chmod(0644)
	}
	if err == nil {
		err = f.Sync()
	}
	if closeErr := f.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		_ = os.Remove(destination)
		return "", err
	}
	return destination, nil
}

func existingIdentical(name string, expected [32]byte, expectedBytes int) (string, error) {
	st, err := os.Lstat(name)
	if err != nil || !st.Mode().IsRegular() || st.Size() != int64(expectedBytes) {
		return "", errors.New("Downloads destination already exists and cannot be safely replaced")
	}
	f, err := os.OpenFile(name, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return "", err
	}
	defer f.Close()
	b, err := io.ReadAll(io.LimitReader(f, MaxBundle+1))
	if err != nil || len(b) != expectedBytes {
		return "", errors.New("Downloads destination verification failed")
	}
	h := sha256.Sum256(b)
	if subtle.ConstantTimeCompare(h[:], expected[:]) != 1 {
		return "", errors.New("Downloads destination differs from verified support ZIP")
	}
	return name, nil
}
