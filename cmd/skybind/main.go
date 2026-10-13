// Skybind native CLI and privileged daemon. Upstream rclone remains unchanged.
package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"skybind/internal/diagnostics"
	"skybind/internal/doctor"
	"skybind/internal/support"
	"skybind/internal/uisettings"
	"skybind/internal/webui"

	"fmt"
	"os"
	"os/signal"
	"skybind/internal/buildinfo"
	"skybind/internal/control"
	"skybind/internal/daemon"
	"skybind/internal/jobs"
	"skybind/internal/journal"
	"skybind/internal/mounts/cache"
	"skybind/internal/mounts/config"
	"skybind/internal/mounts/lifecycle"
	"skybind/internal/mounts/networkwatch"
	"skybind/internal/mounts/policy"
	"skybind/internal/mounts/supervisor"
	"skybind/internal/namespace"
	"skybind/internal/offline"
	"skybind/internal/paths"
	"skybind/internal/platformlifecycle"
	"skybind/internal/protocol"
	"skybind/internal/provider"
	"skybind/internal/rc"
	"skybind/internal/rootmgr"
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
	case "_ns-worker":
		return namespace.RunWorker(args[1:])
	case "webui":
		return webuiCommand(args[1:])
	case "support-export":
		// Fixed, root-only export of a verified owned ZIP. No arbitrary path,
		// shell command, unredacted data, or caller-controlled destination.
		if len(args) != 3 || os.Geteuid() != 0 {
			fmt.Fprintln(os.Stderr, "usage: skybind support-export <bundle-id> <sha256> (root only)")
			return 2
		}
		store, err := support.Open(paths.StateRoot + "/support")
		if err != nil {
			fmt.Fprintln(os.Stderr, "support export:", err)
			return 1
		}
		dest, err := store.ExportToDownloads(args[1], args[2])
		if err != nil {
			fmt.Fprintln(os.Stderr, "support export:", err)
			return 1
		}
		fmt.Println(dest)
		return 0
	case "offline":
		return offlineCommand(args[1:], offline.Canonical())
	case "daemon":
		if len(args) != 1 {
			usage()
			return 2
		}
		return daemonCommand()
	case "purge-preview":
		token, err := platformlifecycle.PreviewPurge()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		fmt.Println(token)
		return 0
	case "purge-state":
		if len(args) != 3 {
			return 2
		}
		if os.Geteuid() != 0 {
			return 1
		}
		if err := paths.EnsurePrivateState(); err != nil {
			return 1
		}
		cfg, err := config.Open(paths.StateRoot + "/config")
		if err != nil {
			return 1
		}
		mnt := lifecycle.Canonical(cfg)
		ns := namespace.CanonicalManager(mnt)
		if err = platformlifecycle.Purge(mnt, ns, args[1], args[2]); err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		return 0
	case "uninstall-stop":
		return uninstallStop()
	case "platform-status":
		return rpcCommand([]string{"platform.status", "query", "{}"})
	case "capabilities":
		if len(args) != 1 {
			return 2
		}
		return rpcCommand([]string{"system.capabilities", "query", "{}"})
	case "mount", "jobs", "job", "crypt", "remotes", "namespace", "doctor", "platform", "runtime", "rc":
		return domainCommand(args, os.Stdin, func(op string, payload []byte) int {
			item, ok := control.Lookup(op)
			if !ok {
				return 2
			}
			return rpcCommandAllowed([]string{op, string(item.OperationClass), string(payload)}, true)
		})
	case "help", "-h", "--help":
		usage()
		return 0
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
	fmt.Fprintln(os.Stderr, "usage: skybind <mount|jobs|job|crypt|remotes|namespace|doctor|platform|runtime|rc|offline|webui|daemon|capabilities|operation|rpc|version|paths|help>")
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
	namespaceEngine := namespace.CanonicalManager(mountEngine)
	jobStore, err := jobs.Canonical()
	if err != nil {
		fmt.Fprintln(os.Stderr, "job store:", err)
		return 1
	}
	providerEngine := provider.Canonical()
	rcEngine := rc.Canonical(func(name string) bool { _, _, err := mountEngine.VerifiedMount(name); return err == nil })
	mountEngine.ConfigureRC(rcEngine.Prepare, rcEngine.Drop)
	mountEngine.ConfigureWriteback(rcEngine.WritebackVerified)
	logStore, err := diagnostics.Open(paths.StateRoot + "/logs")
	if err != nil {
		fmt.Fprintln(os.Stderr, "private logs:", err)
		return 1
	}
	bundleStore, err := support.Open(paths.StateRoot + "/support")
	if err != nil {
		fmt.Fprintln(os.Stderr, "private support:", err)
		return 1
	}
	_ = logStore.Write("INFO", "daemon", "STARTUP", "Skybind daemon starting")
	uiStore, err := uisettings.Open(paths.StateRoot + "/ui")
	if err != nil {
		fmt.Fprintln(os.Stderr, "private UI settings:", err)
		return 1
	}
	engine := daemon.EngineWithObservability(j, cfg, mountEngine, cacheEngine, supervisorEngine, func() policy.Facts { return policy.SampleAndroidFacts(paths.StateRoot + "/cache") }, namespaceEngine, rootmgr.CanonicalDetector{}, jobStore, providerEngine, rcEngine, logStore, bundleStore, doctor.Canonical())
	if err = daemon.RegisterUISettings(engine, uiStore); err != nil {
		fmt.Fprintln(os.Stderr, "UI settings registry:", err)
		return 1
	}
	offlineStore := offline.Canonical()
	if err = daemon.RegisterOffline(engine, offline.NewTaskManager(offlineStore), offlineStore); err != nil {
		fmt.Fprintln(os.Stderr, "offline RPC registry:", err)
		return 1
	}

	srv := daemon.New(paths.DaemonSocket, engine)
	if err = srv.Start(); err != nil {
		fmt.Fprintln(os.Stderr, "daemon start:", err)
		return 1
	}
	defer srv.Close()
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGTERM, syscall.SIGINT)
	defer stop()
	// Kernel link/route events are wakeup hints only. Some Android devices
	// deny NETLINK_ROUTE subscriptions; bounded timer fallback always remains.
	networkEvents, watchErr := networkwatch.Listen(ctx)
	if watchErr != nil {
		_ = logStore.Write("INFO", "supervisor", "NETWORK_FALLBACK", "network_events=unavailable periodic_checks=enabled")
	}
	go runRecoveryLoop(ctx, supervisorEngine, logStore, jobStore, networkEvents)
	if err = srv.Serve(ctx); err != nil {
		fmt.Fprintln(os.Stderr, "daemon:", err)
		return 1
	}
	return 0
}
func rpcCommand(args []string) int { return rpcCommandAllowed(args, false) }
func rpcCommandAllowed(args []string, trustedStdin bool) int {
	if len(args) < 2 || len(args) > 3 {
		usage()
		return 2
	}
	var raw json.RawMessage = []byte(`{}`)
	if len(args) == 3 {
		raw = []byte(args[2])
	}
	item, known := control.Lookup(args[0])
	if !known || string(item.OperationClass) != args[1] || (!trustedStdin && args[0] == "provider.crypt.password.set") {
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

func uninstallStop() int {
	if os.Geteuid() != 0 {
		return 1
	}
	if err := paths.EnsurePrivateState(); err != nil {
		return 1
	}
	cfg, err := config.Open(paths.StateRoot + "/config")
	if err != nil {
		return 1
	}
	mounts := lifecycle.Canonical(cfg)
	ns := namespace.CanonicalManager(mounts)
	stopped, err := platformlifecycle.StopOwned(mounts, ns)
	if err != nil {
		fmt.Fprintln(os.Stderr, "guarded uninstall stop:", err)
		return 1
	}
	fmt.Printf("Skybind-owned mounts stopped: %d. User state preserved.\n", len(stopped))
	return 0
}

// webuiCommand provides exactly two fixed transport entrypoints.
// The root-manager bridge uses a single base64url argument, never a shell payload.
func webuiCommand(args []string) int {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "WebUI bridge requires privileged daemon identity")
		return 1
	}
	if len(args) == 0 {
		return 2
	}
	switch args[0] {
	case "bridge":
		if len(args) == 2 && args[1] == "--capabilities" {
			req := protocol.Request{SchemaVersion: 1, RequestID: "webui-caps", Operation: "system.capabilities", Class: protocol.Query, Arguments: json.RawMessage(`{}`)}
			response, err := daemon.Call(context.Background(), paths.DaemonSocket, req)
			if err != nil || !response.OK {
				return 1
			}
			if err := json.NewEncoder(os.Stdout).Encode(response.Result); err != nil {
				return 1
			}
			return 0
		}
		if len(args) != 3 || args[1] != "--request-base64" || len(args[2]) > protocol.MaxEnvelope*2 {
			return 2
		}
		result, err := webui.CLIRequest(context.Background(), args[2], paths.DaemonSocket)
		if err != nil {
			fmt.Fprintln(os.Stderr, "invalid typed WebUI request or backend unavailable")
			return 1
		}
		if err = json.NewEncoder(os.Stdout).Encode(result); err != nil {
			return 1
		}
		if !result.OK {
			return 1
		}
		return 0
	case "serve":
		if len(args) != 1 {
			return 2
		}
		srv, err := webui.NewStandalone(webui.DaemonCaller(paths.DaemonSocket), paths.ModuleRoot+"/webroot")
		if err == nil {
			srv.WithIdlePolicy(func() (time.Duration, error) {
				store, readErr := uisettings.Open(paths.StateRoot + "/ui")
				if readErr != nil {
					return 0, readErr
				}
				// Reload each authorization: preference changes take effect without
				// restarting the WebUI and cannot extend an already expired session.
				return time.Duration(store.Snapshot().Settings.WebUIIdleSeconds) * time.Second, nil
			})
		}
		if err != nil {
			return 1
		}
		address, token, err := srv.Listen()
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			return 1
		}
		defer srv.Close()
		// URL contains NO auth tokens. Enter one-time token in the auth flow.
		fmt.Fprintln(os.Stdout, "Skybind local WebUI:", address)
		fmt.Fprintln(os.Stdout, "Skybind one-time authentication token:", token)
		ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
		defer stop()
		if err = srv.Serve(ctx); err != nil {
			fmt.Fprintln(os.Stderr, "WebUI transport unavailable")
			return 1
		}
		return 0
	default:
		// Unknown subcommands fail closed.
		return 2
	}
}
