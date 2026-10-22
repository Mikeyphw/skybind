package main

// Explicit, root-operator-only R1 security acceptance. Real socket negatives
// use the installed chrootctl client. Revocation/expiry use the SAME live
// broker grant store, but are accurately labelled in-process rather than
// misleadingly described as external client replay tests.
import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	"skybind/internal/brokergrant"
	"skybind/internal/brokerruntime"
)

const acceptanceChrootctl = "/data/adb/modules/chrootctl/runtime/arm64-v8a/chrootctl"
const acceptanceDir = "/data/adb/skybind/r1-security-acceptance"

type acceptanceCase struct {
	State    string `json:"state"`
	Evidence string `json:"evidence"`
	Reason   string `json:"reason,omitempty"`
}
type securityAcceptance struct {
	Schema                     string                    `json:"schema"`
	State                      string                    `json:"state"`
	CapturedUTC                string                    `json:"captured_utc"`
	Remote                     string                    `json:"remote"`
	Prefix                     string                    `json:"prefix"`
	Cases                      map[string]acceptanceCase `json:"cases"`
	GrantsIssued               bool                      `json:"grants_issued"`
	ExternalProviderQualified  bool                      `json:"external_provider_qualified"`
	BKXNegativeSocketQualified bool                      `json:"bkx_negative_socket_qualified"`
	ReleaseQualified           bool                      `json:"release_qualified"`
	Receipt                    string                    `json:"receipt,omitempty"`
}

func acceptanceCaseResult(ok bool, evidence, reason string) acceptanceCase {
	if ok {
		return acceptanceCase{State: "PASS", Evidence: evidence}
	}
	if reason == "" {
		reason = "evidence_not_established"
	}
	return acceptanceCase{State: "BLOCKED", Evidence: evidence, Reason: reason}
}

func alternateRemote(remote string) string {
	// Same client-side syntax as the approved name; guaranteed distinct.
	candidate := remote + "_R1denied"
	if len(candidate) > 63 {
		candidate = remote[:53] + "_R1denied"
	}
	return candidate
}

// Live process is created by the trusted root operator using ONLY the fixed,
// installed module executable. No shell, flags from consumers or alternate
// executables are allowed. Result bytes are bounded, no tokens are printed.
func runAcceptanceSocketCase(ctx context.Context, g *brokerruntime.Gateway, h *brokerruntime.GrantHandoff, operation, requestedRemote, approvedRemote, prefix string, expectSuccess bool) acceptanceCase {
	evidence := "installed_chrootctl_real_abstract_unix_socket"
	cctx, cancel := context.WithTimeout(ctx, 25*time.Second)
	defer cancel()
	cmd := exec.CommandContext(cctx, acceptanceChrootctl, "skybind-read", "--operation", operation, "--remote", requestedRemote, "--path", prefix)
	var stdout, stderr bytes.Buffer
	cmd.Stdout, cmd.Stderr = &stdout, &stderr
	if e := cmd.Start(); e != nil {
		return acceptanceCaseResult(false, evidence, "installed_client_start_failed")
	}
	peer, e := readPeer(int32(cmd.Process.Pid))
	if e == nil && (peer.UID != 0 || peer.GID != 0) {
		e = errors.New("client_not_root")
	}
	if e == nil {
		e = h.Approve(peer, brokerruntime.HandoffRequest{Consumer: "chrootctl", Remote: approvedRemote, Prefix: prefix, Operations: []string{"system.capabilities"}, TTL: 25 * time.Second})
	}
	if e != nil {
		_ = cmd.Process.Kill()
		_ = cmd.Wait()
		return acceptanceCaseResult(false, evidence, "operator_offer_or_process_attestation_failed")
	}
	e = cmd.Wait()
	d := h.Diagnostics()
	if cctx.Err() != nil {
		return acceptanceCaseResult(false, evidence, "client_timeout")
	}
	if d.Delivered != 1 || d.OfferPending {
		return acceptanceCaseResult(false, evidence, "grant_not_delivered")
	}
	if stdout.Len() > 16384 || stderr.Len() > 16384 {
		return acceptanceCaseResult(false, evidence, "client_response_oversize")
	}
	if expectSuccess {
		if e != nil {
			return acceptanceCaseResult(false, evidence, "approved_client_read_failed")
		}
		var result struct {
			Schema     string   `json:"schema"`
			Version    int      `json:"version"`
			ReadOnly   bool     `json:"read_only"`
			Operations []string `json:"operations"`
		}
		if json.Unmarshal(bytes.TrimSpace(stdout.Bytes()), &result) != nil || result.Schema != "skybind-r1-metadata-v1" || result.Version != 1 || !result.ReadOnly || len(result.Operations) != 5 {
			return acceptanceCaseResult(false, evidence, "metadata_schema_not_verified")
		}
		return acceptanceCaseResult(true, evidence, "")
	}
	// chrootctl intentionally returns 2 for a denied read. A grant MUST have
	// been delivered first, otherwise this is only a transport failure.
	var exit *exec.ExitError
	if !errors.As(e, &exit) || exit.ExitCode() != 2 {
		return acceptanceCaseResult(false, evidence, "cross_scope_request_was_not_denied")
	}
	if !strings.Contains(stderr.String(), "chrootctl skybind-read: read unavailable or denied") {
		return acceptanceCaseResult(false, evidence, "denial_response_not_observed")
	}
	return acceptanceCaseResult(true, evidence, "")
}

