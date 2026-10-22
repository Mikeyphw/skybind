package main

// A single explicit root-operator command coordinates a real AndroidJUnit
// instrumentation running INSIDE the independently attested BKX app process.
// The coordinator is temporary; only fixed case names are accepted, clients
// cannot choose grant scopes, and neither tokens nor Android stdout are logged.
import (
	"bufio"
	"bytes"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"skybind/internal/brokeripc"
	"skybind/internal/brokerruntime"
)

const bkxAcceptanceEndpoint = "\x00skybind-r1-bkx-device-acceptance-v1"
const bkxTestComponent = "com.mikeyphw.bkx.android.test/androidx.test.runner.AndroidJUnitRunner"
const bkxTestClass = "com.mikeyphw.bkx.android.r1.SkybindR1LiveBrokerAcceptanceTest"

var bkxCaseOrder = []string{
	"no_token", "positive_capabilities", "positive_version", "positive_remotes", "positive_list", "positive_size",
	"wrong_operation", "wrong_remote", "wrong_path", "wrong_process", "revocation", "expiry",
}

type bkxCaseResult struct {
	State    string `json:"state"`
	Evidence string `json:"evidence"`
	Reason   string `json:"reason,omitempty"`
}
type bkxDeviceReceipt struct {
	Schema                      string                   `json:"schema"`
	State                       string                   `json:"state"`
	CapturedUTC                 string                   `json:"captured_utc"`
	Remote                      string                   `json:"remote"`
	Cases                       map[string]bkxCaseResult `json:"cases"`
	SocketPeerAttested          bool                     `json:"socket_peer_attested"`
	InstrumentationTerminalPass bool                     `json:"instrumentation_terminal_pass"`
	BKXNegativeSocketQualified  bool                     `json:"bkx_negative_socket_qualified"`
	ExternalProviderQualified   bool                     `json:"external_provider_qualified"`
	ReleaseQualified            bool                     `json:"release_qualified"`
	Receipt                     string                   `json:"receipt,omitempty"`
}
type bkxWire struct {
	Action string `json:"action"`
	Case   string `json:"case,omitempty"`
	State  string `json:"state,omitempty"`
}
type bkxReply struct {
	OK     bool   `json:"ok"`
	Remote string `json:"remote,omitempty"`
	Path   string `json:"path,omitempty"`
}

func bkxCaseOperation(name string) string {
	switch name {
	case "positive_capabilities", "wrong_operation", "wrong_remote", "wrong_path", "wrong_process", "revocation", "expiry":
		return "system.capabilities"
	case "positive_version":
		return "rclone.version"
	case "positive_remotes":
		return "rclone.listremotes"
	case "positive_list":
		return "rclone.lsjson"
	case "positive_size":
		return "rclone.size"
	default:
		return ""
	}
}
func bkxDenied(reason string) bkxCaseResult {
	return bkxCaseResult{State: "BLOCKED", Evidence: "bkx_installed_app_abstract_unix_socket", Reason: reason}
}
func bkxPassed() bkxCaseResult {
	return bkxCaseResult{State: "PASS", Evidence: "bkx_installed_app_abstract_unix_socket"}
}
func bkxPolicyScope(policy brokerruntime.Policy, remote, path string) (string, error) {
	if !validAcceptanceRemote(remote) || len(path) > 4096 || strings.HasPrefix(path, "/") || strings.ContainsAny(path, "\\:%?#\x00\n\r") {
		return "", errors.New("invalid_remote_or_path")
	}
	if path != "" {
		for _, v := range strings.Split(path, "/") {
			if v == "" || v == "." || v == ".." {
				return "", errors.New("unsafe_path")
			}
		}
	}
	for _, rule := range policy.Rules {
		if rule.Consumer != "bkx" || rule.Remote != remote {
			continue
		}
		if path != rule.Prefix && rule.Prefix != "" && !strings.HasPrefix(path, rule.Prefix+"/") {
			continue
		}
		all := true
		for _, name := range bkxCaseOrder {
			op := bkxCaseOperation(name)
			if op == "" {
				continue
			}
			found := false
			for _, approved := range rule.Operations {
				if approved == op {
					found = true
					break
				}
			}
			if !found {
				all = false
				break
			}
		}
		if all {
			return rule.Prefix, nil
		}
	}
	return "", errors.New("bkx_policy_operations_or_path_not_approved")
}

