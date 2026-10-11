// Package runtimeauth resolves immutable Skybind module paths; no PATH lookup.
package runtimeauth

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"skybind/internal/integrity"
	"skybind/internal/paths"
	"strings"
	"syscall"
)

type Status struct {
	Provider            string `json:"provider"`
	Ready               bool   `json:"ready"`
	Reason              string `json:"reason"`
	ProvenanceAvailable bool   `json:"provenance_available"`
	ProvenanceValid     bool   `json:"provenance_valid"`
	RuntimeSHA256       string `json:"runtime_sha256,omitempty"`
	FuseHelperSHA256    string `json:"fuse_helper_sha256,omitempty"`
	Binary              string `json:"binary,omitempty"`
	FuseHelperBinary    string `json:"fuse_helper_binary,omitempty"`
	Config              string `json:"config,omitempty"`
}

// StatusCanonical is read-only and intentionally cannot take a path override.
func StatusCanonical() Status { return inspect(paths.ModuleRoot) }

// inspect is package-private for mock module fixtures. Never expose it from CLI.
func inspect(module string) Status {
	st := Status{Reason: "not verified"}
	path := filepath.Join(module, "runtime.provenance.json")
	fd, e := syscall.Open(path, syscall.O_RDONLY|syscall.O_NOFOLLOW|syscall.O_CLOEXEC, 0)
	if e != nil {
		st.Reason = e.Error()
		return st
	}
	f := os.NewFile(uintptr(fd), path)
	defer f.Close()
	stat, e := f.Stat()
	if e != nil || !stat.Mode().IsRegular() || stat.Size() > 128*1024 || stat.Mode().Perm()&022 != 0 {
		st.Reason = "unsafe manifest mode or size"
		return st
	}
	// Reject symlinks in module-relative ancestors as well as final files.
	for _, member := range []string{"runtime.provenance.json", "system", "system/bin", "system/vendor", "system/vendor/bin", "system/vendor/lib64"} {
		p := filepath.Join(module, member)
		info, err := os.Lstat(p)
		if err != nil {
			continue
		} // lib64 optional in future; missing files are checked below
		if info.Mode()&os.ModeSymlink != 0 {
			st.Reason = "module path contains symlink"
			return st
		}
	}
	if strings.Contains(module, "/../") {
		st.Reason = "invalid module path"
		return st
	}
	b := make([]byte, stat.Size())
	n, e := io.ReadFull(f, b)
	if e != nil || int64(n) != stat.Size() {
		st.Reason = "manifest read failed"
		return st
	}
	m, e := integrity.Decode(b)
	if e != nil {
		st.Reason = e.Error()
		return st
	}
	st.Provider = m.Provider
	st.ProvenanceAvailable = true
	st.RuntimeSHA256 = m.Files[m.Engine].SHA256
	st.FuseHelperSHA256 = m.Files[m.Helper].SHA256
	st.Binary = filepath.Join(module, m.Engine)
	st.FuseHelperBinary = filepath.Join(module, m.Helper)
	st.Config = paths.RcloneConfig
	for name, info := range m.Files {
		p := filepath.Join(module, name)
		if e = integrity.CheckOpen(p, info); e != nil {
			st.Reason = fmt.Sprintf("%s: %v", name, e)
			return st
		}
	}
	// A helper is not proof of actual usable FUSE, which requires device checks.
	st.Ready = true
	st.ProvenanceValid = true
	st.Reason = "on-disk hashes verified; FUSE device untested"
	return st
}

var ErrRuntimeNotReady = errors.New("bundled runtime not verified")
