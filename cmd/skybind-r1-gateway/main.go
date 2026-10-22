// An explicit, interactive ROOT-OPERATOR diagnostic gateway. Never launched
// by the ordinary Skybind module; no grants or backup operations on startup.
package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
	"skybind/internal/brokerruntime"
	"strconv"
	"strings"
	"syscall"
	"time"
)

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "R1_OPERATOR_ROOT_REQUIRED")
		return 2
	}
	f := flag.NewFlagSet("skybind-r1-gateway", flag.ContinueOnError)
	policyPath := f.String("policy", brokerruntime.CanonicalPolicy, "root-owned policy path")
	uid := f.Uint("authority-uid", 0, "independently approved Skybind app UID")
	label := f.String("authority-context", "", "approved app SELinux context")
	apk := f.String("authority-apk", "", "approved canonical installed Skybind APK path")
	digest := f.String("authority-apk-sha256", "", "independently approved SHA256 of exact APK bytes")
	approved := f.Bool("operator-approve", false, "explicit manual R1 read-only gateway activation")
	if f.Parse(args) != nil || len(f.Args()) != 0 || !*approved || *uid < 10000 || *uid > 1<<31-1 {
		fmt.Fprintln(os.Stderr, "R1_OPERATOR_APPROVAL_REQUIRED")
		return 2
	}
	policy, e := brokerruntime.LoadAt(*policyPath)
	if e != nil {
		fmt.Fprintln(os.Stderr, "R1_OPERATOR_POLICY_DENIED")
		return 2
	}
	bridge := &brokeridentity.PMBridge{Pin: brokeridentity.AuthorityPeerPin{UID: uint32(*uid), SELinuxContext: *label}, Proc: brokeridentity.LinuxProc{},
		Anchor: brokeridentity.AuthorityAPKAnchor{AppUID: uint32(*uid), ApprovedAPKPath: *apk, ApprovedAPK_SHA256: *digest}}
	if e = bridge.Listen(); e != nil {
		fmt.Fprintln(os.Stderr, "R1_OPERATOR_BRIDGE_DENIED")
		return 2
	}
	defer bridge.Close()
	fmt.Fprintln(os.Stderr, "R1_AWAITING_SKYBIND_UI_AUTHORITY")
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer cancel()
	wait, wcancel := context.WithTimeout(ctx, 30*time.Second)
	e = bridge.Accept(wait)
	wcancel()
	if e != nil {
		fmt.Fprintln(os.Stderr, "R1_AUTHORITY_NOT_VERIFIED")
		return 2
	}
	g, e := brokerruntime.Assemble(policy, brokerruntime.Dependencies{PlatformAuthority: bridge, Proc: brokeridentity.LinuxProc{}, ModuleAuthority: brokeridentity.InstalledModuleAttestor{}, Backend: brokerruntime.ProductionMetadata().Read})
	if e != nil {
		fmt.Fprintln(os.Stderr, "R1_GATEWAY_ASSEMBLY_DENIED")
		return 2
	}
	if e = g.StartAbstract(); e != nil {
		fmt.Fprintln(os.Stderr, "R1_ABSTRACT_START_DENIED")
		return 2
	}
	defer g.CloseAbstract()
	handoff := &brokerruntime.GrantHandoff{Gateway: g}
	if e = handoff.Start(); e != nil {
		fmt.Fprintln(os.Stderr, "R1_HANDOFF_START_DENIED")
		return 2
	}
	defer handoff.Close()
	go func() { _ = g.ServeAbstract(ctx) }()
	go func() { _ = handoff.Serve(ctx) }()
	fmt.Fprintln(os.Stderr, "R1_OPERATOR_READY (interactive; no grants issued)")
	fmt.Fprintln(os.Stderr, "Commands: approve PID bkx|chrootctl REMOTE PREFIX|- OPERATION TTL_SECONDS ; diagnostics ; acceptance REMOTE ; receipts ; revoke RECEIPT_ID ; quit")
	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 4096), 4096)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) == 1 && fields[0] == "quit" {
			return 0
		}
		if len(fields) == 1 && fields[0] == "diagnostics" {
			// Display only bounded fixed-category counts to the authenticated
			// interactive root operator, never to a client or persistent log.
			payload, e := json.Marshal(handoff.Diagnostics())
			if e != nil {
				fmt.Fprintln(os.Stderr, "R1_HANDOFF_DIAGNOSTICS_UNAVAILABLE")
			} else {
				fmt.Fprintln(os.Stderr, "R1_HANDOFF_DIAGNOSTICS", string(payload))
			}
			continue
		}
		if len(fields) == 2 && fields[0] == "acceptance" {
			fmt.Fprintln(os.Stderr, "R1_SECURITY_ACCEPTANCE_STARTED (real module socket checks; grant-store checks; private JSON receipt)")
			result := runSecurityAcceptance(ctx, g, handoff, policy, fields[1])
			data, err := json.Marshal(result)
			if err != nil {
				fmt.Fprintln(os.Stderr, "R1_SECURITY_ACCEPTANCE_REPORT_FAILED")
			} else {
				fmt.Fprintln(os.Stderr, "R1_SECURITY_ACCEPTANCE", string(data))
			}
			continue
		}
		if len(fields) == 1 && fields[0] == "receipts" {
			for _, id := range handoff.IssuedReceiptIDs() {
				fmt.Fprintln(os.Stderr, "R1_RECEIPT", id)
			}
			continue
		}
		if len(fields) == 2 && fields[0] == "revoke" {
			if handoff.RevokeIssued(fields[1]) {
				fmt.Fprintln(os.Stderr, "R1_GRANT_REVOKED")
			} else {
				fmt.Fprintln(os.Stderr, "R1_GRANT_NOT_FOUND")
			}
			continue
		}

		if len(fields) != 7 || fields[0] != "approve" {
			fmt.Fprintln(os.Stderr, "R1_OPERATOR_COMMAND_REJECTED")
			continue
		}
		pid, e1 := strconv.ParseInt(fields[1], 10, 32)
		ttl, e2 := strconv.ParseInt(fields[6], 10, 32)
		if e1 != nil || e2 != nil || pid <= 0 || ttl <= 0 || ttl > 300 {
			fmt.Fprintln(os.Stderr, "R1_OPERATOR_ARGUMENTS_DENIED")
			continue
		}
		peer, e := readPeer(int32(pid))
		if e != nil {
			fmt.Fprintln(os.Stderr, "R1_OPERATOR_PID_UNAVAILABLE")
			continue
		}
		prefix := fields[4]
		if prefix == "-" {
			prefix = ""
		}
		e = handoff.Approve(peer, brokerruntime.HandoffRequest{Consumer: fields[2], Remote: fields[3], Prefix: prefix, Operations: []string{fields[5]}, TTL: time.Duration(ttl) * time.Second})
		if e != nil {
			fmt.Fprintln(os.Stderr, "R1_OPERATOR_APPROVAL_DENIED")
			continue
		}
		fmt.Fprintln(os.Stderr, "R1_ONE_PROCESS_GRANT_OFFER_READY (expires after 30s; no token displayed)")
	}
	if scanner.Err() != nil {
		fmt.Fprintln(os.Stderr, "R1_OPERATOR_STDIN_FAILED")
		return 2
	}
	return 0
}

