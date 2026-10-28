package featuregateway

// Separate from the API-04 query guard. Mutation admission requires BOTH the
// existing verified Android identity and an independent root-operator approval.
import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"skybind/internal/brokergrant"
	"skybind/internal/brokeripc"
	"skybind/internal/featureapi"
	"skybind/internal/protocol"
	"time"
)

type MutationCall struct {
	Version   int    `json:"version"`
	Action    string `json:"action"` // preview | execute | status
	RequestID string `json:"request_id,omitempty"`
	Operation string `json:"operation,omitempty"`
	Name      string `json:"name,omitempty"`
	PreviewID string `json:"preview_id,omitempty"`
}
type MutationResult struct {
	PreviewID string `json:"preview_id"`
	RequestID string `json:"request_id,omitempty"`
	Operation string `json:"operation,omitempty"`
	Name      string `json:"name,omitempty"`
	Digest    string `json:"preview_sha256,omitempty"`
	Expires   int64  `json:"expires_unix,omitempty"`
	State     string `json:"state"`
}
type MutationService struct {
	Guard    *Guard
	Policy   MutationPolicy
	Store    *MutationStore
	Dispatch Dispatch
}

func NewMutationService(g *Guard, p MutationPolicy, store *MutationStore, dispatch Dispatch) (*MutationService, error) {
	if g == nil || p.Validate(g.policy) != nil || store == nil || dispatch == nil {
		return nil, errors.New("api04_mutation_not_authorized")
	}
	return &MutationService{Guard: g, Policy: p, Store: store, Dispatch: dispatch}, nil
}
func validClientRequestID(s string) bool {
	if len(s) < 1 || len(s) > 80 {
		return false
	}
	for _, r := range s {
		if !(r >= 'A' && r <= 'Z' || r >= 'a' && r <= 'z' || r >= '0' && r <= '9' || r == '_' || r == '-') {
			return false
		}
	}
	return true
}
func DecodeMutationCall(data []byte) (MutationCall, error) {
	var c MutationCall
	if len(data) == 0 || len(data) > protocol.MaxEnvelope || rejectDuplicateKeys(data) != nil || protocol.StrictBytes(data, &c) != nil || c.Version != 1 {
		return MutationCall{}, errors.New("api04_mutation_request_invalid")
	}
	switch c.Action {
	case "preview":
		if !validClientRequestID(c.RequestID) || !mutationAllow[c.Operation] || !mountName.MatchString(c.Name) || c.PreviewID != "" {
			return MutationCall{}, errors.New("api04_mutation_preview_invalid")
		}
	case "execute", "status":
		if !validMutationID(c.PreviewID) || c.RequestID != "" || c.Operation != "" || c.Name != "" {
			return MutationCall{}, errors.New("api04_mutation_request_invalid")
		}
	default:
		return MutationCall{}, errors.New("api04_mutation_action_denied")
	}
	return c, nil
}
func (s *MutationService) verify(peer brokeripc.KernelPeer) (brokergrant.Identity, error) {
	if s == nil || s.Guard == nil || peer.PID <= 0 || peer.UID != s.Guard.policy.BKX.UID || peer.UID < 10000 || peer.GID == 0 {
		return brokergrant.Identity{}, errors.New("api04_mutation_peer_denied")
	}
	id, e := s.Guard.verifier.VerifyPeer(peer)
	if e != nil || id.UID != peer.UID || id.ProcessKey == "" {
		return brokergrant.Identity{}, errors.New("api04_mutation_identity_denied")
	}
	return id, nil
}

