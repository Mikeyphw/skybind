package featuregateway

import (
	"bytes"
	"encoding/json"
	"errors"
	"skybind/internal/brokergrant"
	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
	"skybind/internal/featureapi"
	"skybind/internal/protocol"
)

// Dependencies can only provide independent kernel/Android package authorities.
// A caller-supplied JSON certificate, executable name or claimed UID is never
// accepted as a replacement for the Android PackageManager/proc evidence.
type Dependencies struct {
	Packages brokeridentity.PackageAuthority
	Proc     brokeridentity.ProcReader
}

type Guard struct {
	policy   Policy
	verifier brokeridentity.AndroidVerifier
}

func NewGuard(policy Policy, deps Dependencies) (*Guard, error) {
	if err := policy.Validate(); err != nil {
		return nil, err
	}
	if deps.Packages == nil || deps.Proc == nil {
		return nil, errors.New("api04_trusted_identity_authority_missing")
	}
	v := brokeridentity.AndroidVerifier{
		Pins:     map[uint32]brokeridentity.PackagePin{policy.BKX.UID: policy.PackagePin()},
		Packages: brokeridentity.PlatformPackageAttestor{Authority: deps.Packages},
		Proc:     deps.Proc,
	}
	return &Guard{policy: policy, verifier: v}, nil
}

// Prepare is a narrowly scoped, fail-closed admission check; it does not
// execute features or create sockets/grants. The peer must come from the kernel
// SO_PEERCRED observer in the future operator-enabled API-04 transport.
// The resulting API-02 daemon request is a *read-only* feature.execute query.
func (g *Guard) Prepare(peer brokeripc.KernelPeer, body []byte) (protocol.Request, brokergrant.Identity, error) {
	empty := protocol.Request{}
	denied := brokergrant.Identity{}
	if g == nil || peer.UID < 10000 || peer.UID != g.policy.BKX.UID || peer.PID <= 0 || peer.GID == 0 {
		return empty, denied, errors.New("api04_peer_denied")
	}
	identity, err := g.verifier.VerifyPeer(peer)
	if err != nil || identity.UID != peer.UID || identity.ProcessKey == "" {
		return empty, denied, errors.New("api04_identity_unverified")
	}
	call, err := featureapi.DecodeCall(bytes.NewReader(body))
	if err != nil {
		return empty, denied, errors.New("api04_invalid_request")
	}
	if !g.policy.Allows(call.Operation) {
		return empty, denied, errors.New("api04_operation_denied")
	}
	// The policy also pins each query to a specific configured mount. API-02
	// daemon's strict decoder rejects unknown members, while featureapi has
	// already rejected duplicate keys and ambiguous nested JSON.
	var args struct {
		Name string `json:"name"`
	}
	if err := protocol.StrictBytes(call.Arguments, &args); err != nil || !g.policy.AllowsMount(args.Name) {
		return empty, denied, errors.New("api04_mount_scope_denied")
	}
	// Safe only as a prepared, typed query: this package has NO listener or
	// transport, and does not call a root daemon. The next phase must securely
	// bind this very checked peer to the root-owned API-02 daemon connection.
	wrapped, err := json.Marshal(call)
	if err != nil {
		return empty, denied, errors.New("api04_encoding_failed")
	}
	return protocol.Request{SchemaVersion: protocol.Version, RequestID: call.RequestID,
		Operation: "feature.execute", Class: protocol.Query, Arguments: wrapped}, identity, nil
}