// Authenticate an actual installed module process, then use the production
// Store's Authorize/Revoke/expiry semantics. Do NOT send test-only tokens to an
// external socket; no token is stored in a receipt or operator terminal.
func runAcceptanceStoreCases(ctx context.Context, g *brokerruntime.Gateway, remote, prefix string) map[string]acceptanceCase {
	evidence := "attested_installed_chrootctl_production_grant_store"
	out := map[string]acceptanceCase{}
	names := []string{"operation_isolation_store", "remote_isolation_store", "wrong_peer_store", "no_token_store", "revocation_store", "expiry_store"}
	blockAll := func(reason string) map[string]acceptanceCase {
		for _, n := range names {
			out[n] = acceptanceCaseResult(false, evidence, reason)
		}
		return out
	}
	cctx, cancel := context.WithTimeout(ctx, 20*time.Second)
	defer cancel()
	cmd := exec.CommandContext(cctx, acceptanceChrootctl, "skybind-read", "--operation", "system.capabilities", "--remote", remote, "--path", prefix)
	// It waits for a separate handoff, which we intentionally never approve.
	cmd.Stdout, cmd.Stderr = &bytes.Buffer{}, &bytes.Buffer{}
	if err := cmd.Start(); err != nil {
		return blockAll("installed_client_start_failed")
	}
	defer func() { _ = cmd.Process.Kill(); _ = cmd.Wait() }()
	peer, e := readPeer(int32(cmd.Process.Pid))
	if e != nil || peer.UID != 0 || peer.GID != 0 {
		return blockAll("root_process_not_observed")
	}
	identity, e := g.Verifier.VerifyPeer(peer)
	if e != nil || identity.ProcessKey == "" {
		return blockAll("installed_process_reverification_failed")
	}
	token, receipt, e := g.IssueApproved(peer, "chrootctl", remote, prefix, []string{"system.capabilities"}, 10*time.Second)
	if e != nil {
		return blockAll("least_privilege_grant_issuance_failed")
	}
	defer g.Revoke(receipt.ID)
	out["operation_isolation_store"] = acceptanceCaseResult(g.Grants.Authorize(token, identity, "rclone.lsjson", remote, prefix) != nil, evidence, "unapproved_operation_accepted")
	out["remote_isolation_store"] = acceptanceCaseResult(g.Grants.Authorize(token, identity, "system.capabilities", alternateRemote(remote), prefix) != nil, evidence, "unapproved_remote_accepted")
	wrong := brokergrant.Identity{UID: identity.UID, ProcessKey: strings.Repeat("0", 64)}
	if wrong == identity {
		wrong.ProcessKey = strings.Repeat("1", 64)
	}
	out["wrong_peer_store"] = acceptanceCaseResult(g.Grants.Authorize(token, wrong, "system.capabilities", remote, prefix) != nil, evidence, "wrong_process_accepted")
	out["no_token_store"] = acceptanceCaseResult(g.Grants.Authorize(strings.Repeat("0", 64), identity, "system.capabilities", remote, prefix) != nil, evidence, "absent_token_accepted")
	allowedBefore := g.Grants.Authorize(token, identity, "system.capabilities", remote, prefix) == nil
	revoked := g.Revoke(receipt.ID)
	deniedAfter := g.Grants.Authorize(token, identity, "system.capabilities", remote, prefix) != nil
	out["revocation_store"] = acceptanceCaseResult(allowedBefore && revoked && deniedAfter, evidence, "revocation_did_not_invalidate_active_token")
	expToken, expReceipt, expErr := g.IssueApproved(peer, "chrootctl", remote, prefix, []string{"system.capabilities"}, 5*time.Second)
	if expErr != nil {
		out["expiry_store"] = acceptanceCaseResult(false, evidence, "short_grant_not_issued")
		return out
	}
	defer g.Revoke(expReceipt.ID)
	validBefore := g.Grants.Authorize(expToken, identity, "system.capabilities", remote, prefix) == nil
	time.Sleep(5250 * time.Millisecond)
	expired := g.Grants.Authorize(expToken, identity, "system.capabilities", remote, prefix) != nil
	out["expiry_store"] = acceptanceCaseResult(validBefore && expired, evidence, "expired_token_not_denied")
	return out
}