// The wire contains case labels and results only, never grant bytes. A fixed
// order blocks a client from using the coordinator as a generic issuance API.
func bkxServeControl(ctx context.Context, c *net.UnixConn, g *brokerruntime.Gateway, h *brokerruntime.GrantHandoff, policy brokerruntime.Policy, remote, prefix, path string, r *bkxDeviceReceipt) error {
	defer c.Close()
	peer, err := brokeripc.PeerCredentials(c)
	if err != nil || peer.UID != policy.BKX.UID || peer.GID != policy.BKX.UID {
		return errors.New("bkx_peer_credentials_denied")
	}
	pinned, err := g.Verifier.VerifyPeer(peer)
	if err != nil || pinned.UID != peer.UID || pinned.ProcessKey == "" {
		return errors.New("bkx_peer_not_attested")
	}
	r.SocketPeerAttested = true
	reader := bufio.NewReaderSize(io.LimitReader(c, 8192), 4096)
	writer := bufio.NewWriter(c)
	send := func(reply bkxReply) error {
		_ = c.SetWriteDeadline(time.Now().Add(5 * time.Second))
		b, _ := json.Marshal(reply)
		if _, e := writer.Write(append(b, '\n')); e != nil {
			return e
		}
		return writer.Flush()
	}
	read := func() (bkxWire, error) {
		_ = c.SetReadDeadline(time.Now().Add(18 * time.Second))
		raw, e := reader.ReadBytes('\n')
		if e != nil || len(raw) > 512 {
			return bkxWire{}, errors.New("control_frame_missing_or_oversized")
		}
		var w bkxWire
		d := json.NewDecoder(bytes.NewReader(raw))
		d.DisallowUnknownFields()
		if d.Decode(&w) != nil || d.Decode(new(any)) != io.EOF {
			return bkxWire{}, errors.New("control_frame_invalid")
		}
		current, e := g.Verifier.VerifyPeer(peer)
		if e != nil || current != pinned {
			return bkxWire{}, errors.New("bkx_peer_identity_changed")
		}
		if ctx.Err() != nil {
			return bkxWire{}, errors.New("campaign_cancelled")
		}
		return w, nil
	}
	_ = c.SetWriteDeadline(time.Now().Add(5 * time.Second))
	hello, e := read()
	if e != nil || hello.Action != "hello" || hello.Case != "" || hello.State != "" {
		return errors.New("bkx_handshake_denied")
	}
	if send(bkxReply{OK: true, Remote: remote, Path: path}) != nil {
		return errors.New("bkx_handshake_reply_failed")
	}
	receipts := map[string]struct{}{}
	defer func() {
		for id := range receipts {
			h.RevokeIssued(id)
		}
	}()
	for _, name := range bkxCaseOrder {
		step, e := read()
		if e != nil || step.Action != "prepare" || step.Case != name || step.State != "" {
			r.Cases[name] = bkxDenied("missing_or_unordered_step")
			return errors.New("bkx_step_not_authenticated")
		}
		if name != "no_token" {
			before := map[string]bool{}
			for _, id := range h.IssuedReceiptIDs() {
				before[id] = true
			}
			ttl := 45 * time.Second
			if name == "expiry" {
				ttl = 2 * time.Second
			}
			e = h.Approve(peer, brokerruntime.HandoffRequest{Consumer: "bkx", Remote: remote, Prefix: prefix, Operations: []string{bkxCaseOperation(name)}, TTL: ttl})
			if e != nil {
				r.Cases[name] = bkxDenied("exact_process_grant_approval_denied")
				return e
			}
			if send(bkxReply{OK: true}) != nil {
				return errors.New("step_reply_failed")
			}
			if name == "revocation" {
				revoke, e := read()
				if e != nil || revoke.Action != "revoke" || revoke.Case != name {
					r.Cases[name] = bkxDenied("revocation_handshake_missing")
					return errors.New("bkx_revoke_ack_missing")
				}
				diag := h.Diagnostics()
				if diag.Delivered != 1 || diag.Rejections != 0 {
					r.Cases[name] = bkxDenied("grant_delivery_not_proven")
					return errors.New("grant_not_delivered")
				}
				fresh := []string{}
				for _, id := range h.IssuedReceiptIDs() {
					if !before[id] {
						fresh = append(fresh, id)
					}
				}
				if len(fresh) != 1 || !h.RevokeIssued(fresh[0]) {
					r.Cases[name] = bkxDenied("fresh_grant_revocation_failed")
					return errors.New("revoke_failed")
				}
				if send(bkxReply{OK: true}) != nil {
					return errors.New("revoke_reply_failed")
				}
			}
		} else if send(bkxReply{OK: true}) != nil {
			return errors.New("no_token_reply_failed")
		}
		completed, e := read()
		if e != nil || completed.Action != "result" || completed.Case != name || completed.State != "PASS" {
			r.Cases[name] = bkxDenied("client_socket_assertion_failed_or_missing")
			return errors.New("bkx_socket_assertion_missing")
		}
		if name != "no_token" {
			diag := h.Diagnostics()
			if diag.Delivered != 1 || diag.Rejections != 0 {
				r.Cases[name] = bkxDenied("handoff_diagnostics_not_clean")
				return errors.New("handoff_incomplete")
			}
			for _, id := range h.IssuedReceiptIDs() {
				receipts[id] = struct{}{}
			}
		}
		r.Cases[name] = bkxPassed()
		if send(bkxReply{OK: true}) != nil {
			return errors.New("result_ack_failed")
		}
	}
	bye, e := read()
	if e != nil || bye.Action != "done" {
		return errors.New("bkx_instrumentation_incomplete")
	}
	return send(bkxReply{OK: true})
}

