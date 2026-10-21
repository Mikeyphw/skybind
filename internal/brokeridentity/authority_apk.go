package brokeridentity

// AuthorityAPKAnchor checks a separately operator-approved installed Skybind
// APK byte seal. This is an independent exact-file trust anchor, NOT a proof
// of APK signing lineage or of the APK's association with a kernel PID.
// Those remain separate required Android platform checks before production.
import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

type AuthorityAnchor interface {
	VerifyAuthorityProcess(context.Context, int32, uint32) error
}
type AuthorityAPKAnchor struct {
	AppUID             uint32
	ApprovedAPKPath    string
	ApprovedAPK_SHA256 string
}

func (a AuthorityAPKAnchor) VerifyAuthorityProcess(ctx context.Context, pid int32, uid uint32) error {
	if pid <= 0 || uid < 10000 || uid != a.AppUID || !cleanSHA256(a.ApprovedAPK_SHA256) ||
		!filepath.IsAbs(a.ApprovedAPKPath) || filepath.Clean(a.ApprovedAPKPath) != a.ApprovedAPKPath ||
		!strings.HasPrefix(a.ApprovedAPKPath, "/data/app/") || !strings.HasSuffix(a.ApprovedAPKPath, "/base.apk") ||
		strings.Contains(a.ApprovedAPKPath, "/../") {
		return ErrUnverified
	}
	// Android's package manager maintains system-owned installed APKs. An app
	// cannot authorize itself by supplying another path at request time.
	return verifyAuthorityAPKBytes(ctx, a.ApprovedAPKPath, a.ApprovedAPK_SHA256)
}

// verifyAuthorityAPKBytes is separated solely for owned-file fixture tests;
// VerifyAuthorityProcess always enforces the production /data/app/ location.
func verifyAuthorityAPKBytes(ctx context.Context, path, wantSHA string) error {
	if !cleanSHA256(wantSHA) {
		return ErrUnverified
	}
	st, e := os.Lstat(path)
	if e != nil || !st.Mode().IsRegular() || st.Mode()&os.ModeSymlink != 0 || st.Mode().Perm()&0022 != 0 || st.Size() < 1024 || st.Size() > 200<<20 {
		return ErrUnverified
	}
	raw, ok := st.Sys().(*syscall.Stat_t)
	if !ok || (raw.Uid != 0 && raw.Uid != 1000) || raw.Nlink != 1 {
		return ErrUnverified
	}
	f, e := os.Open(path)
	if e != nil {
		return ErrUnverified
	}
	defer f.Close()
	opened, e := f.Stat()
	if e != nil || !os.SameFile(st, opened) {
		return ErrUnverified
	}
	h := sha256.New()
	n, e := io.Copy(h, io.LimitReader(f, 200<<20+1))
	if e != nil || n != st.Size() || ctx.Err() != nil {
		return ErrUnverified
	}
	after, e := os.Lstat(path)
	if e != nil || !os.SameFile(st, after) || !st.ModTime().Equal(after.ModTime()) {
		return ErrUnverified
	}
	expected, _ := hex.DecodeString(wantSHA)
	if subtle.ConstantTimeCompare(expected, h.Sum(nil)) != 1 {
		return ErrUnverified
	}
	return nil
}

var _ AuthorityAnchor = AuthorityAPKAnchor{}
