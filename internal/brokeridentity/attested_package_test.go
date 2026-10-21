package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"testing"
)

type pmAuthority struct {
	record PlatformPackageRecord
	err    error
}

func (p pmAuthority) LookupInstalled(_ context.Context, _ uint32, _ string) (PlatformPackageRecord, error) {
	return p.record, p.err
}
func TestTrustedPlatformSigningAndExactUID(t *testing.T) {
	cert := []byte(strings.Repeat("A", 512))
	dig := sha256.Sum256(cert)
	pin := PackagePin{Name: "com.mikeyphw.bkx.android", CertSHA256: hex.EncodeToString(dig[:]), SELinuxContext: "u:r:untrusted_app:s0:c123,c456"}
	ok := PlatformPackageRecord{UID: 10327, PackagesForUID: []string{pin.Name}, InstalledPackage: pin.Name, APKContentsSigners: [][]byte{cert}, IsInstalledForUser: true}
	if err := (PlatformPackageAttestor{Authority: pmAuthority{record: ok}}).Verify(context.Background(), 10327, pin); err != nil {
		t.Fatal(err)
	}
	cases := []struct {
		name   string
		change func(*PlatformPackageRecord)
	}{
		{"shared-uid", func(x *PlatformPackageRecord) { x.PackagesForUID = append(x.PackagesForUID, "org.attacker") }},
		{"uid", func(x *PlatformPackageRecord) { x.UID++ }},
		{"renamed", func(x *PlatformPackageRecord) { x.InstalledPackage = "org.attacker" }},
		{"uninstalled", func(x *PlatformPackageRecord) { x.IsInstalledForUser = false }},
		{"missing-signing", func(x *PlatformPackageRecord) { x.APKContentsSigners = nil }},
		{"multiple-signing", func(x *PlatformPackageRecord) { x.APKContentsSigners = append(x.APKContentsSigners, cert) }},
		{"rotated-signing", func(x *PlatformPackageRecord) { x.APKContentsSigners = [][]byte{[]byte(strings.Repeat("B", 512))} }},
		{"short-signing", func(x *PlatformPackageRecord) { x.APKContentsSigners = [][]byte{{1}} }},
		{"bad-history", func(x *PlatformPackageRecord) { x.SigningHistory = [][]byte{{1}} }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			v := ok
			tc.change(&v)
			if err := (PlatformPackageAttestor{Authority: pmAuthority{record: v}}).Verify(context.Background(), 10327, pin); err == nil {
				t.Fatal("unauthorized identity accepted")
			}
		})
	}
	if (PlatformPackageAttestor{}).Verify(context.Background(), 10327, pin) == nil {
		t.Fatal("missing platform authority")
	}
	if (PlatformPackageAttestor{Authority: pmAuthority{record: ok, err: errors.New("offline")}}).Verify(context.Background(), 10327, pin) == nil {
		t.Fatal("authority error ignored")
	}

}