func runBKXDeviceAcceptance(parent context.Context, g *brokerruntime.Gateway, h *brokerruntime.GrantHandoff, policy brokerruntime.Policy, remote, path string) bkxDeviceReceipt {
	r := bkxDeviceReceipt{Schema: "skybind-r1-bkx-device-acceptance-v1", State: "BLOCKED", CapturedUTC: time.Now().UTC().Format(time.RFC3339Nano), Remote: remote, Cases: map[string]bkxCaseResult{}, ExternalProviderQualified: false, ReleaseQualified: false}
	reason := ""
	prefix, e := bkxPolicyScope(policy, remote, path)
	if e != nil {
		reason = "operator_policy_scope_not_approved"
		goto finalize
	}
	if g == nil || h == nil {
		reason = "gateway_not_ready"
		goto finalize
	}
	{
		ctx, cancel := context.WithTimeout(parent, 150*time.Second)
		defer cancel()
		listener, err := net.ListenUnix("unix", &net.UnixAddr{Name: bkxAcceptanceEndpoint, Net: "unix"})
		if err != nil {
			reason = "test_coordination_socket_unavailable"
			goto finalize
		}
		defer listener.Close()
		// Android's instrumentation controller, not a shell-selected executable.
		cmd := exec.CommandContext(ctx, "/system/bin/am", "instrument", "-w", "-r", "-e", "class", bkxTestClass, bkxTestComponent)
		cmd.Env = []string{"PATH=/system/bin:/system/xbin", "HOME=/data/adb/skybind"}
		var output bytes.Buffer
		cmd.Stdout = &boundedBKXWriter{out: &output, limit: 65536}
		cmd.Stderr = io.Discard
		if err = cmd.Start(); err != nil {
			reason = "android_instrumentation_unavailable"
			goto finalize
		}
		_ = listener.SetDeadline(time.Now().Add(30 * time.Second))
		conn, err := listener.AcceptUnix()
		if err != nil {
			reason = "bkx_test_process_did_not_connect"
			_ = cmd.Process.Kill()
			_ = cmd.Wait()
			goto finalize
		}
		err = bkxServeControl(ctx, conn, g, h, policy, remote, prefix, path, &r)
		if err != nil {
			_ = cmd.Process.Kill()
		}
		waitErr := cmd.Wait()
		if err != nil {
			reason = "bkx_control_or_socket_assertion_failed"
			goto finalize
		}
		// The test sends the final success only after all socket assertions. Android's
		// terminal instrumentation code is separately required; no marker = BLOCKED.
		if waitErr != nil || !bytes.Contains(output.Bytes(), []byte("INSTRUMENTATION_CODE: -1")) || bytes.Contains(output.Bytes(), []byte("FAILURES!!!")) {
			reason = "android_instrumentation_terminal_not_pass"
			goto finalize
		}
		r.InstrumentationTerminalPass = true
		if len(r.Cases) != len(bkxCaseOrder) {
			reason = "cases_incomplete"
			goto finalize
		}
		for _, name := range bkxCaseOrder {
			if r.Cases[name].State != "PASS" {
				reason = "socket_case_not_pass"
				goto finalize
			}
		}
		r.State = "PASS_R1_BKX_LIVE_SOCKET_ACCEPTANCE_ONLY"
		r.BKXNegativeSocketQualified = true
	}
finalize:
	if reason != "" {
		r.Cases["campaign"] = bkxDenied(reason)
	}
	// Keep a separate BKX receipt family: the existing chrootctl collector
	// must never accidentally classify this report as its 9-case chroot result.
	if err := persistBKXAcceptance(&r); err != nil {
		r.State = "BLOCKED"
		r.BKXNegativeSocketQualified = false
		r.Cases["receipt_persistence"] = bkxDenied("root_private_receipt_not_saved")
	}
	return r
}

