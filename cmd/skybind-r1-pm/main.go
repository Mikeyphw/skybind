package main

// Explicit root-only R1 Android->Go platform authority acceptance. There are
// no grants, client sockets, module changes or backup operations in this CLI.
import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"skybind/internal/brokeridentity"
	"time"
)

type pmAcceptance struct {
	Schema                  string `json:"schema"`
	State                   string `json:"state"`
	PMChannelAuthenticated  bool   `json:"pm_channel_authenticated"`
	BKXSignerApproved       bool   `json:"bkx_signer_approved"`
	ConsumerBrokerQualified bool   `json:"consumer_broker_qualified"`
	GrantsIssued            bool   `json:"grants_issued"`
	M3DeviceRetestsRun      bool   `json:"m3_device_retests_run"`
	Reason                  string `json:"reason,omitempty"`
}

func main() { os.Exit(r1PMBridgeCheck(os.Args[1:])) }

func r1PMBridgeCheck(args []string) int {
	result := pmAcceptance{Schema: "skybind-r1-android-to-go-pm-v1", State: "BLOCKED"}
	defer func() { _ = json.NewEncoder(os.Stdout).Encode(result) }()
	if os.Geteuid() != 0 {
		result.Reason = "ROOT_REQUIRED"
		return 2
	}
	fs := flag.NewFlagSet("r1-pm-bridge-check", flag.ContinueOnError)
	fs.SetOutput(os.Stderr)
	authorityUID := fs.Uint("skybind-uid", 0, "independently approved Skybind Android app UID")
	authorityContext := fs.String("skybind-context", "", "independently approved Skybind app process SELinux context")
	bkxUID := fs.Uint("bkx-uid", 0, "independently approved BKX app UID")
	bkxSigner := fs.String("bkx-signer", "", "independently approved BKX DER certificate SHA-256")
	if fs.Parse(args) != nil || len(fs.Args()) != 0 || *authorityUID > 1<<31-1 || *bkxUID > 1<<31-1 {
		result.Reason = "INVALID_ARGUMENTS"
		return 2
	}
	appPin := brokeridentity.PackagePin{Name: "com.mikeyphw.bkx.android", CertSHA256: *bkxSigner, SELinuxContext: "u:r:untrusted_app:s0"}
	// The signer must be approved out of band: empty/malformed pins never run.
	if len(*bkxSigner) != 64 || *bkxUID < 10000 || *authorityUID < 10000 {
		result.Reason = "OPERATOR_PIN_REQUIRED"
		return 2
	}
	bridge := &brokeridentity.PMBridge{Pin: brokeridentity.AuthorityPeerPin{UID: uint32(*authorityUID), SELinuxContext: *authorityContext}, Proc: brokeridentity.LinuxProc{}}
	if err := bridge.Listen(); err != nil {
		result.Reason = "AUTHORITY_LISTENER_DENIED"
		return 2
	}
	defer bridge.Close()
	fmt.Fprintln(os.Stderr, "R1 authority listener started. Open Skybind app to activate its unprivileged PM agent.")
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
	defer cancel()
	if e := bridge.Accept(ctx); e != nil {
		result.Reason = "AUTHORITY_PEER_NOT_ATTESTED"
		return 2
	}
	result.PMChannelAuthenticated = true
	attestor := brokeridentity.PlatformPackageAttestor{Authority: bridge}
	if e := attestor.Verify(ctx, uint32(*bkxUID), appPin); e != nil {
		result.Reason = "BKX_SIGNER_OR_UID_DENIED"
		return 2
	}
	result.BKXSignerApproved = true
	result.State = "PASS_R1_AUTHENTICATED_PM_CHANNEL_ONLY"
	return 0
}
