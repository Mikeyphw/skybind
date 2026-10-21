// Package brokeridentity validates Android IPC peer identities against a
// trusted platform package attestor and the current kernel process instance.
// This package does NOT implement the privileged Android PackageManager bridge;
// until an operator provisions that bridge, every external caller is denied.
package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
)

var ErrUnverified = errors.New("android_peer_unverified")

// PackagePin is an operator-approved identity, never one supplied in RPC JSON.
// CertSHA256 is the SHA-256 digest of the Android APK signing certificate.
type PackagePin struct {
	Name       string
	CertSHA256 string
	// SELinuxContext is measured for this Android app process on this device.
	// It must be operator-approved, never taken from a request field.
	SELinuxContext string
}

// PackageAttestor is a trusted platform-side Android PackageManager authority.
// Verify must establish that UID owns exactly the pinned package, with an
// allowed signing lineage and no additional packages sharing the UID.
// Self-reported package names, adb output, app-supplied signatures, and
// /proc/cmdline are not acceptable implementations.
type PackageAttestor interface {
	Verify(ctx context.Context, uid uint32, pin PackagePin) error
}

// ProcReader supports minimal, testable kernel process identity snapshots.
type ProcReader interface {
	Read(pid int32, filename string) ([]byte, error)
}
type LinuxProc struct{ Root string }

func (p LinuxProc) Read(pid int32, filename string) ([]byte, error) {
	if pid <= 0 || (filename != "stat" && filename != "status" && filename != "attr/current") {
		return nil, ErrUnverified
	}
	root := p.Root
	if root == "" {
		root = "/proc"
	}
	return os.ReadFile(filepath.Join(root, strconv.FormatInt(int64(pid), 10), filename))
}

type AndroidVerifier struct {
	// Pins is an explicit UID-to-package/certificate allowlist. No UID fallback.
	Pins     map[uint32]PackagePin
	Packages PackageAttestor
	Proc     ProcReader
}

// parseStartTicks identifies Linux /proc/PID/stat field 22, accounting for
// embedded spaces and closing parentheses in the process command name.
func parseStartTicks(data []byte, pid int32) (uint64, error) {
	s := strings.TrimSpace(string(data))
	i := strings.LastIndex(s, ")")
	if i < 1 || !strings.Contains(s[:i], "(") {
		return 0, ErrUnverified
	}
	if strings.TrimSpace(s[:strings.Index(s, "(")]) != strconv.FormatInt(int64(pid), 10) {
		return 0, ErrUnverified
	}
	f := strings.Fields(strings.TrimSpace(s[i+1:]))
	// f[0] is field 3 (state), f[19] is field 22 (starttime).
	if len(f) < 20 || len(f[0]) != 1 {
		return 0, ErrUnverified
	}
	ticks, e := strconv.ParseUint(f[19], 10, 64)
	if e != nil || ticks == 0 {
		return 0, ErrUnverified
	}
	return ticks, nil
}
func parseStatusUID(data []byte) (uint32, error) {
	seen := false
	var uid uint32
	for _, line := range strings.Split(string(data), "\n") {
		if !strings.HasPrefix(line, "Uid:") {
			continue
		}
		if seen {
			return 0, ErrUnverified
		}
		seen = true
		fields := strings.Fields(strings.TrimSpace(strings.TrimPrefix(line, "Uid:")))
		if len(fields) != 4 {
			return 0, ErrUnverified
		}
		a, e := strconv.ParseUint(fields[0], 10, 32)
		if e != nil {
			return 0, ErrUnverified
		}
		for _, s := range fields[1:] {
			v, e := strconv.ParseUint(s, 10, 32)
			if e != nil || v != a {
				return 0, ErrUnverified
			}
		}
		uid = uint32(a)
	}
	if !seen {
		return 0, ErrUnverified
	}
	return uid, nil
}
func cleanPin(pin PackagePin) bool {
	if len(pin.Name) < 3 || len(pin.Name) > 255 || strings.HasPrefix(pin.Name, ".") || strings.HasSuffix(pin.Name, ".") || !strings.Contains(pin.Name, ".") || strings.Contains(pin.Name, "..") {
		return false
	}
	for _, r := range pin.Name {
		if !(r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r >= '0' && r <= '9' || r == '.' || r == '_') {
			return false
		}
	}
	if len(pin.SELinuxContext) < 8 || len(pin.SELinuxContext) > 192 ||
		!strings.HasPrefix(pin.SELinuxContext, "u:r:") || strings.ContainsAny(pin.SELinuxContext, "\r\n\x00\t") {
		return false
	}
	if len(pin.CertSHA256) != 64 {
		return false
	}
	for _, r := range pin.CertSHA256 {
		if !(r >= '0' && r <= '9' || r >= 'a' && r <= 'f') {
			return false
		}
	}
	return true
}
func (v *AndroidVerifier) VerifyPeer(peer brokeripc.KernelPeer) (brokergrant.Identity, error) {
	if v == nil || v.Proc == nil || v.Packages == nil || peer.PID <= 0 || peer.UID < 10000 || peer.GID == 0 {
		return brokergrant.Identity{}, ErrUnverified
	}
	pin, ok := v.Pins[peer.UID]
	if !ok || !cleanPin(pin) {
		return brokergrant.Identity{}, ErrUnverified
	}
	// Snapshot before and after platform attestation. PID reuse and unexpected
	// changes to UID/start-time invalidate the entire authentication attempt.
	readSnapshot := func() (uint64, error) {
		a, e := v.Proc.Read(peer.PID, "stat")
		if e != nil {
			return 0, ErrUnverified
		}
		ticks, e := parseStartTicks(a, peer.PID)
		if e != nil {
			return 0, ErrUnverified
		}
		b, e := v.Proc.Read(peer.PID, "status")
		if e != nil {
			return 0, ErrUnverified
		}
		uid, e := parseStatusUID(b)
		if e != nil || uid != peer.UID {
			return 0, ErrUnverified
		}
		label, e := v.Proc.Read(peer.PID, "attr/current")
		observedLabel, labelErr := procSELinuxLabel(label)
		if e != nil || labelErr != nil || observedLabel != pin.SELinuxContext {
			return 0, ErrUnverified
		}
		return ticks, nil
	}
	first, e := readSnapshot()
	if e != nil {
		return brokergrant.Identity{}, e
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if e = v.Packages.Verify(ctx, peer.UID, pin); e != nil {
		return brokergrant.Identity{}, ErrUnverified
	}
	second, e := readSnapshot()
	if e != nil || first != second {
		return brokergrant.Identity{}, ErrUnverified
	}
	// Binds every grant to an individual process incarnation and authenticated
	// package certificate, rather than UID alone or a caller-supplied string.
	sum := sha256.Sum256([]byte(fmt.Sprintf("skybind-r1-android-v2\x00%d\x00%d\x00%d\x00%s\x00%s\x00%s", peer.UID, peer.PID, first, pin.Name, pin.CertSHA256, pin.SELinuxContext)))
	return brokergrant.Identity{UID: peer.UID, ProcessKey: hex.EncodeToString(sum[:])}, nil
}