func persistBKXAcceptance(r *bkxDeviceReceipt) error {
	parent := "/data/adb/skybind"
	st, err := os.Lstat(parent)
	if err != nil || !st.IsDir() || st.Mode().Perm() != 0700 || st.Mode()&os.ModeSymlink != 0 || !ownedByRoot(st) {
		return errors.New("unsafe_state_parent")
	}
	dir := filepath.Join(parent, "r1-bkx-acceptance")
	if e := os.Mkdir(dir, 0700); e != nil && !os.IsExist(e) {
		return errors.New("bkx_receipt_directory_unavailable")
	}
	st, err = os.Lstat(dir)
	if err != nil || !st.IsDir() || st.Mode().Perm() != 0700 || st.Mode()&os.ModeSymlink != 0 || !ownedByRoot(st) {
		return errors.New("bkx_receipt_directory_unsafe")
	}
	random := make([]byte, 16)
	if _, err = rand.Read(random); err != nil {
		return errors.New("bkx_receipt_random_failed")
	}
	path := filepath.Join(dir, "r1-bkx-"+hex.EncodeToString(random)+".json")
	r.Receipt = path
	body, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return err
	}
	f, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0600)
	if err != nil {
		return errors.New("bkx_receipt_create_denied")
	}
	_, err = f.Write(append(body, '\n'))
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil || closeErr != nil {
		_ = os.Remove(path)
		return errors.New("bkx_receipt_write_failed")
	}
	return nil
}

type boundedBKXWriter struct {
	out   *bytes.Buffer
	limit int
}

func (b *boundedBKXWriter) Write(p []byte) (int, error) {
	if len(p) > b.limit {
		return 0, errors.New("instrumentation_output_exceeds_limit")
	}
	n, e := b.out.Write(p)
	b.limit -= n
	return n, e
}
