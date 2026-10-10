// Skybind native CLI foundation; privileged daemon work begins in SB-O06.
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"skybind/internal/buildinfo"
	"skybind/internal/paths"
	"skybind/internal/runtimeauth"
)

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	if len(args) != 1 {
		fmt.Fprintln(os.Stderr, "usage: skybind <version|paths|runtime-status>")
		return 2
	}
	switch args[0] {
	case "version", "--version":
		fmt.Printf("%s %s (%s)\n", buildinfo.Product, buildinfo.Version, buildinfo.Commit)
		return 0
	case "runtime-status":
		status := runtimeauth.StatusCanonical()
		if err := json.NewEncoder(os.Stdout).Encode(status); err != nil {
			return 1
		}
		if !status.Ready {
			return 1
		}
		return 0
	case "paths":
		p := paths.Default()
		fmt.Printf("module=%s\nstate=%s\nengine=%s\nfuse=%s\nsocket=%s\n", p.Module, p.State, p.Engine, p.Fuse, p.Socket)
		return 0
	default:
		fmt.Fprintln(os.Stderr, "unsupported command; this bootstrap does not run a daemon or manage mounts")
		return 2
	}
}
