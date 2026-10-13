package offline

// A separately published, immutable-by-convention Android Downloads snapshot
// tree of complete pins. This is NOT a FUSE overlay, not a synced folder, and
// not a writable offline journal. The original private objects remain intact.

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"syscall"
	"time"
)

const publicViewRoot = "/storage/emulated/0/Download/Skybind-Offline-Views"

// PublishView makes a distinct complete Android-visible snapshot for one mount.
// It neither changes the original FUSE mount nor contacts the remote provider.
// A new path is generated each time: older views are NEVER silently replaced.
func (s *Store) PublishView(ctx context.Context, mount string) (string, error) {
	return s.publishViewAt(ctx, mount, publicViewRoot)
}

func (s *Store) publishViewAt(ctx context.Context, mount, root string) (string, error) {
	if !safeName.MatchString(mount) {
		return "", errors.New("invalid offline view mount")
	}
	if err := ctx.Err(); err != nil {
		return "", err
	}
	release, err := s.lock()
	if err != nil {
		return "", err
	}
	defer release()
	manifest, err := s.load()
	if err != nil {
		return "", err
	}
	configured, err := s.mount(mount)
	if err != nil {
		return "", err
	}
	expectedIdentity := identity(configured)
	pins := make([]Pin, 0)
	var bytes int64
	for _, p := range manifest.Pins {
		if p.Mount != mount {
			continue
		}
		if err = validatePath(p.Path); err != nil {
			return "", err
		}
		if p.RemoteIdentity != expectedIdentity {
			return "", errors.New("offline view contains stale remote identity")
		}
		pins = append(pins, p)
		bytes += p.Size
		if len(pins) > maxFiles || bytes > manifest.QuotaBytes {
			return "", errors.New("offline view exceeds bound")
		}
	}
	if len(pins) == 0 {
		return "", errors.New("no pinned files for selected mount")
	}
	sort.Slice(pins, func(i, j int) bool { return pins[i].Path < pins[j].Path })
	// No public output is created if even one private object fails verification.
	for _, p := range pins {
		if err = ctx.Err(); err != nil {
			return "", err
		}
		h, n, e := hashFile(filepath.Join(s.dir, "objects", p.SHA256))
		if e != nil || h != p.SHA256 || n != p.Size {
			return "", errors.New("offline view source is not verified")
		}
	}
	// The fixed Android Downloads root must exist. Never create arbitrary parent
	// paths or accept path components swapped to symlinks.
	if err = ensureViewRoot(root); err != nil {
		return "", err
	}
	var stat syscall.Statfs_t
	if err = syscall.Statfs(root, &stat); err != nil {
		return "", err
	}
	if uint64(bytes+minFree) > stat.Bavail*uint64(stat.Bsize) {
		return "", errors.New("insufficient space to publish offline view")
	}
	base, err := openViewDirectory(root)
	if err != nil {
		return "", err
	}
	defer syscall.Close(base)
	if err = mkdirOpenat(base, mount, 0755); err != nil {
		return "", err
	}
	mountfd, err := syscall.Openat(base, mount, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return "", err
	}
	defer syscall.Close(mountfd)
	var nonce [12]byte
	if _, err = rand.Read(nonce[:]); err != nil {
		return "", err
	}
	suffix := time.Now().UTC().Format("20060102T150405Z") + "-" + hex.EncodeToString(nonce[:])
	staging := ".building-" + suffix
	final := "snapshot-" + suffix
	if err = syscall.Mkdirat(mountfd, staging, 0755); err != nil {
		return "", err
	}
	committed := false
	defer func() {
		if !committed {
			_ = os.RemoveAll(filepath.Join(root, mount, staging))
		}
	}()
	stagefd, err := syscall.Openat(mountfd, staging, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return "", err
	}
	defer syscall.Close(stagefd)
	for _, p := range pins {
		if err = ctx.Err(); err != nil {
			return "", err
		}
		if err = copyVerifiedIntoView(ctx, stagefd, p, filepath.Join(s.dir, "objects", p.SHA256)); err != nil {
			return "", err
		}
	}
	_ = syscall.Fchmod(stagefd, 0755) // best effort on emulated storage
	if err = syncPublicDirectory(stagefd); err != nil {
		return "", err
	}
	// New unpredictable destination, no replace. On Android/Linux renameat2
	// RENAME_NOREPLACE is not guaranteed, so refuse any preexisting entry before
	// renaming. Only this process knows the fresh random destination.
	if existingFD, e := syscall.Openat(mountfd, final, syscall.O_RDONLY|syscall.O_NOFOLLOW, 0); e == nil {
		_ = syscall.Close(existingFD)
		return "", errors.New("offline view destination already exists")
	} else if e != syscall.ENOENT {
		return "", e
	}
	if err = syscall.Renameat(mountfd, staging, mountfd, final); err != nil {
		return "", err
	}
	committed = true
	if err = syncPublicDirectory(mountfd); err != nil {
		return "", fmt.Errorf("view published but directory sync failed: %w", err)
	}
	return filepath.Join(root, mount, final), nil
}

