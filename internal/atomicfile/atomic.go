// Package atomicfile implements single-file private state publication.
package atomicfile

import (
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"skybind/internal/paths"
	"strings"
	"syscall"
)

func validName(name string) bool {
	return name != "" && name != "." && name != ".." && !strings.ContainsAny(name, "/\\\x00")
}

// Write safely replaces a file in an owner-only private directory.
// Caller must restrict dir to one of the canonical Skybind state directories.
// The directory chain is opened with O_NOFOLLOW, and the target cannot be a symlink.
func Write(dir, name string, data []byte) error { return writeWithHook(dir, name, data, nil) }

func writeWithHook(dir, name string, data []byte, beforeRename func() error) error {
	if !validName(name) {
		return errors.New("invalid state filename")
	}
	fd, err := paths.OpenVerifiedDirectory(dir)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	if err := validateExisting(fd, name, uint32(os.Geteuid())); err != nil {
		return err
	}
	secret := make([]byte, 16)
	if _, err = rand.Read(secret); err != nil {
		return err
	}
	temp := "." + name + "." + hex.EncodeToString(secret) + ".tmp"
	f, err := syscall.Openat(fd, temp, syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0600)
	if err != nil {
		return err
	}
	committed := false
	defer func() {
		if !committed {
			syscall.Unlinkat(fd, temp)
		}
	}()
	file := os.NewFile(uintptr(f), temp)
	if _, err = file.Write(data); err != nil {
		file.Close()
		return err
	}
	if err = file.Sync(); err != nil {
		file.Close()
		return err
	}
	if err = file.Close(); err != nil {
		return err
	}
	if beforeRename != nil {
		if err = beforeRename(); err != nil {
			return err
		}
	}
	// Reject racing changes of the existing target immediately before rename.
	if err = validateExisting(fd, name, uint32(os.Geteuid())); err != nil {
		return err
	}
	if err = syscall.Renameat(fd, temp, fd, name); err != nil {
		return fmt.Errorf("publish: %w", err)
	}
	committed = true
	return syscall.Fsync(fd)
}

func validateExisting(fd int, name string, owner uint32) error {
	f, err := syscall.Openat(fd, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if errors.Is(err, syscall.ENOENT) {
		return nil
	}
	if err != nil {
		return fmt.Errorf("unsafe existing destination: %w", err)
	}
	defer syscall.Close(f)
	var st syscall.Stat_t
	if err = syscall.Fstat(f, &st); err != nil {
		return err
	}
	if st.Mode&syscall.S_IFMT != syscall.S_IFREG || st.Uid != owner || st.Mode&0777 != 0600 || st.Nlink != 1 {
		return errors.New("unsafe existing private file ownership/mode/link count")
	}
	return nil
}

// Read returns a bounded file snapshot. The caller specifies a small private
// state limit and cannot escape the verified private directory.
func Read(dir, name string, max int64) ([]byte, error) {
	if !validName(name) || max <= 0 {
		return nil, errors.New("invalid private read")
	}
	fd, err := paths.OpenVerifiedDirectory(dir)
	if err != nil {
		return nil, err
	}
	defer syscall.Close(fd)
	if err = validateExisting(fd, name, uint32(os.Geteuid())); err != nil {
		return nil, err
	}
	f, err := syscall.Openat(fd, name, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if err != nil {
		return nil, err
	}
	file := os.NewFile(uintptr(f), name)
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, max+1))
	if err != nil {
		return nil, err
	}
	if int64(len(data)) > max {
		return nil, errors.New("private file size limit exceeded")
	}
	return data, nil
}
