package namespace

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
)

type linuxWorker struct{}

func (linuxWorker) call(ctx context.Context, kind string, pid int, ns string, src Signature, id string) (string, error) {
	if os.Geteuid() != 0 || pid <= 0 || !filepath.IsAbs(src.Target) || src.Target == "/" {
		return "", errors.New("namespace worker requires root and verified target")
	}
	h, e := os.Open(fmt.Sprintf("/proc/%d/ns/mnt", pid))
	if e != nil {
		return "", e
	}
	defer h.Close()
	actual, e := os.Readlink(fmt.Sprintf("/proc/%d/ns/mnt", pid))
	if e != nil || actual != ns {
		return "", errors.New("namespace identity drift")
	}
	// Reverify the mount ID before pinning the source descriptor. If the
	// source changed since the manager preview, never bind the new filesystem.
	pre, ok, e := mountAt(src.Target)
	if e != nil || !ok || pre.MountID != src.MountID || pre.FS != src.FS || pre.Source != src.Source {
		return "", errors.New("source mount identity changed before worker")
	}
	if e = validNoSymlinks(src.Target); e != nil {
		return "", e
	}
	// Open the owned source before entering the target namespace, and pin it by fd.
	f, e := os.Open(src.Target)
	if e != nil {
		return "", e
	}
	defer f.Close()
	args := []string{"_ns-worker", kind, ns, src.Target, src.FS, src.Source, id}
	cmd := exec.CommandContext(ctx, "/proc/self/exe", args...)
	cmd.ExtraFiles = []*os.File{h, f}
	cmd.Env = []string{"PATH=/system/bin:/system/xbin"}
	b, e := cmd.Output()
	if e != nil {
		return "", fmt.Errorf("namespace worker failed: %w", e)
	}
	var out struct {
		MountID string `json:"mount_id"`
		Error   string `json:"error"`
	}
	if json.Unmarshal(b, &out) != nil || out.Error != "" || out.MountID == "" {
		return "", errors.New("unverified namespace worker outcome")
	}
	return out.MountID, nil
}
func (w linuxWorker) Bind(ctx context.Context, pid int, ns string, src Signature) (string, error) {
	return w.call(ctx, "bind", pid, ns, src, "")
}
func (w linuxWorker) Detach(ctx context.Context, r BindRecord) error {
	_, e := w.call(ctx, "detach", r.PID, r.Namespace, r.Source, r.MountID)
	return e
}
func mountAt(target string) (Signature, bool, error) {
	data, e := os.ReadFile("/proc/self/mountinfo")
	if e != nil {
		return Signature{}, false, e
	}
	if len(data) > maxMountinfoBytes {
		return Signature{}, false, errors.New("mountinfo too large")
	}
	for _, s := range parseMountinfo(data) {
		if s.Target == target {
			return s, true, nil
		}
	}
	return Signature{}, false, nil
}
func validNoSymlinks(target string) error {
	if !filepath.IsAbs(target) || filepath.Clean(target) != target || target == "/" {
		return errors.New("unsafe namespace destination")
	}
	path := "/"
	for _, c := range strings.Split(strings.TrimPrefix(target, "/"), "/") {
		if c == "" || c == ".." || c == "." {
			return errors.New("unsafe target component")
		}
		path = filepath.Join(path, c)
		st, e := os.Lstat(path)
		if e != nil {
			return e
		}
		if !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
			return errors.New("symlink or non-directory target")
		}
	}
	return nil
}

// RunWorker is reachable only via the private _ns-worker subprocess entrypoint.
// It never consumes web/CLI-provided executable names or arbitrary flags.
func RunWorker(args []string) int {
	errout := func(e error) int {
		b, _ := json.Marshal(map[string]string{"error": e.Error()})
		fmt.Println(string(b))
		return 1
	}
	if len(args) != 6 || os.Geteuid() != 0 {
		return errout(errors.New("invalid privileged worker request"))
	}
	kind, ns, target, fs, source, wantID := args[0], args[1], args[2], args[3], args[4], args[5]
	if kind != "bind" && kind != "detach" {
		return errout(errors.New("invalid worker action"))
	}
	if !strings.HasPrefix(fs, "fuse") || source == "" || ns == "" {
		return errout(errors.New("invalid filesystem identity"))
	}
	nf := os.NewFile(3, "namespace-fd")
	sf := os.NewFile(4, "source-fd")
	if nf == nil || sf == nil {
		return errout(errors.New("worker descriptors unavailable"))
	}
	defer nf.Close()
	defer sf.Close()
	// Restrict to the actual pinned descriptor's identity (not a PID lookup).
	actual, e := os.Readlink("/proc/self/fd/3")
	if e != nil || !strings.Contains(actual, "mnt:") {
		return errout(errors.New("namespace descriptor invalid"))
	}
	if actual != ns {
		return errout(errors.New("namespace changed before worker"))
	}
	// setns mutates a thread only: run inside a disposable subprocess, lock this OS thread.
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	var call uintptr
	switch runtime.GOARCH {
	case "arm64":
		call = 268
	case "amd64":
		call = 308
	default:
		return errout(errors.New("unsupported setns architecture"))
	}
	_, _, errno := syscall.RawSyscall(call, uintptr(nf.Fd()), uintptr(0x00020000), 0) // CLONE_NEWNS
	if errno != 0 {
		return errout(errno)
	}
	if e = validNoSymlinks(target); e != nil {
		return errout(e)
	}
	at, exists, e := mountAt(target)
	if e != nil {
		return errout(e)
	}
	if kind == "bind" {
		if exists {
			return errout(errors.New("destination is occupied in target namespace"))
		}
		if e = syscall.Mount("/proc/self/fd/4", target, "", syscall.MS_BIND, ""); e != nil {
			return errout(e)
		}
		at, exists, e = mountAt(target)
		if e != nil || !exists || at.MountID == "" || at.FS != fs || at.Source != source {
			_ = syscall.Unmount(target, 0)
			return errout(errors.New("post-bind signature verification failed"))
		}
	} else {
		if !exists || wantID == "" || at.MountID != wantID || at.FS != fs || at.Source != source {
			return errout(errors.New("refusing to unmount foreign or changed target"))
		}
		if e = syscall.Unmount(target, 0); e != nil {
			return errout(e)
		}
	}
	b, _ := json.Marshal(map[string]string{"mount_id": at.MountID})
	fmt.Println(string(b))
	return 0
}
