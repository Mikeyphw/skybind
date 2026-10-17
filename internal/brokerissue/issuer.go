// Package brokerissue is an internal, non-RPC issuance control plane.
// It cannot be driven by untrusted broker requests. An operator-approved rule
// and current trusted kernel/process identity are required to mint a grant.
package brokerissue

import (
	"errors"
	"time"

	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
)

var ErrDenied = errors.New("broker_issuance_denied")

// Rule is provisioned by a trusted operator, never copied from an app request.
// Matching includes the exact process incarnation as returned by the verifier.
type Rule struct {
	Caller     brokergrant.Identity
	Remote     string
	Prefix     string
	Operations []string
	MaxTTL     time.Duration
}
type Issuer struct {
	Grants   *brokergrant.Store
	Verifier brokeripc.Verifier
	Rules    []Rule
}
type Request struct {
	Remote, Prefix string
	Operations     []string
	TTL            time.Duration
}

func operationsEqual(a, b []string) bool {
	if len(a) == 0 || len(a) != len(b) {
		return false
	}
	seen := make(map[string]int, len(a))
	for _, v := range a {
		seen[v]++
	}
	for _, v := range b {
		seen[v]--
		if seen[v] < 0 {
			return false
		}
	}
	for _, v := range seen {
		if v != 0 {
			return false
		}
	}
	return true
}

// IssueForPeer may be called only by a trusted, local control-plane entrypoint
// after explicit approval. It does not create an exposed IPC grant endpoint.
func (i *Issuer) IssueForPeer(peer brokeripc.KernelPeer, req Request) (string, brokergrant.GrantReceipt, error) {
	if i == nil || i.Grants == nil || i.Verifier == nil {
		return "", brokergrant.GrantReceipt{}, ErrDenied
	}
	identity, err := i.Verifier.VerifyPeer(peer)
	if err != nil || identity.ProcessKey == "" || identity.UID != peer.UID {
		return "", brokergrant.GrantReceipt{}, ErrDenied
	}
	for _, rule := range i.Rules {
		if rule.Caller != identity || rule.Remote != req.Remote || rule.Prefix != req.Prefix || rule.MaxTTL <= 0 || req.TTL <= 0 || req.TTL > rule.MaxTTL || !operationsEqual(rule.Operations, req.Operations) {
			continue
		}
		// Recheck the same process immediately before minting; a changed PID
		// incarnation or a vanished package invalidates approval.
		current, e := i.Verifier.VerifyPeer(peer)
		if e != nil || current != identity {
			return "", brokergrant.GrantReceipt{}, ErrDenied
		}
		token, receipt, e := i.Grants.Issue(brokergrant.GrantSpec{Caller: current, Remote: rule.Remote, Prefix: rule.Prefix, Operations: rule.Operations, TTL: req.TTL})
		if e != nil {
			return "", brokergrant.GrantReceipt{}, ErrDenied
		}
		return token, receipt, nil
	}
	return "", brokergrant.GrantReceipt{}, ErrDenied
}