// featureCall reuses API-02's private feature.execute and validates BOTH
// protocol envelopes; direct daemon socket addresses are never supplied by a client.
func (s *MutationService) featureCall(ctx context.Context, reqID, op string, args any) (protocol.Response, error) {
	cls, ok := featureapi.ClassFor(op)
	if !ok {
		return protocol.Response{}, errors.New("api04_mutation_operation_denied")
	}
	raw, e := json.Marshal(args)
	if e != nil {
		return protocol.Response{}, e
	}
	call := featureapi.Call{APIVersion: featureapi.Version, Operation: op, RequestID: reqID, Arguments: raw}
	wrapped, e := json.Marshal(call)
	if e != nil {
		return protocol.Response{}, e
	}
	request := protocol.Request{SchemaVersion: protocol.Version, RequestID: reqID, Operation: "feature.execute", Class: protocol.Query, Arguments: wrapped}
	outer, e := s.Dispatch(ctx, request)
	if e != nil || outer.SchemaVersion != protocol.Version || outer.RequestID != reqID || !outer.OK {
		return protocol.Response{}, errors.New("api04_mutation_daemon_unavailable")
	}
	inside, e := json.Marshal(outer.Result)
	if e != nil || len(inside) > protocol.MaxResponse {
		return protocol.Response{}, errors.New("api04_mutation_daemon_reply_invalid")
	}
	var inner protocol.Response
	if protocol.StrictBytes(inside, &inner) != nil || inner.SchemaVersion != protocol.Version || inner.RequestID != reqID {
		return protocol.Response{}, errors.New("api04_mutation_daemon_reply_invalid")
	}
	if inner.Error != nil && inner.OK {
		return protocol.Response{}, errors.New("api04_mutation_daemon_reply_invalid")
	}
	if cls == protocol.Preview && !inner.OK {
		return protocol.Response{}, errors.New("api04_mutation_preview_rejected")
	}
	return inner, nil
}

// nativeMutationOperation maps API04's narrow public operation to its distinct
// proof-gated daemon operation. Never use API02's legacy unguarded mount.stop.
func nativeMutationOperation(op string) string {
	if op == "mount.stop" {
		return "mount.stop.guarded"
	}
	return op
}

