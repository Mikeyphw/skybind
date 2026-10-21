package brokeridentity

import (
	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
)

// ConsumerVerifier never aliases root and app identities. It does not grant
// access merely because a peer belongs to an otherwise approved UID.
type ConsumerVerifier struct {
	BKXUID    uint32
	BKX       *AndroidVerifier
	Chrootctl *RootVerifier
}

func (v ConsumerVerifier) VerifyPeer(peer brokeripc.KernelPeer) (brokergrant.Identity, error) {
	if peer.UID == 0 {
		if v.Chrootctl == nil {
			return brokergrant.Identity{}, ErrUnverified
		}
		return v.Chrootctl.VerifyPeer(peer)
	}
	if v.BKXUID < 10000 || peer.UID != v.BKXUID || v.BKX == nil {
		return brokergrant.Identity{}, ErrUnverified
	}
	return v.BKX.VerifyPeer(peer)
}

var _ brokeripc.Verifier = ConsumerVerifier{}
