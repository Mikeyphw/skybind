package brokeridentity

import (
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
)

// PlatformPackageRecord is produced by the trusted Android PackageManager
// bridge, never from a broker client's JSON, CLI output or /proc/cmdline.
// Certificates are DER-encoded APK signing certificates authenticated by PM.
type PlatformPackageRecord struct {
	UID                uint32
	PackagesForUID     []string
	InstalledPackage   string
	APKContentsSigners [][]byte
	SigningHistory     [][]byte
	IsInstalledForUser bool
}

// PackageAuthority has to be an authenticated platform-side implementation.
// No authority is configured by default: a client cannot attest itself.
type PackageAuthority interface {
	LookupInstalled(ctx context.Context, uid uint32, packageName string) (PlatformPackageRecord, error)
}

// PlatformPackageAttestor verifies package ownership and approved signing key
// from trusted PackageManager observations. BKX's source/version are NOT pins.
// A changed signing key needs independent approval, not a Skybind rebuild.
type PlatformPackageAttestor struct{ Authority PackageAuthority }

func (p PlatformPackageAttestor) Verify(ctx context.Context, uid uint32, pin PackagePin) error {
	if p.Authority == nil || !cleanPin(pin) || uid < 10000 {
		return ErrUnverified
	}
	record, err := p.Authority.LookupInstalled(ctx, uid, pin.Name)
	if err != nil || !record.IsInstalledForUser || record.UID != uid ||
		record.InstalledPackage != pin.Name || len(record.PackagesForUID) != 1 ||
		record.PackagesForUID[0] != pin.Name || len(record.APKContentsSigners) != 1 ||
		len(record.SigningHistory) > 64 {
		return ErrUnverified
	}
	expected, err := hex.DecodeString(pin.CertSHA256)
	if err != nil || len(expected) != sha256.Size {
		return ErrUnverified
	}
	// Android PackageManager confirms the installed APK contents signer.
	// History may be retained for diagnostics but is NOT implicitly trusted:
	// accepting past keys requires an explicit rotation policy.
	current := record.APKContentsSigners[0]
	if len(current) < 64 || len(current) > 8192 {
		return ErrUnverified
	}
	actual := sha256.Sum256(current)
	if subtle.ConstantTimeCompare(actual[:], expected) != 1 {
		return ErrUnverified
	}
	for _, cert := range record.SigningHistory {
		if len(cert) < 64 || len(cert) > 8192 {
			return ErrUnverified
		}
	}
	return nil
}