func (s *MutationService) Process(ctx context.Context, peer brokeripc.KernelPeer, call MutationCall) (MutationResult, error) {
	var empty MutationResult
	id, e := s.verify(peer)
	if e != nil {
		return empty, e
	}
	switch call.Action {
	case "preview":
		if !s.Policy.Allows(call.Operation, call.Name) || !s.Guard.policy.AllowsMount(call.Name) {
			return empty, errors.New("api04_mutation_scope_denied")
		}
		previewID, e := newMutationID()
		if e != nil {
			return empty, e
		}
		nativeID := "api04_" + previewID
		op := "mount.start.preview"
		if call.Operation == "mount.stop" {
			op = "mount.stop.preview"
		}
		previewReq := "preview_" + previewID
		inner, e := s.featureCall(ctx, previewReq, op, map[string]string{"name": call.Name})
		if e != nil || !inner.OK {
			return empty, errors.New("api04_mutation_preview_unavailable")
		}
		proof := ""
		if call.Operation == "mount.start" || call.Operation == "mount.stop" {
			b, e := json.Marshal(inner.Result)
			if e != nil || len(b) > protocol.MaxResponse {
				return empty, errors.New("api04_mutation_proof_invalid")
			}
			// API02 preview replies contain additional descriptive metadata.
			// Decode as an object, then require precisely one typed proof field;
			// don't reject valid native previews for containing mount metadata.
			var fields map[string]json.RawMessage
			if protocol.StrictBytes(b, &fields) != nil || fields == nil {
				return empty, errors.New("api04_mutation_proof_invalid")
			}
			if json.Unmarshal(fields["proof"], &proof) != nil || len(proof) != 64 {
				return empty, errors.New("api04_mutation_proof_invalid")
			}
			for _, ch := range proof {
				if !(ch >= '0' && ch <= '9' || ch >= 'a' && ch <= 'f') {
					return empty, errors.New("api04_mutation_proof_invalid")
				}
			}
		}
		issued := time.Now().Unix()
		rec := MutationRecord{ID: previewID, RequestID: call.RequestID, NativeID: nativeID, Operation: call.Operation, Mount: call.Name,
			CallerUID: peer.UID, ProcessKey: id.ProcessKey, Issued: issued, Expires: issued + int64(mutationTTL/time.Second), NativeProof: proof, State: "previewed"}
		rec.Digest = mutationDigest(rec)
		if e = s.Store.add(rec); e != nil {
			return empty, errors.New("api04_mutation_store_unavailable")
		}
		return MutationResult{PreviewID: rec.ID, RequestID: call.RequestID, Operation: rec.Operation, Name: rec.Mount, Digest: rec.Digest, Expires: rec.Expires, State: "awaiting_root_approval"}, nil
	case "execute":
		existing, e := s.Store.get(call.PreviewID)
		if e != nil || existing.CallerUID != peer.UID || !s.Policy.Allows(existing.Operation, existing.Mount) || !s.Guard.policy.AllowsMount(existing.Mount) {
			return empty, errors.New("api04_mutation_record_denied")
		}
		rec, e := s.Store.reserve(call.PreviewID, id.ProcessKey, peer.UID)
		if e != nil {
			return empty, errors.New("api04_mutation_not_approved")
		}
		// Submitted is durable before the first daemon invocation. Unknown
		// outcomes are NEVER replayed by this API, even after a crash/restart.
		args := map[string]string{"name": rec.Mount}
		// Both mutations must carry a native single-use proof. Never reach
		// API02's original root-only unguarded mount.stop from API04.
		if rec.NativeProof == "" {
			return empty, errors.New("api04_mutation_native_proof_missing")
		}
		args["proof"] = rec.NativeProof
		inner, e := s.featureCall(ctx, rec.NativeID, nativeMutationOperation(rec.Operation), args)
		state := "unknown"
		if e == nil {
			if inner.OK {
				state = "succeeded"
			} else {
				state = "failed"
			}
		}
		if err := s.Store.SetOutcome(rec.ID, state); err != nil {
			return empty, errors.New("api04_mutation_outcome_unpersisted")
		}
		// Verify the same process incarnation after crossing the daemon trust boundary.
		again, verifyErr := s.verify(peer)
		if verifyErr != nil || again != id {
			return empty, errors.New("api04_mutation_identity_changed")
		}
		return MutationResult{PreviewID: rec.ID, RequestID: rec.RequestID, Operation: rec.Operation, Name: rec.Mount, State: state}, nil
	case "status":
		rec, e := s.Store.get(call.PreviewID)
		if e != nil || rec.CallerUID != peer.UID || !s.Policy.Allows(rec.Operation, rec.Mount) || !s.Guard.policy.AllowsMount(rec.Mount) {
			return empty, errors.New("api04_mutation_record_denied")
		}
		state := rec.State
		if state == "previewed" || state == "approved" {
			if time.Now().Unix() >= rec.Expires {
				state = "expired"
			}
		}
		if state == "submitted" || state == "unknown" {
			// Read only the precise native operation by its server-issued ID;
			// never expose global operation history or daemon journal contents.
			lookupID, err := newMutationID()
			if err != nil {
				return empty, err
			}
			inner, err := s.featureCall(ctx, "status_"+lookupID, "operation.status", map[string]string{"id": rec.NativeID})
			if err == nil && inner.OK {
				raw, _ := json.Marshal(inner.Result)
				var found struct {
					RequestID string `json:"request_id"`
					State     string `json:"state"`
					Action    string `json:"action"`
				}
				if json.Unmarshal(raw, &found) == nil && found.RequestID == rec.NativeID && found.Action == nativeMutationOperation(rec.Operation) {
					switch found.State {
					case "succeeded", "failed", "interrupted", "cancelled", "running":
						state = found.State
					}
				}
			}
			if state == "submitted" {
				state = "unknown"
			}
		}
		return MutationResult{PreviewID: rec.ID, RequestID: rec.RequestID, Operation: rec.Operation, Name: rec.Mount, State: state}, nil
	}
	return empty, fmt.Errorf("api04_mutation_unknown_action")
}
