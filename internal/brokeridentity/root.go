package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"

	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
)

// ModulePin names an explicitly approved root-module workload, not just a
// file in /data/adb/modules or an untrusted process command-line argument.
// A consumer can update independently, but a changed installed module seal
// requires fresh administrator approval/attestation, not a Skybind rebuild.
type ModulePin struct {
	Name             string
	ModuleSealSHA256 string
	SELinuxContext   string
}

// ModuleAttestor MUST be implemented by an independent trusted runtime
// authority that binds this exact PID/instance to the sealed executable and
// module identity. No self-attestation or UID=0-only acceptance is permitted.
type ModuleAttestor interface {
	VerifyModuleProcess(ctx context.Context, pid int32, pin ModulePin) error
}

// RootVerifier is an R1 source-only verifier for the chrootctl root workload.
// It is NOT attached to any production listener and has no implicit grants.
// The AndroidVerifier continues to serve app-UID BKX identities separately.
type RootVerifier struct {
	Pin     ModulePin
	Proc    ProcReader
	Modules ModuleAttestor
}

func cleanModulePin(pin ModulePin) bool {
	if pin.Name != "chrootctl" || !cleanSHA256(pin.ModuleSealSHA256) ||
		len(pin.SELinuxContext) < 8 || len(pin.SELinuxContext) > 192 ||
		!strings.HasPrefix(pin.SELinuxContext, "u:r:") ||
		strings.ContainsAny(pin.SELinuxContext, "\r\n\x00\t") {
		return false
	}
	return true
}

func cleanSHA256(d string) bool {
	if len(d) != 64 {
		return false
	}
	for _, r := range d {
		if !((r >= '0' && r <= '9') || (r >= 'a' && r <= 'f')) {
			return false
		}
	}
	return true
}

func (v *RootVerifier) VerifyPeer(peer brokeripc.KernelPeer) (brokergrant.Identity, error) {
	if v == nil || v.Proc == nil || v.Modules == nil ||
		peer.PID <= 0 || peer.UID != 0 || peer.GID != 0 || !cleanModulePin(v.Pin) {
		return brokergrant.Identity{}, ErrUnverified
	}
	// Snapshot kernel-owned start time, four effective/saved/fs UID fields,
	// and SELinux context on both sides of the independent module attestation.
	snapshot := func() (uint64, error) {
		stat, err := v.Proc.Read(peer.PID, "stat")
		if err != nil {
			return 0, ErrUnverified
		}
		ticks, err := parseStartTicks(stat, peer.PID)
		if err != nil {
			return 0, ErrUnverified
		}
		status, err := v.Proc.Read(peer.PID, "status")
		if err != nil {
			return 0, ErrUnverified
		}
		uid, err := parseStatusUID(status)
		if err != nil || uid != 0 {
			return 0, ErrUnverified
		}
		label, err := v.Proc.Read(peer.PID, "attr/current")
		observedLabel, labelErr := procSELinuxLabel(label)
		if err != nil || labelErr != nil || observedLabel != v.Pin.SELinuxContext {
			return 0, ErrUnverified
		}
		return ticks, nil
	}
	before, err := snapshot()
	if err != nil {
		return brokergrant.Identity{}, ErrUnverified
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	if err = v.Modules.VerifyModuleProcess(ctx, peer.PID, v.Pin); err != nil {
		return brokergrant.Identity{}, ErrUnverified
	}
	after, err := snapshot()
	if err != nil || before != after {
		return brokergrant.Identity{}, ErrUnverified
	}
	key := sha256.Sum256([]byte(fmt.Sprintf("skybind-r1-module-v1\x00%d\x00%d\x00%d\x00%s\x00%s\x00%s",
		peer.UID, peer.PID, before, v.Pin.Name, v.Pin.ModuleSealSHA256, v.Pin.SELinuxContext)))
	return brokergrant.Identity{UID: peer.UID, ProcessKey: hex.EncodeToString(key[:])}, nil
}

var _ brokeripc.Verifier = (*RootVerifier)(nil)
