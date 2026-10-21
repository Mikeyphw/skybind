package main

import (
	"errors"
	"net"
	"skybind/internal/brokeridentity"
	"testing"
)

func TestExplicitAuthorityDiagnosticFailureKinds(t *testing.T) {
	tests := []struct {
		err  error
		want string
	}{
		{brokeridentity.ErrPMBridgePeerLabelMismatch, "AUTHORITY_PEER_SELINUX_MISMATCH"},
		{&net.OpError{Op: "accept", Net: "unix", Err: timeoutErr{}}, "AUTHORITY_CONNECTION_TIMEOUT"},
		{errors.New("unverified_identity"), "AUTHORITY_PEER_NOT_ATTESTED"},
	}
	for _, tc := range tests {
		if got := classifyAuthorityAcceptError(tc.err); got != tc.want {
			t.Errorf("got %s want %s", got, tc.want)
		}
	}
}

type timeoutErr struct{}

func (timeoutErr) Error() string   { return "timeout" }
func (timeoutErr) Timeout() bool   { return true }
func (timeoutErr) Temporary() bool { return true }
