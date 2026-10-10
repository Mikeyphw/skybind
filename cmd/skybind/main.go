// Skybind native CLI and privileged daemon. Upstream rclone remains unchanged.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"skybind/internal/buildinfo"
	"skybind/internal/control"
	"skybind/internal/daemon"
	"skybind/internal/journal"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/mounts/policy"
	"skybind/internal/mounts/supervisor"
	"skybind/internal/paths"
	"skybind/internal/protocol"
	"skybind/internal/runtimeauth"
	"syscall"
	"time"
)

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	if len(args) == 0 {
		usage()
		return 2
	}
	switch args[0] {
	case "version", "--version":
		fmt.Printf("%s %s (%s)\n", buildinfo.Product, buildinfo.Version, buildinfo.Commit)
		return 0
	case "runtime-status":
		s := runtimeauth.StatusCanonical()
		_ = json.NewEncoder(os.Stdout).Encode(s)
		if !s.Ready {
			return 1
		}
		return 0
	case "paths":
		p := paths.Default()
		fmt.Printf("module=%s\nstate=%s\nengine=%s\nfuse=%s\nsocket=%s\n", p.Module, p.State, p.Engine, p.Fuse, p.Socket)
		return 0
	case "daemon":
		if len(args) != 1 {
			usage()
			return 2
		}
		return daemonCommand()
	case "capabilities":
		if len(args) != 1 {
			return 2
		}
		return rpcCommand([]string{"system.capabilities", "query", "{}"})
	case "operation":
		if len(args) < 2 || len(args) > 3 {
			return 2
		}
		item, ok := control.Lookup(args[1])
		if !ok {
			fmt.Fprintln(os.Stderr, "unknown operation")
			return 2
		}
		payload := "{}"
		if len(args) == 3 {
			payload = args[2]
		}
		return rpcCommand([]string{item.Name, string(item.OperationClass), payload})
	case "rpc":
		return rpcCommand(args[1:])
	default:
		usage()
		return 2
	}
}
func usage() {
	fmt.Fprintln(os.Stderr, "usage: skybind <version|paths|runtime-status|daemon|capabilities|operation NAME [ARGS_JSON]|rpc OP CLASS [ARGS_JSON]>")
}
func daemonCommand() int {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "daemon requires root")
		return 1
	}
	if err := paths.EnsurePrivateState(); err != nil {
		fmt.Fprintln(os.Stderr, "private state:", err)
		return 1
	}
	j, err := journal.Open(paths.StateRoot + "/journal")
	if err != nil {
		fmt.Fprintln(os.Stderr, "journal:", err)
		return 1
	}
	cfg, err := config.Open(paths.StateRoot + "/config")
	if err != nil {
		fmt.Fprintln(os.Stderr, "config:", err)
		return 1
	}
	mountEngine := lifecycle.Canonical(cfg)
	cacheEngine := cache.Canonical(func(name string) bool {
		st, err := mountEngine.Status(name)
		return err != nil || st.Observed != "STOPPED"
	})
	supervisorEngine, err := supervisor.NewCanonical(mountEngine)
	if err != nil {
		fmt.Fprintln(os.Stderr, "supervisor state:", err)
		return 1
	}
	supervisorEngine.ConfigureCache(cacheEngine, cfg)
	srv := daemon.New(paths.DaemonSocket, daemon.EngineWithMounts(j, cfg, mountEngine, cacheEngine, supervisorEngine, func() policy.Facts { return policy.AndroidFacts(paths.StateRoot + "/cache") }))
	if err = srv.Start(); err != nil {
		fmt.Fprintln(os.Stderr, "daemon start:", err)
		return 1
	}
	defer srv.Close()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	// Periodic reconciliation is bounded and driven solely by persisted desired
	// state; explicit stop is not undone and no unknown network is assumed safe.
	go func() {
		timer := time.NewTicker(30 * time.Second)
		defer timer.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-timer.C:
				_, _ = supervisorEngine.Reconcile(ctx)
			}
		}
	}()
	if err = srv.Serve(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "daemon:", err)
		return 1
	}
	return 0
}
func rpcCommand(args []string) int {
	if len(args) < 2 || len(args) > 3 {
		usage()
		return 2
	}
	var raw json.RawMessage = []byte(`{}`)
	if len(args) == 3 {
		raw = []byte(args[2])
	}
	item, known := control.Lookup(args[0])
	if !known || string(item.OperationClass) != args[1] {
		fmt.Fprintln(os.Stderr, "unknown operation or class mismatch")
		return 2
	}
	idBytes := make([]byte, 16)
	if _, err := rand.Read(idBytes); err != nil {
		return 1
	}
	req := protocol.Request{SchemaVersion: protocol.Version, RequestID: hex.EncodeToString(idBytes), Operation: args[0], Class: protocol.Class(args[1]), Arguments: raw}
	if !json.Valid(raw) {
		fmt.Fprintln(os.Stderr, "invalid JSON arguments")
		return 2
	}
	result, err := daemon.Call(context.Background(), paths.DaemonSocket, req)
	if err != nil {
		fmt.Fprintln(os.Stderr, "RPC transport:", err)
		return 1
	}
	if err = json.NewEncoder(os.Stdout).Encode(result); err != nil {
		return 1
	}
	if !result.OK {
		return 1
	}
	return 0
}
