package brokerruntime

import (
	"errors"
	"time"

	"skybind/internal/brokergrant"
	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
	"skybind/internal/brokerissue"
)

// PlatformAuthority MUST be backed by an authenticated Android PackageManager
// request/response channel. A caller-created JSON record is not acceptable.
// Until that trusted bridge exists, no production Gateway can be assembled.
type Dependencies struct {
	PlatformAuthority brokeridentity.PackageAuthority
	Proc              brokeridentity.ProcReader
	ModuleAuthority   brokeridentity.ModuleAttestor
	Backend           brokeripc.Reader
}
type Gateway struct {
	socket   *brokeripc.ConsumerSocket
	Verifier brokeridentity.ConsumerVerifier
	Grants   *brokergrant.Store
	policy   Policy
}

func Assemble(policy Policy, deps Dependencies) (*Gateway, error) {
	if e := policy.Validate(); e != nil {
		return nil, e
	}
	if deps.PlatformAuthority == nil || deps.Proc == nil || deps.ModuleAuthority == nil || deps.Backend == nil {
		return nil, errors.New("r1_trusted_authorities_not_connected")
	}
	// The installed module attestor is canonical in production. Dependency
	// injection exists only for isolated and explicitly approved device tests.
	bkx := &brokeridentity.AndroidVerifier{Pins: map[uint32]brokeridentity.PackagePin{policy.BKX.UID: policy.PackagePin()}, Packages: brokeridentity.PlatformPackageAttestor{Authority: deps.PlatformAuthority}, Proc: deps.Proc}
	chroot := &brokeridentity.RootVerifier{Pin: policy.ModulePin(), Proc: deps.Proc, Modules: deps.ModuleAuthority}
	verifier := brokeridentity.ConsumerVerifier{BKXUID: policy.BKX.UID, BKX: bkx, Chrootctl: chroot}
	grants := brokergrant.New()
	socket := &brokeripc.ConsumerSocket{Directory: "/data/adb/skybind/consumer-gateway", BKXUID: policy.BKX.UID, ExplicitlyEnabled: true, Grants: grants, Verifier: verifier, Backend: deps.Backend}
	return &Gateway{socket: socket, Verifier: verifier, Grants: grants, policy: policy}, nil
}

// Start is never invoked by the ordinary daemon; only a separately qualified
// operator-controlled runtime may start the listener after trusted linkage.
func (g *Gateway) Start() error {
	if g == nil || g.socket == nil {
		return errors.New("r1_gateway_unconfigured")
	}
	return g.socket.Start()
}
func (g *Gateway) Close() error {
	if g == nil || g.socket == nil {
		return nil
	}
	return g.socket.Close()
}

// IssueApproved grants only the exact policy scope to an independently
// verified, currently active peer. This function is NOT an IPC endpoint;
// callers must be privileged, explicitly authorized operator control planes.
// Tokens are never persisted or logged by this package.
func (g *Gateway) IssueApproved(peer brokeripc.KernelPeer, consumer, remote, prefix string, ops []string, ttl time.Duration) (string, brokergrant.GrantReceipt, error) {
	if g == nil || ttl <= 0 || ttl > MaxGrantTTL {
		return "", brokergrant.GrantReceipt{}, errors.New("r1_operator_approval_required")
	}
	if consumer == "bkx" && peer.UID != g.policy.BKX.UID {
		return "", brokergrant.GrantReceipt{}, errors.New("r1_wrong_app_uid")
	}
	if consumer == "chrootctl" && peer.UID != 0 {
		return "", brokergrant.GrantReceipt{}, errors.New("r1_wrong_module_uid")
	}
	identity, e := g.Verifier.VerifyPeer(peer)
	if e != nil {
		return "", brokergrant.GrantReceipt{}, errors.New("r1_unattested_peer")
	}
	rules := make([]brokerissue.Rule, 0, 1)
	for _, r := range g.policy.Rules {
		if r.Consumer == consumer {
			rules = append(rules, brokerissue.Rule{Caller: identity, Remote: r.Remote, Prefix: r.Prefix, Operations: r.Operations, MaxTTL: MaxGrantTTL})
		}
	}
	issuer := brokerissue.Issuer{Grants: g.Grants, Verifier: g.Verifier, Rules: rules}
	return issuer.IssueForPeer(peer, brokerissue.Request{Remote: remote, Prefix: prefix, Operations: ops, TTL: ttl})
}
func (g *Gateway) Revoke(id string) bool { return g != nil && g.Grants != nil && g.Grants.Revoke(id) }