func ensureViewRoot(root string) error {
	// Production root is fixed, with symlink-safe parent verification.
	if root == publicViewRoot {
		if err := ensureExportParent(root); err != nil {
			return err
		}
		// Android emulated storage may ignore or reject chmod; public copies
		// must never be described as permission-enforced read-only files.
		_ = os.Chmod(root, 0755)
	} else if !filepath.IsAbs(root) || filepath.Clean(root) != root {
		return errors.New("invalid test view root")
	}
	st, err := os.Lstat(root)
	if err != nil || !st.IsDir() || st.Mode()&os.ModeSymlink != 0 {
		return errors.New("offline view root unavailable or unsafe")
	}
	return nil
}
func openViewDirectory(path string) (int, error) {
	return syscall.Open(path, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
}
func mkdirOpenat(parent int, name string, mode uint32) error {
	if err := syscall.Mkdirat(parent, name, mode); err != nil && err != syscall.EEXIST {
		return err
	}
	fd, err := syscall.Openat(parent, name, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return err
	}
	defer syscall.Close(fd)
	_ = syscall.Fchmod(fd, mode) // emulated storage may not implement chmod
	return nil
}
func copyVerifiedIntoView(ctx context.Context, stagefd int, pin Pin, source string) error {
	segments := strings.Split(pin.Path, "/")
	parent := stagefd
	closeParents := func() {
		if parent != stagefd {
			_ = syscall.Close(parent)
		}
	}
	defer closeParents()
	for _, seg := range segments[:len(segments)-1] {
		if err := mkdirOpenat(parent, seg, 0755); err != nil {
			return err
		}
		next, err := syscall.Openat(parent, seg, syscall.O_RDONLY|syscall.O_DIRECTORY|syscall.O_NOFOLLOW, 0)
		if err != nil {
			return err
		}
		if parent != stagefd {
			_ = syscall.Close(parent)
		}
		parent = next
	}
	src, err := os.OpenFile(source, os.O_RDONLY|syscall.O_NOFOLLOW, 0)
	if err != nil {
		return err
	}
	defer src.Close()
	st, err := src.Stat()
	if err != nil || !st.Mode().IsRegular() || st.Mode().Perm() != 0600 || st.Size() != pin.Size {
		return errors.New("offline source unsafe")
	}
	raw, ok := st.Sys().(*syscall.Stat_t)
	if !ok || raw.Nlink != 1 {
		return errors.New("offline source not singly owned")
	}
	fd, err := syscall.Openat(parent, segments[len(segments)-1], syscall.O_WRONLY|syscall.O_CREAT|syscall.O_EXCL|syscall.O_NOFOLLOW, 0444)
	if err != nil {
		return err
	}
	out := os.NewFile(uintptr(fd), "offline-view-copy")
	h := sha256.New()
	n, copyErr := io.Copy(io.MultiWriter(out, h), cancelableReader{ctx: ctx, r: src})
	if copyErr == nil {
		_ = out.Chmod(0444) // advisory only; Android shared storage may ignore
	}
	if copyErr == nil {
		copyErr = out.Sync()
	}
	closeErr := out.Close()
	if copyErr == nil {
		copyErr = closeErr
	}
	if copyErr != nil || n != pin.Size || hex.EncodeToString(h.Sum(nil)) != pin.SHA256 {
		return errors.New("offline view copy verification failed")
	}
	return nil
}

// Android emulated-storage FUSE may not implement directory fsync. The
// root-private verified store remains the durable source of truth; failure to
// support a public directory fsync is not evidence that copies are corrupted.
func syncPublicDirectory(fd int) error {
	err := syscall.Fsync(fd)
	if err == syscall.EINVAL || err == syscall.ENOSYS || err == syscall.EOPNOTSUPP {
		return nil
	}
	return err
}