func persistSecurityAcceptance(r *securityAcceptance) error {
	// Canonical root-owned directory and private receipt. Any unsafe existing
	// parent/leaf fails closed. The result remains in the operator terminal
	// even when persistent evidence cannot be saved.
	parent := "/data/adb/skybind"
	info, e := os.Lstat(parent)
	if e != nil || !info.IsDir() || info.Mode().Perm() != 0700 || info.Mode()&os.ModeSymlink != 0 || !ownedByRoot(info) {
		return errors.New("unsafe_state_parent")
	}
	if e = os.Mkdir(acceptanceDir, 0700); e != nil && !os.IsExist(e) {
		return errors.New("receipt_directory_unavailable")
	}
	info, e = os.Lstat(acceptanceDir)
	if e != nil || !info.IsDir() || info.Mode().Perm() != 0700 || info.Mode()&os.ModeSymlink != 0 || !ownedByRoot(info) {
		return errors.New("unsafe_receipt_directory")
	}
	randBytes := make([]byte, 16)
	if _, e = rand.Read(randBytes); e != nil {
		return errors.New("receipt_random_failed")
	}
	name := "r1-security-" + hex.EncodeToString(randBytes) + ".json"
	path := filepath.Join(acceptanceDir, name)
	r.Receipt = path
	raw, e := json.MarshalIndent(r, "", "  ")
	if e != nil {
		return e
	}
	f, e := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if e != nil {
		return errors.New("receipt_create_denied")
	}
	_, e = f.Write(append(raw, '\n'))
	if e == nil {
		e = f.Sync()
	}
	ce := f.Close()
	if e != nil || ce != nil {
		_ = os.Remove(path)
		return errors.New("receipt_write_failed")
	}
	return nil
}

func runSecurityAcceptance(ctx context.Context, g *brokerruntime.Gateway, h *brokerruntime.GrantHandoff, policy brokerruntime.Policy, remote string) securityAcceptance {
	r := securityAcceptance{Schema: "skybind-r1-security-acceptance-v1", State: "BLOCKED", CapturedUTC: time.Now().UTC().Format(time.RFC3339Nano), Remote: remote, Cases: map[string]acceptanceCase{}, ExternalProviderQualified: false, BKXNegativeSocketQualified: false, ReleaseQualified: false}
	if ctx.Err() != nil || g == nil || h == nil || !validAcceptanceRemote(remote) {
		r.Cases["precondition"] = acceptanceCaseResult(false, "root_operator", "invalid_request")
		return r
	}
	matched := false
	for _, rule := range policy.Rules {
		if rule.Consumer != "chrootctl" || rule.Remote != remote {
			continue
		}
		for _, op := range rule.Operations {
			if op == "system.capabilities" {
				r.Prefix = rule.Prefix
				matched = true
				break
			}
		}
	}
	if !matched {
		r.Cases["precondition"] = acceptanceCaseResult(false, "root_operator", "remote_or_capability_not_approved")
		return r
	}
	r.Cases["positive_live_socket"] = runAcceptanceSocketCase(ctx, g, h, "system.capabilities", remote, remote, r.Prefix, true)
	if r.Cases["positive_live_socket"].State == "PASS" {
		r.Cases["wrong_operation_live_socket"] = runAcceptanceSocketCase(ctx, g, h, "rclone.lsjson", remote, remote, r.Prefix, false)
		r.Cases["wrong_remote_live_socket"] = runAcceptanceSocketCase(ctx, g, h, "system.capabilities", alternateRemote(remote), remote, r.Prefix, false)
	} else {
		for _, n := range []string{"wrong_operation_live_socket", "wrong_remote_live_socket"} {
			r.Cases[n] = acceptanceCaseResult(false, "installed_chrootctl_real_abstract_unix_socket", "positive_transport_precondition_failed")
		}
	}
	for name, result := range runAcceptanceStoreCases(ctx, g, remote, r.Prefix) {
		r.Cases[name] = result
	}
	all := len(r.Cases) == 9
	for _, v := range r.Cases {
		if v.State != "PASS" {
			all = false
		}
	}
	if all {
		r.State = "PASS_R1_CHROOTCTL_SECURITY_ACCEPTANCE_ONLY"
	}
	// In-process grants are issued/revoked; NEVER claim zero issuance.
	r.GrantsIssued = r.Cases["positive_live_socket"].State == "PASS" || r.Cases["operation_isolation_store"].State == "PASS" || r.Cases["revocation_store"].State == "PASS" || r.Cases["expiry_store"].State == "PASS"
	if e := persistSecurityAcceptance(&r); e != nil {
		r.Cases["evidence_persistence"] = acceptanceCaseResult(false, "root_private_device_json", e.Error())
		r.State = "BLOCKED"
		r.Receipt = ""
	}
	return r
}

func validAcceptanceRemote(remote string) bool {
	if len(remote) < 1 || len(remote) > 63 || remote[0] < 'A' && remote[0] < 'a' {
		return false
	}
	for i, c := range remote {
		if i == 0 && !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z')) {
			return false
		}
		if !((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '_' || c == '-') {
			return false
		}
	}
	return true
}

func ownedByRoot(info os.FileInfo) bool {
	s, ok := info.Sys().(*syscall.Stat_t)
	return ok && s.Uid == 0
}
