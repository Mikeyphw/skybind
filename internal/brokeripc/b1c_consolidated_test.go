package brokeripc

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"skybind/internal/brokergrant"
)

func TestB1C5RejectDuplicateAndAmbiguousJSONFields(t *testing.T) {
	cases := []string{
		`{"version":1,"token":"abc","token":"def","operation":"rclone.version","remote":"drive","path":""}`,
		`{"version":1,"version":1,"token":"a"}`,
		`{"version":1,"operation":"rclone.version","operation":"rclone.deletefile"}`,
		`{"version":1,"remote":"drive","remote":"other"}`,
		`{"version":1,"path":"","path":"other"}`,
		`{"version":1,"remote":{"name":"drive"}}`,
		`{"version":1} {"version":1}`,
		`[ {"version":1} ]`,
	}
	for _, raw := range cases {
		t.Run(raw, func(t *testing.T) {
			if _, err := parseRequest([]byte(raw)); err == nil {
				t.Fatal("accepted ambiguous request")
			}
		})
	}
	good := `{"version":1,"token":"abc","operation":"rclone.version","remote":"drive","path":""}`
	if _, err := parseRequest([]byte(good)); err != nil {
		t.Fatal(err)
	}
}

type transitionVerifier struct {
	count    atomic.Int32
	identity brokergrant.Identity
}

func (v *transitionVerifier) VerifyPeer(_ KernelPeer) (brokergrant.Identity, error) {
	if v.count.Add(1) >= 3 {
		return brokergrant.Identity{}, errors.New("revoked_identity")
	}
	return v.identity, nil
}

func TestB1C5ThirdPeerVerificationPreventsBackendRead(t *testing.T) {
	identity := brokergrant.Identity{UID: uint32(os.Getuid()), ProcessKey: "uid-pid-cert-verified"}
	grants := brokergrant.New()
	token, _, err := grants.Issue(brokergrant.GrantSpec{Caller: identity, Remote: "drive", Operations: []string{"rclone.version"}, TTL: time.Minute})
	if err != nil {
		t.Fatal(err)
	}
	var reads atomic.Int32
	verifier := &transitionVerifier{identity: identity}
	server := &Server{Grants: grants, Verifier: verifier, Read: func(Request) (json.RawMessage, error) { reads.Add(1); return json.RawMessage(`{}`), nil }}
	req := `{"version":1,"token":"` + token + `","operation":"rclone.version","remote":"drive","path":""}`
	response, err := roundTrip(t, server, req)
	if err == nil || response.OK || reads.Load() != 0 || verifier.count.Load() != 3 {
		t.Fatalf("failed closed incorrectly: %+v %v calls=%d", response, err, verifier.count.Load())
	}
	// The same grant must not permit any payload with duplicate fields.
	verifier.count.Store(0)
	dup := strings.Replace(req, `"operation":"rclone.version"`, `"operation":"rclone.version","operation":"rclone.version"`, 1)
	response, err = roundTrip(t, server, dup)
	if err == nil || response.OK || reads.Load() != 0 {
		t.Fatal("duplicate JSON reached backend")
	}
}
