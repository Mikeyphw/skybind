package backup

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"syscall"
)

const Downloads = "/storage/emulated/0/Download"

func SaveToDownloads(doc Document) (string, error) {
	if os.Geteuid() != 0 {
		return "", errors.New("backup export requires root")
	}
	return SaveToDir(doc, Downloads)
}

// SaveToDir is restricted to the compiled-in Downloads directory in production;
// a named, non-overwritable JSON document is never used for privileged reads.
func SaveToDir(doc Document, dir string) (string, error) {
	if err := Validate(doc); err != nil {
		return "", err
	}
	st, err := os.Lstat(dir)
	if err != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return "", errors.New("Downloads directory is unavailable")
	}
	data, err := json.Marshal(doc)
	if err != nil {
		return "", err
	}

	name := "skybind-personal-backup-" + doc.SHA256[:16] + ".json"
	dest := filepath.Join(dir, name)
	fd, err := os.OpenFile(dest, os.O_WRONLY|os.O_EXCL|os.O_CREATE|syscall.O_NOFOLLOW, 0644)
	if errors.Is(err, os.ErrExist) {
		old, e := os.Lstat(dest)
		if e != nil || !old.Mode().IsRegular() || old.Size() != int64(len(data)) {
			return "", errors.New("backup destination already exists and differs")
		}
		f, e := os.OpenFile(dest, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
		if e != nil {
			return "", e
		}
		defer f.Close()
		existing, e := io.ReadAll(io.LimitReader(f, int64(len(data))+1))
		if e != nil || !bytes.Equal(existing, data) {
			return "", errors.New("backup destination already exists and differs")
		}
		return dest, nil
	}
	if err != nil {
		return "", err
	}
	_, err = fd.Write(data)
	if err == nil {
		err = fd.Sync()
	}
	if e := fd.Close(); err == nil {
		err = e
	}
	if err != nil {
		_ = os.Remove(dest)
		return "", err
	}
	return dest, nil
}
