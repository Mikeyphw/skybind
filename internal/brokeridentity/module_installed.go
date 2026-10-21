package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
)

const (
	installedChrootModule = "/data/adb/modules/chrootctl"
	chrootEntry           = "runtime/arm64-v8a/chrootctl"
	chrootManifest        = "config/chrootctl/module-package-manifest.json"
)

// InstalledModuleAttestor verifies an operator-approved manifest digest,
// the installed executable referenced by that manifest, and /proc/PID/exe.
// ModuleSealSHA256 is independently approved, NOT learnt from the client,
// the module's self-asserted manifest, or an automatically changing source pin.
// Root/ProcRoot are restricted to canonical paths on Android; substitutions
// exist solely for isolated host tests, never in the daemon boot contract.
type InstalledModuleAttestor struct{ Root, ProcRoot string }

type packageSeal struct {
	SchemaVersion     int    `json:"schemaVersion"`
	ModuleID          string `json:"moduleId"`
	RuntimeABI        string `json:"runtimeAbi"`
	RuntimeEntrypoint string `json:"runtimeEntrypoint"`
	Files             []struct {
		Path       string `json:"path"`
		Size       int64  `json:"size"`
		SHA256     string `json:"sha256"`
		Mode       string `json:"mode"`
		Executable bool   `json:"executable"`
	} `json:"files"`
}

func trustedModuleFile(path string, max int64, executable bool) ([]byte, error) {
	st, err := os.Lstat(path)
	if err != nil || !st.Mode().IsRegular() || st.Size() < 1 || st.Size() > max || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm()&0022 != 0 {
		return nil, ErrUnverified
	}
	raw, ok := st.Sys().(*syscall.Stat_t)
	if !ok || raw.Uid != 0 || (executable && st.Mode().Perm() != 0755) {
		return nil, ErrUnverified
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, ErrUnverified
	}
	defer f.Close()
	fst, err := f.Stat()
	if err != nil || !os.SameFile(st, fst) {
		return nil, ErrUnverified
	}
	data, err := io.ReadAll(io.LimitReader(f, max+1))
	if err != nil || int64(len(data)) > max || int64(len(data)) != st.Size() {
		return nil, ErrUnverified
	}
	after, err := os.Lstat(path)
	if err != nil || !os.SameFile(st, after) || !after.ModTime().Equal(st.ModTime()) {
		return nil, ErrUnverified
	}
	return data, nil
}

func trustedRootDirs(root string) error {
	for _, rel := range []string{"", "config", "config/chrootctl", "runtime", "runtime/arm64-v8a"} {
		p := filepath.Join(root, rel)
		st, err := os.Lstat(p)
		if err != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm()&0022 != 0 {
			return ErrUnverified
		}
		s, ok := st.Sys().(*syscall.Stat_t)
		if !ok || s.Uid != 0 {
			return ErrUnverified
		}
	}
	return nil
}

func (a InstalledModuleAttestor) VerifyModuleProcess(ctx context.Context, pid int32, pin ModulePin) error {
	if !cleanModulePin(pin) || pid <= 0 {
		return ErrUnverified
	}
	root, proc := a.Root, a.ProcRoot
	if root == "" {
		root = installedChrootModule
	}
	if proc == "" {
		proc = "/proc"
	}
	if !filepath.IsAbs(root) || filepath.Clean(root) != root || !filepath.IsAbs(proc) || filepath.Clean(proc) != proc {
		return ErrUnverified
	}
	if root != installedChrootModule && proc == "/proc" {
		return ErrUnverified
	}
	if err := ctx.Err(); err != nil {
		return ErrUnverified
	}
	if err := trustedRootDirs(root); err != nil {
		return err
	}
	manifest, err := trustedModuleFile(filepath.Join(root, chrootManifest), 1<<20, false)
	if err != nil {
		return ErrUnverified
	}
	seal := sha256.Sum256(manifest)
	want, _ := hex.DecodeString(pin.ModuleSealSHA256)
	if len(want) != 32 || !constantTimeDigest(seal[:], want) {
		return ErrUnverified
	}
	var m packageSeal
	if err = json.Unmarshal(manifest, &m); err != nil || m.SchemaVersion != 1 || m.ModuleID != "chrootctl" || m.RuntimeABI != "arm64-v8a" || m.RuntimeEntrypoint != "chrootctl" {
		return ErrUnverified
	}
	var expected string
	var count int
	for _, file := range m.Files {
		if file.Path == chrootEntry {
			count++
			if !file.Executable || file.Mode != "0755" || file.Size < 1 || file.Size > 100<<20 || !cleanSHA256(file.SHA256) {
				return ErrUnverified
			}
			expected = file.SHA256
		}
	}
	if count != 1 {
		return ErrUnverified
	}
	exe := filepath.Join(root, chrootEntry)
	disk, err := trustedModuleFile(exe, 100<<20, true)
	if err != nil {
		return ErrUnverified
	}
	digest := sha256.Sum256(disk)
	if hex.EncodeToString(digest[:]) != expected {
		return ErrUnverified
	}
	procExe := filepath.Join(proc, strconv.FormatInt(int64(pid), 10), "exe")
	target, err := os.Readlink(procExe)
	if err != nil || target != exe || strings.Contains(target, " (deleted)") {
		return ErrUnverified
	}
	processFD, err := os.Open(procExe)
	if err != nil {
		return ErrUnverified
	}
	defer processFD.Close()
	running, err := processFD.Stat()
	installed, ie := os.Stat(exe)
	if err != nil || ie != nil || !os.SameFile(running, installed) {
		return ErrUnverified
	}
	processDigest := sha256.New()
	n, err := io.Copy(processDigest, io.LimitReader(processFD, 100<<20+1))
	if err != nil || n != int64(len(disk)) || !constantTimeDigest(processDigest.Sum(nil), digest[:]) {
		return ErrUnverified
	}
	// Detect mutation of the already approved manifest while hashing the executable.
	again, err := trustedModuleFile(filepath.Join(root, chrootManifest), 1<<20, false)
	if err != nil || sha256.Sum256(again) != seal {
		return ErrUnverified
	}
	if err := ctx.Err(); err != nil {
		return ErrUnverified
	}
	return nil
}

func constantTimeDigest(a, b []byte) bool {
	if len(a) != len(b) {
		return false
	}
	var mismatch byte
	for i := range a {
		mismatch |= a[i] ^ b[i]
	}
	return mismatch == 0
}

// Ensure the concrete module attestor actually satisfies RootVerifier's trust slot.
var _ ModuleAttestor = InstalledModuleAttestor{}
