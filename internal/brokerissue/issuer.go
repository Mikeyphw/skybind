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

// operationsWithinRule accepts only a nonempty, nonduplicated subset of an
// operator-owned policy rule. A narrower request must NEVER inherit the other
// operations from that rule when the grant is minted.
func operationsWithinRule(approved, requested []string) bool {
	if len(approved) == 0 || len(requested) == 0 || len(requested) > len(approved) {
		return false
	}
	allowed := make(map[string]bool, len(approved))
	for _, op := range approved {
		if op == "" || allowed[op] {
			return false
		}
		allowed[op] = true
	}
	seen := make(map[string]bool, len(requested))
	for _, op := range requested {
		if !allowed[op] || seen[op] {
			return false
		}
		seen[op] = true
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
		if rule.Caller != identity || rule.Remote != req.Remote || rule.Prefix != req.Prefix || rule.MaxTTL <= 0 || req.TTL <= 0 || req.TTL > rule.MaxTTL || !operationsWithinRule(rule.Operations, req.Operations) {
			continue
		}
		// Recheck the same process immediately before minting; a changed PID
		// incarnation or a vanished package invalidates approval.
		current, e := i.Verifier.VerifyPeer(peer)
		if e != nil || current != identity {
			return "", brokergrant.GrantReceipt{}, ErrDenied
		}
		token, receipt, e := i.Grants.Issue(brokergrant.GrantSpec{Caller: current, Remote: rule.Remote, Prefix: rule.Prefix, Operations: append([]string(nil), req.Operations...), TTL: req.TTL})
		if e != nil {
			return "", brokergrant.GrantReceipt{}, ErrDenied
		}
		return token, receipt, nil
	}
	return "", brokergrant.GrantReceipt{}, ErrDenied
}
