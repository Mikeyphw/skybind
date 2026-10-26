package integrity

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

type File struct {
	SHA256 string `json:"sha256"`
	Size   int64  `json:"size"`
}
type Manifest struct {
	Schema   int             `json:"schema_version"`
	Product  string          `json:"product"`
	Provider string          `json:"provider"`
	Arch     string          `json:"arch"`
	Engine   string          `json:"engine_path"`
	Helper   string          `json:"helper_path"`
	Files    map[string]File `json:"files"`
}

// CheckOpen verifies exact bytes through an O_NOFOLLOW descriptor. Caller must
// first ensure the module parent chain is trusted/owned by root.
func CheckOpen(path string, want File) error {
	if len(want.SHA256) != 64 || want.Size <= 0 {
		return errors.New("invalid digest/size authority")
	}
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_CLOEXEC|syscall.O_NOFOLLOW, 0)
	if e != nil {
		return e
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	st, e := f.Stat()
	if e != nil {
		return e
	}
	if !st.Mode().IsRegular() || st.Size() != want.Size || st.Mode().Perm()&022 != 0 {
		return errors.New("invalid mode/size/regular-file")
	}
	h := sha256.New()
	n, e := io.Copy(h, io.LimitReader(f, want.Size+1))
	if e != nil {
		return e
	}
	if n != want.Size || hex.EncodeToString(h.Sum(nil)) != want.SHA256 {
		return errors.New("runtime bytes differ from provenance")
	}
	return nil
}

func Decode(data []byte) (Manifest, error) {
	var m Manifest
	if len(data) > 128*1024 {
		return m, errors.New("manifest exceeds bounded size")
	}
	if e := json.Unmarshal(data, &m); e != nil {
		return m, e
	}
	if m.Schema != 1 || m.Product != "Skybind" || m.Arch != "arm64" || (m.Provider != "newfuture" && m.Provider != "bclone") || (m.Engine != "system/bin/rclone" && m.Engine != "system/bin/skybind-rclone-engine") || m.Helper != "system/vendor/bin/fusermount3" {
		return m, errors.New("invalid runtime authority")
	}
	// Runtime v1 includes pinned provider ELF plus fusermount3. Native CLI modules
	// additionally include the immutable public launcher; shared
	// libfuse layouts may have additional members. Both executable members
	// remain mandatory and every listed file is digest-checked on disk.
	if len(m.Files) < 2 || len(m.Files) > 66 {
		return m, errors.New("invalid manifest inventory")
	}
	for p, f := range m.Files {
		if filepath.IsAbs(p) || strings.Contains(p, "\\") || filepath.Clean(p) != p || strings.HasPrefix(p, "../") || strings.Contains("/"+p+"/", "/../") || !strings.HasPrefix(p, "system/") || len(f.SHA256) != 64 || f.Size <= 0 {
			return m, fmt.Errorf("invalid manifest member: %s", p)
		}
		if _, err := hex.DecodeString(f.SHA256); err != nil {
			return m, err
		}
	}
	if m.Engine == "system/bin/skybind-rclone-engine" {
		if _, ok := m.Files["system/bin/rclone"]; !ok {
			return m, errors.New("native runtime launcher missing in provenance")
		}
		if _, ok := m.Files["system/bin/skybind-rclone"]; !ok {
			return m, errors.New("native runtime public alias missing in provenance")
		}
	}
	if _, ok := m.Files[m.Engine]; !ok {
		return m, errors.New("engine missing in provenance")
	}
	if _, ok := m.Files[m.Helper]; !ok {
		return m, errors.New("helper missing in provenance")
	}
	return m, nil
}
