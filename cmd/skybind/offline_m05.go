package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"skybind/internal/offline"
	"skybind/internal/paths"
	"strconv"
	"time"
)

func offlineCommand(args []string, store *offline.Store) int {
	if os.Geteuid() != 0 || paths.EnsurePrivateState() != nil {
		fmt.Fprintln(os.Stderr, "offline: requires trusted root/private Skybind state")
		return 1
	}
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "usage: skybind offline <list|pin|pin-dir|status|check|export|view-publish|unpin|gc|quota> [mount] [relative-path]")
		return 2
	}
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
	defer cancel()
	var v any
	var err error
	switch args[0] {
	case "list":
		if len(args) != 1 {
			return 2
		}
		v, err = store.List()
	case "quota":
		if len(args) != 2 {
			return 2
		}
		gb, e := strconv.ParseInt(args[1], 10, 64)
		if e != nil || gb < 1 || gb > 64 {
			return 2
		}
		err = store.Quota(gb << 30)
		v = map[string]any{"quota_gb": gb}
	case "pin", "pin-dir":
		if len(args) != 3 {
			return 2
		}
		var count int
		count, err = store.Pin(ctx, args[1], args[2], args[0] == "pin-dir")
		v = map[string]any{"pinned": count}
	case "status", "check":
		if len(args) != 3 {
			return 2
		}
		v, err = store.Status(ctx, args[1], args[2], args[0] == "check")
	case "export":
		if len(args) != 3 {
			return 2
		}
		var dest string
		dest, err = store.Export(args[1], args[2])
		v = map[string]any{"exported_path": dest, "warning": "export is a separate readable Android media copy, NOT a synced or protected mount"}
	case "view-publish":
		if len(args) != 2 {
			return 2
		}
		var dest string
		dest, err = store.PublishView(ctx, args[1])
		v = map[string]any{"view_path": dest, "warning": "public Android Downloads snapshot; separate from original FUSE mount, not synchronized or tamper-resistant"}
	case "unpin":
		if len(args) != 3 {
			return 2
		}
		err = store.Unpin(args[1], args[2])
		v = map[string]any{"unpinned": true}
	case "gc":
		if len(args) != 1 {
			return 2
		}
		var count int
		count, err = store.GC()
		v = map[string]any{"removed_unreferenced_offline_objects": count}
	default:
		return 2
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "offline:", err)
		return 1
	}
	_ = json.NewEncoder(os.Stdout).Encode(v)
	return 0
}
