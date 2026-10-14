package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/signal"
	"skybind/internal/daemon"
	"skybind/internal/opevents"
	"skybind/internal/paths"
	"skybind/internal/protocol"
	"strconv"
	"syscall"
)

// events [--id RUN_ID] [--cursor SEQUENCE] [--follow]
// Emits a stable JSON Lines event stream, retaining a cursor after each
// successful poll. No rclone flag, arbitrary executable, URL, or raw log is
// exposed through this command.
func eventsCommand(args []string) int {
	id := ""
	cursor := uint64(0)
	follow := false
	for i := 0; i < len(args); i++ {
		switch args[i] {
		case "--id":
			if i+1 >= len(args) || id != "" {
				return 2
			}
			i++
			id = args[i]
		case "--cursor":
			if i+1 >= len(args) {
				return 2
			}
			i++
			v, err := strconv.ParseUint(args[i], 10, 64)
			if err != nil {
				return 2
			}
			cursor = v
		case "--follow":
			follow = true
		default:
			fmt.Fprintln(os.Stderr, "usage: skybind events [--id RUN_ID] [--cursor N] [--follow]")
			return 2
		}
	}
	if id != "" && (len(id) != 32 || !isLowerHex(id)) {
		return 2
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	return streamOperationEvents(ctx, paths.DaemonSocket, id, cursor, follow, os.Stdout)
}
func isLowerHex(s string) bool {
	for _, c := range s {
		if c < '0' || c > '9' && (c < 'a' || c > 'f') {
			return false
		}
	}
	return true
}
func streamOperationEvents(ctx context.Context, socket, id string, cursor uint64, follow bool, out *os.File) int {
	enc := json.NewEncoder(out)
	for {
		if ctx.Err() != nil {
			return 0
		}
		rawID := make([]byte, 16)
		if _, err := rand.Read(rawID); err != nil {
			return 1
		}
		wait := 0
		if follow {
			wait = 5000
		}
		payload, _ := json.Marshal(map[string]any{"cursor": cursor, "limit": 64, "operation_id": id, "wait_ms": wait})
		req := protocol.Request{SchemaVersion: protocol.Version, RequestID: hex.EncodeToString(rawID), Operation: "operation.events", Class: protocol.Query, Arguments: payload}
		res, err := daemon.Call(ctx, socket, req)
		if err != nil {
			fmt.Fprintln(os.Stderr, "event transport unavailable:", err)
			return 1
		}
		if !res.OK {
			fmt.Fprintln(os.Stderr, "event API unavailable")
			return 1
		}
		b, err := json.Marshal(res.Result)
		if err != nil {
			return 1
		}
		var page opevents.Page
		if err = json.Unmarshal(b, &page); err != nil {
			return 1
		}
		if page.Gap || page.CursorReset {
			fmt.Fprintf(os.Stderr, "event cursor discontinuity: oldest=%d latest=%d\n", page.OldestCursor, page.LatestCursor)
		}
		terminal := false
		for _, event := range page.Events {
			if err = enc.Encode(event); err != nil {
				return 1
			}
			if id != "" && (event.Type == "job.completed" || event.Type == "job.failed" || event.Type == "job.cancelled" || event.Type == "job.interrupted" || event.Type == "operation.succeeded" || event.Type == "operation.failed") {
				terminal = true
			}
		}
		if page.Degraded {
			fmt.Fprintln(os.Stderr, "warning: operation event persistence degraded; poll job status for authoritative state")
		}
		if terminal {
			return 0
		}
		cursor = page.NextCursor
		if !follow {
			return 0
		}
		// Advance through backlog without waiting; otherwise bounded long poll.
	}
}
