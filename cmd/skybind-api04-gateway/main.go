// Explicit root operator tool only. Nothing starts this command automatically.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"skybind/internal/brokeridentity"
	"skybind/internal/daemon"
	"skybind/internal/featuregateway"
	"skybind/internal/paths"
	"skybind/internal/protocol"
)

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "API04_ROOT_REQUIRED")
		return 2
	}
	f := flag.NewFlagSet("skybind-api04-gateway", flag.ContinueOnError)
	approved := f.Bool("operator-approve", false, "explicit root-operator activation")
	uid := f.Uint("authority-uid", 0, "independently pinned Skybind Android app UID")
	label := f.String("authority-context", "", "independently pinned Skybind app SELinux label")
	apk := f.String("authority-apk", "", "approved installed Skybind APK path")
	digest := f.String("authority-apk-sha256", "", "approved installed Skybind APK SHA256")
	if f.Parse(args) != nil || len(f.Args()) != 0 || !*approved || *uid < 10000 || *uid > 1<<31-1 {
		fmt.Fprintln(os.Stderr, "API04_OPERATOR_APPROVAL_REQUIRED")
		return 2
	}
	policy, err := featuregateway.LoadCanonical()
	if err != nil {
		fmt.Fprintln(os.Stderr, "API04_POLICY_DENIED")
		return 2
	}
	bridge := &brokeridentity.PMBridge{
		Pin:    brokeridentity.AuthorityPeerPin{UID: uint32(*uid), SELinuxContext: *label},
		Proc:   brokeridentity.LinuxProc{},
		Anchor: brokeridentity.AuthorityAPKAnchor{AppUID: uint32(*uid), ApprovedAPKPath: *apk, ApprovedAPK_SHA256: *digest},
	}
	if err = bridge.ListenAPI04(); err != nil {
		fmt.Fprintln(os.Stderr, "API04_PM_BIND_DENIED")
		return 2
	}
	defer bridge.Close()
	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()
	wait, stop := context.WithTimeout(ctx, 30*time.Second)
	err = bridge.Accept(wait)
	stop()
	if err != nil {
		fmt.Fprintln(os.Stderr, "API04_PM_AUTHORITY_DENIED")
		return 2
	}
	guard, err := featuregateway.NewGuard(policy, featuregateway.Dependencies{
		Packages: bridge, Proc: brokeridentity.LinuxProc{},
	})
	if err != nil {
		fmt.Fprintln(os.Stderr, "API04_GUARD_DENIED")
		return 2
	}
	server := &featuregateway.EndpointServer{
		Guard: guard, ExplicitlyEnabled: true,
		Dispatch: func(ctx context.Context, req protocol.Request) (protocol.Response, error) {
			return daemon.Call(ctx, paths.DaemonSocket, req)
		},
	}
	if err = server.Start(); err != nil {
		fmt.Fprintln(os.Stderr, "API04_SOCKET_BIND_DENIED")
		return 2
	}
	defer server.Close()
	fmt.Fprintln(os.Stderr, "API04_ROOT_OPERATOR_READY (query only, no grants, not auto-started)")
	if err = server.Serve(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "API04_SERVICE_STOPPED")
		return 1
	}
	return 0
}
