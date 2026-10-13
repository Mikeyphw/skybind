// Package paths owns canonical product paths. No environment variable,
// CLI argument, or unprivileged WebUI input may override these values.
package paths

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

const (
	ModuleRoot   = "/data/adb/modules/skybind"
	StateRoot    = "/data/adb/skybind"
	Engine       = ModuleRoot + "/system/bin/rclone"
	FuseHelper   = ModuleRoot + "/system/vendor/bin/fusermount3"
	DaemonSocket = StateRoot + "/run/skybindd.sock"
	RcloneConfig = StateRoot + "/config/rclone.conf"
)

// linuxOPath is Linux O_PATH (0x200000), also used by Android arm64.
// The stdlib syscall package does not expose this constant on all Go hosts.
const linuxOPath = 0x200000

// StateDirectories is an immutable allowlist of root-private storage directories.
var StateDirectories = [...]string{
	"run", "config", "config/previous", "desired", "health", "jobs",
	"namespace", "cache", "logs", "rc", "ui", "support", "journal", "locks",
	"offline", "offline/objects", "offline/writes", "offline/writes/objects",
}

// Layout is a read-only set of well-known paths, not a mutable root override.
type Layout struct {
	Module, State, Engine, Fuse, Socket, Config string
}

func Default() Layout {
	return Layout{ModuleRoot, StateRoot, Engine, FuseHelper, DaemonSocket, RcloneConfig}
}

func validateRelative(part string) error {
	if part == "" || part == "." || part == ".." || filepath.IsAbs(part) || strings.Contains(part, "\\") {
		return errors.New("unsafe private relative path")
	}
	for _, s := range strings.Split(part, "/") {
		if s == "" || s == "." || s == ".." {
			return errors.New("unsafe private relative path")
		}
	}
	return nil
}

// Child produces only a clean subpath; it does not create or verify filesystem content.
func Child(relative string) (string, error) {
	if err := validateRelative(relative); err != nil {
		return "", err
	}
	return StateRoot + "/" + relative, nil
}

// EnsurePrivateState requires actual effective root and creates/verifies the
// canonical tree using descriptor-relative O_NOFOLLOW traversals.
func EnsurePrivateState() error {
	if os.Geteuid() != 0 {
		return errors.New("Skybind private state requires root")
	}
	return ensureAt(StateRoot, StateDirectories[:], 0)
}

// ensureAt is only used by package-internal unit fixtures and by the
// canonical root caller above. No alternate root enters a privileged command.
func ensureAt(base string, dirs []string, owner uint32) error {
	if !filepath.IsAbs(base) || filepath.Clean(base) != base {
		return errors.New("state root must be a clean absolute path")
	}
	fd, err := openTree(base, true, owner)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	for _, child := range dirs {
		if err := validateRelative(child); err != nil {
			return err
		}
		current, err := syscall.Dup(fd)
		if err != nil {
			return err
		}
		for _, component := range strings.Split(child, "/") {
			next, e := secureDirChild(current, component, true, owner)
			syscall.Close(current)
			if e != nil {
				return fmt.Errorf("%s: %w", child, e)
			}
			current = next
		}
		syscall.Close(current)
	}
	return nil
}

// openTree anchors traversal at / and rejects symlinks in EVERY path component.
// Only the private leaf and its newly created descendants are permission checked;
// Android-controlled /data parents have platform-dependent owners/modes.
func openTree(path string, create bool, owner uint32) (int, error) {
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || path == "/" {
		return -1, errors.New("invalid private root")
	}
	// An Android app may search /data/data without permission to list it.
	// O_PATH allows search-only traversal without opening parent directories
	// for reading. The final private directory still requires O_RDONLY and
	// is checked for exact owner and mode below.
	current, err := syscall.Open("/", linuxOPath|syscall.O_DIRECTORY|syscall.O_CLOEXEC, 0)
	if err != nil {
		return -1, err
	}
	segments := strings.Split(strings.TrimPrefix(path, "/"), "/")
	for i, component := range segments {
		leaf := i == len(segments)-1
		var next int
		var e error
		if leaf {
			next, e = secureDirChild(current, component, create, owner)
			if e == nil {
				e = checkPrivateFD(next, owner)
			}
		} else {
			// O_NOFOLLOW|O_DIRECTORY rejects any symlinked ancestor.
			// Prefer a readable directory descriptor where available so we
			// can fsync it when creating the private state root.
			flags := syscall.O_DIRECTORY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC
			next, e = syscall.Openat(current, component, flags|syscall.O_RDONLY, 0)
			if errors.Is(e, syscall.EACCES) || errors.Is(e, syscall.EPERM) {
				next, e = syscall.Openat(current, component, flags|linuxOPath, 0)
			}
		}
		syscall.Close(current)
		if e != nil {
			if next >= 0 {
				syscall.Close(next)
			}
			return -1, e
		}
		current = next
	}
	return current, nil
}

func secureDirChild(parent int, name string, create bool, owner uint32) (int, error) {
	if name == "" || name == "." || name == ".." {
		return -1, errors.New("unsafe directory component")
	}
	flags := syscall.O_RDONLY | syscall.O_DIRECTORY | syscall.O_NOFOLLOW | syscall.O_CLOEXEC
	fd, err := syscall.Openat(parent, name, flags, 0)
	if errors.Is(err, syscall.ENOENT) && create {
		if e := syscall.Mkdirat(parent, name, 0700); e != nil && !errors.Is(e, syscall.EEXIST) {
			return -1, e
		}
		// Fsync the parent entry when the kernel gives us a readable fd.
		// Fsync on a search-only O_PATH descriptor returns EBADF. The
		// exception is allowed only for a *verified O_PATH* parent, never
		// for owned private directories (which use O_RDONLY descriptors).
		if e := syscall.Fsync(parent); e != nil {
			if !errors.Is(e, syscall.EBADF) || !isOPathFD(parent) {
				return -1, e
			}
		}
		fd, err = syscall.Openat(parent, name, flags, 0)
	}
	if err != nil {
		return -1, err
	}
	if create {
		if err = checkPrivateFD(fd, owner); err != nil {
			syscall.Close(fd)
			return -1, err
		}
	}
	return fd, nil
}

func isOPathFD(fd int) bool {
	flags, _, errno := syscall.Syscall(syscall.SYS_FCNTL, uintptr(fd), uintptr(syscall.F_GETFL), 0)
	return errno == 0 && flags&linuxOPath == linuxOPath
}

func checkPrivateFD(fd int, owner uint32) error {
	var st syscall.Stat_t
	if err := syscall.Fstat(fd, &st); err != nil {
		return err
	}
	if st.Mode&syscall.S_IFMT != syscall.S_IFDIR {
		return errors.New("not a directory")
	}
	if st.Uid != owner {
		return fmt.Errorf("private directory owner %d, need %d", st.Uid, owner)
	}
	if st.Mode&0777 != 0700 {
		return fmt.Errorf("private directory mode %o, need 700", st.Mode&0777)
	}
	return nil
}

// OpenVerifiedDirectory is consumed by atomicfile to avoid path re-resolution.
// Only files beneath a checked caller-owned private directory may be written.
func OpenVerifiedDirectory(path string) (int, error) {
	return openTree(path, false, uint32(os.Geteuid()))
}