func readPeer(pid int32) (brokeripc.KernelPeer, error) {
	var out brokeripc.KernelPeer
	if pid <= 0 {
		return out, fmt.Errorf("bad PID")
	}
	raw, e := os.ReadFile(fmt.Sprintf("/proc/%d/status", pid))
	if e != nil {
		return out, e
	}
	vals := map[string]uint32{}
	for _, line := range strings.Split(string(raw), "\n") {
		for _, key := range []string{"Uid:", "Gid:"} {
			if !strings.HasPrefix(line, key) {
				continue
			}
			parts := strings.Fields(strings.TrimPrefix(line, key))
			if len(parts) != 4 {
				return out, fmt.Errorf("invalid proc status")
			}
			first, e := strconv.ParseUint(parts[0], 10, 32)
			if e != nil {
				return out, e
			}
			for _, field := range parts[1:] {
				v, er := strconv.ParseUint(field, 10, 32)
				if er != nil || v != first {
					return out, fmt.Errorf("changed process creds")
				}
			}
			if _, seen := vals[key]; seen {
				return out, fmt.Errorf("duplicate proc status")
			}
			vals[key] = uint32(first)
		}
	}
	if len(vals) != 2 {
		return out, fmt.Errorf("missing peer creds")
	}
	return brokeripc.KernelPeer{PID: pid, UID: vals["Uid:"], GID: vals["Gid:"]}, nil
}
