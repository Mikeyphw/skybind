package brokeridentity

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAuthorityAPKAnchorDeniesUnapprovedClaims(t *testing.T) {
	for _, a := range []AuthorityAPKAnchor{
		{}, {AppUID: 10335, ApprovedAPKPath: "/tmp/untrusted/base.apk", ApprovedAPK_SHA256: strings.Repeat("a", 64)},
		{AppUID: 10335, ApprovedAPKPath: "/data/app/../unsafe/base.apk", ApprovedAPK_SHA256: strings.Repeat("a", 64)},
		{AppUID: 10335, ApprovedAPKPath: "/data/app/pkg/base.apk", ApprovedAPK_SHA256: "bad"},
	} {
		if e := a.VerifyAuthorityProcess(context.Background(), 222, 10335); e == nil {
			t.Fatalf("accepted unsafe APK pin: %#v", a)
		}
	}
	if e := (AuthorityAPKAnchor{AppUID: 10335, ApprovedAPKPath: "/data/app/pkg/base.apk", ApprovedAPK_SHA256: strings.Repeat("a", 64)}).VerifyAuthorityProcess(context.Background(), 222, 10336); e == nil {
		t.Fatal("wrong UID accepted")
	}
}
func TestAuthorityAPKExactApprovedBytesAndMutation(t *testing.T) {
    // The production validator deliberately permits only root/system-owned APKs.
    // A GitHub ubuntu-runner or Termux UID cannot mint a valid trusted fixture.
    // GitHub separately executes this positive+mutation test under sudo and
    // asserts the test PASSED (not skipped) before publishing diagnostics.
    if os.Geteuid() != 0 {
        t.Skip("requires a root-owned APK fixture; CI executes under sudo")
    }
	dir := t.TempDir()
	path := filepath.Join(dir, "base.apk")
	raw := []byte(strings.Repeat("VALID-APK-FIXTURE-", 512))
	if e := os.WriteFile(path, raw, 0644); e != nil {
		t.Fatal(e)
	}
	sum := sha256.Sum256(raw)
	approved := hex.EncodeToString(sum[:])
	if e := verifyAuthorityAPKBytes(context.Background(), path, approved); e != nil {
		t.Fatal(e)
	}
	if e := verifyAuthorityAPKBytes(context.Background(), path, strings.Repeat("f", 64)); e == nil {
		t.Fatal("wrong seal accepted")
	}
	if e := os.WriteFile(path, []byte(strings.Repeat("changed", 300)), 0644); e != nil {
		t.Fatal(e)
	}
	if e := verifyAuthorityAPKBytes(context.Background(), path, approved); e == nil {
		t.Fatal("changed bytes accepted")
	}
	if e := os.Chmod(path, 0666); e != nil {
		t.Fatal(e)
	}
	if e := verifyAuthorityAPKBytes(context.Background(), path, approved); e == nil {
		t.Fatal("writable APK accepted")
	}
}

// An ordinary hosted or Termux process cannot manufacture the root/system APK
// ownership required by production, even when its fixture bytes and digest
// agree. This is an actual negative test, not a substituted positive claim.
func TestAuthorityAPKUnprivilegedOwnerIsRejected(t *testing.T) {
    if os.Geteuid() == 0 || os.Geteuid() == 1000 {
        t.Skip("requires a UID other than root/Android system; CI executes unprivileged lane")
    }
    path := filepath.Join(t.TempDir(), "base.apk")
    data := []byte(strings.Repeat("UNTRUSTED-OWNER-APK-", 512))
    if e := os.WriteFile(path, data, 0644); e != nil { t.Fatal(e) }
    sum := sha256.Sum256(data)
    if e := verifyAuthorityAPKBytes(context.Background(), path, hex.EncodeToString(sum[:])); e == nil {
        t.Fatal("accepted byte-matching APK owned by an untrusted app/CI user")
    }
}
