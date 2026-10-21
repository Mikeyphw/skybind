package brokerruntime

// One-shot, operator-authorized credential delivery to an exact verified
// process. A client cannot request a scope, mint a token, or select a PID.
// The separately operated root authority must explicitly Approve an active
// kernel peer; the recipient gets a scoped token only over its own SO_PEERCRED
// authenticated connection. No filesystem token, Android intent, or log.
import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"os"
	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
	"sync"
	"time"
)

const GrantHandoffEndpoint = "\x00skybind-r1-grant-handoff-v1"
const handoffTimeout = 30 * time.Second

type HandoffRequest struct {
	Consumer   string
	Remote     string
	Prefix     string
	Operations []string
	TTL        time.Duration
}

type pendingGrant struct {
	Peer     brokeripc.KernelPeer
	Identity brokergrant.Identity
	Request  HandoffRequest
	Expires  time.Time
}

type GrantHandoff struct {
	Gateway  *Gateway
	mu       sync.Mutex
	listener *net.UnixListener
	pending  *pendingGrant
	issued   map[string]time.Time
}

func (h *GrantHandoff) Start() error {
	if os.Geteuid() != 0 || h == nil || h.Gateway == nil || h.Gateway.Grants == nil || h.Gateway.Verifier.BKX == nil || h.Gateway.Verifier.Chrootctl == nil {
		return errors.New("r1_handoff_disabled")
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.listener != nil {
		return errors.New("r1_handoff_already_started")
	}
	l, e := net.ListenUnix("unix", &net.UnixAddr{Name: GrantHandoffEndpoint, Net: "unix"})
	if e != nil {
		return e
	}
	h.listener = l
	return nil
}

// Approve must be invoked from a privileged *local operator workflow*, never
// by a consumer-readable IPC method. It issues nothing and stores no token.
func (h *GrantHandoff) Approve(peer brokeripc.KernelPeer, req HandoffRequest) error {
	if os.Geteuid() != 0 || h == nil || h.Gateway == nil || peer.PID <= 0 || len(req.Operations) == 0 || req.TTL <= 0 || req.TTL > MaxGrantTTL ||
		(req.Consumer != "bkx" && req.Consumer != "chrootctl") {
		return errors.New("r1_operator_approval_required")
	}
	identity, e := h.Gateway.Verifier.VerifyPeer(peer)
	if e != nil || identity.ProcessKey == "" || identity.UID != peer.UID {
		return errors.New("r1_unverified_approval_subject")
	}
	// Validate against policy *before* accepting an offer, so there is never an
	// advertised scope beyond the root-owned maximum.
	allowed := false
	for _, rule := range h.Gateway.policy.Rules {
		if rule.Consumer != req.Consumer || rule.Remote != req.Remote || rule.Prefix != req.Prefix {
			continue
		}
		ok := true
		for _, operation := range req.Operations {
			found := false
			for _, o := range rule.Operations {
				if o == operation {
					found = true
					break
				}
			}
			if !found {
				ok = false
				break
			}
		}
		if ok {
			allowed = true
			break
		}
	}
	if !allowed {
		return errors.New("r1_handoff_scope_not_approved")
	}
	if (req.Consumer == "bkx" && peer.UID != h.Gateway.policy.BKX.UID) || (req.Consumer == "chrootctl" && peer.UID != 0) {
		return errors.New("r1_wrong_consumer_identity")
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.listener == nil || h.pending != nil {
		return errors.New("r1_handoff_not_ready")
	}
	h.pending = &pendingGrant{Peer: peer, Identity: identity, Request: req, Expires: time.Now().Add(handoffTimeout)}
	return nil
}

// serveOne refuses every unrelated kernel peer without consuming the offer.
// An expired offer is discarded; no token has been minted at that point.
func (h *GrantHandoff) serveOne(c *net.UnixConn) error {
	defer c.Close()
	_ = c.SetDeadline(time.Now().Add(5 * time.Second))
	peer, e := brokeripc.PeerCredentials(c)
	if e != nil {
		return errors.New("r1_handoff_peer_unavailable")
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	offer := h.pending
	if offer == nil {
		return errors.New("r1_handoff_no_approval")
	}
	if time.Now().After(offer.Expires) {
		h.pending = nil
		return errors.New("r1_handoff_approval_expired")
	}
	if peer != offer.Peer {
		return errors.New("r1_handoff_wrong_process")
	}
	verified, e := h.Gateway.Verifier.VerifyPeer(peer)
	if e != nil || verified != offer.Identity {
		return errors.New("r1_handoff_identity_changed")
	}
	// Keep the operator's receipt IDs, never tokens, for immediate revocation.
	for id, expiry := range h.issued {
		if !time.Now().Before(expiry) {
			delete(h.issued, id)
		}
	}
	if len(h.issued) >= 64 {
		return errors.New("r1_grant_receipt_capacity")
	}
	token, receipt, e := h.Gateway.IssueApproved(peer, offer.Request.Consumer, offer.Request.Remote, offer.Request.Prefix, offer.Request.Operations, offer.Request.TTL)
	if e != nil {
		return e
	}
	// Do not allow the same approval to issue twice, even if transmission fails.
	h.pending = nil
	if h.issued == nil {
		h.issued = make(map[string]time.Time)
	}
	h.issued[receipt.ID] = receipt.ExpiresAt
	packet, err := json.Marshal(struct {
		Version   int       `json:"version"`
		Token     string    `json:"token"`
		ExpiresAt time.Time `json:"expires_at"`
	}{1, token, receipt.ExpiresAt})
	if err != nil {
		h.Gateway.Revoke(receipt.ID)
		return err
	}
	packet = append(packet, '\n')
	n, err := c.Write(packet)
	if err != nil || n != len(packet) {
		h.Gateway.Revoke(receipt.ID)
		return errors.New("r1_handoff_write_failed")
	}
	return nil
}

func (h *GrantHandoff) Serve(ctx context.Context) error {
	if h == nil || ctx == nil {
		return errors.New("r1_handoff_disabled")
	}
	h.mu.Lock()
	l := h.listener
	h.mu.Unlock()
	if l == nil {
		return errors.New("r1_handoff_disabled")
	}
	end := make(chan struct{})
	go func() {
		select {
		case <-ctx.Done():
			_ = l.Close()
		case <-end:
		}
	}()
	defer close(end)
	for {
		c, e := l.AcceptUnix()
		if e != nil {
			if ctx.Err() != nil {
				return nil
			}
			return e
		}
		_ = h.serveOne(c)
	}
}
func (h *GrantHandoff) Close() error {
	if h == nil {
		return nil
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	h.pending = nil
	for id := range h.issued {
		h.Gateway.Revoke(id)
	}
	h.issued = nil
	if h.listener == nil {
		return nil
	}
	e := h.listener.Close()
	h.listener = nil
	return e
}

// RevokeIssued is only for the in-process root operator workflow; it neither
// opens a caller socket nor accepts untrusted consumer revocation messages.
func (h *GrantHandoff) RevokeIssued(id string) bool {
	if h == nil || h.Gateway == nil || os.Geteuid() != 0 {
		return false
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.issued[id]; !ok {
		return false
	}
	delete(h.issued, id)
	return h.Gateway.Revoke(id)
}
func (h *GrantHandoff) IssuedReceiptIDs() []string {
	if h == nil {
		return nil
	}
	h.mu.Lock()
	defer h.mu.Unlock()
	ids := make([]string, 0, len(h.issued))
	for id, expiry := range h.issued {
		if time.Now().Before(expiry) {
			ids = append(ids, id)
		}
	}
	return ids
}
