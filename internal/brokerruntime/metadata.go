package brokerruntime

// Read-only R1 metadata backend. It deliberately reuses Skybind's existing
// bounded provider rather than exposing generic RC, arbitrary rclone flags,
// or a command selected by an IPC caller. No config bytes leave this package.
import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"regexp"
	"skybind/internal/brokeripc"
	"skybind/internal/paths"
	"skybind/internal/provider"
	"strings"
	"time"
)

var metaRemote = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)
var versionLine = regexp.MustCompile(`^rclone v[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?$`)

type Metadata struct {
	Provider *provider.Manager
	Runner   provider.Runner
}

func ProductionMetadata() *Metadata {
	return &Metadata{Provider: provider.Canonical(), Runner: provider.RuntimeRunner()}
}

func metadataPath(p string) bool {
	if len(p) > 4096 || strings.ContainsAny(p, "\\:%?#\r\n\x00") || strings.HasPrefix(p, "/") {
		return false
	}
	if p == "" {
		return true
	}
	for _, part := range strings.Split(p, "/") {
		if part == "" || part == "." || part == ".." {
			return false
		}
	}
	return true
}
func (m *Metadata) Read(r brokeripc.Request) (json.RawMessage, error) {
	if m == nil || m.Provider == nil || m.Runner == nil || r.Version != brokeripc.ProtocolVersion || !metaRemote.MatchString(r.Remote) || !metadataPath(r.Path) {
		return nil, errors.New("r1_metadata_invalid_request")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 12*time.Second)
	defer cancel()
	// Only names are returned, never types, backing paths, passwords or config.
	remotes, err := m.Provider.Remotes()
	if err != nil {
		return nil, errors.New("r1_metadata_remote_lookup_failed")
	}
	exists := false
	names := make([]string, 0, len(remotes))
	for _, remote := range remotes {
		if metaRemote.MatchString(remote.Name) {
			names = append(names, remote.Name)
			if remote.Name == r.Remote {
				exists = true
			}
		}
	}
	if !exists {
		return nil, errors.New("r1_metadata_unknown_remote")
	}
	switch r.Operation {
	case "system.capabilities":
		return json.Marshal(struct {
			Schema     string   `json:"schema"`
			Version    int      `json:"version"`
			Operations []string `json:"operations"`
			ReadOnly   bool     `json:"read_only"`
		}{"skybind-r1-metadata-v1", 1, []string{"system.capabilities", "rclone.version", "rclone.listremotes", "rclone.lsjson", "rclone.size"}, true})
	case "rclone.listremotes":
		return json.Marshal(struct {
			Remotes []string `json:"remotes"`
		}{[]string{r.Remote}})
	case "rclone.version":
		out, e := m.Runner.Run(ctx, nil, "version")
		if e != nil || len(out) > 4096 {
			return nil, errors.New("r1_metadata_version_unavailable")
		}
		line := strings.TrimSpace(strings.SplitN(string(out), "\n", 2)[0])
		if !versionLine.MatchString(line) {
			return nil, errors.New("r1_metadata_invalid_version")
		}
		return json.Marshal(struct {
			Version string `json:"version"`
		}{line})
	case "rclone.lsjson":
		entries, e := m.Provider.Browse(ctx, r.Remote+":"+r.Path)
		if e != nil {
			return nil, errors.New("r1_metadata_list_failed")
		}
		return json.Marshal(entries)
	case "rclone.size":
		out, e := m.Runner.Run(ctx, nil, "--config", paths.RcloneConfig, "size", "--json", "--", r.Remote+":"+r.Path)
		if e != nil || len(out) == 0 || len(out) > 4096 {
			return nil, errors.New("r1_metadata_size_failed")
		}
		dec := json.NewDecoder(bytes.NewReader(out))
		dec.DisallowUnknownFields()
		var result struct {
			Count int64 `json:"count"`
			Bytes int64 `json:"bytes"`
		}
		if e = dec.Decode(&result); e != nil {
			return nil, errors.New("r1_metadata_bad_size")
		}
		if e = dec.Decode(new(any)); e != io.EOF || result.Count < 0 || result.Bytes < 0 {
			return nil, errors.New("r1_metadata_bad_size")
		}
		return json.Marshal(result)
	default:
		return nil, fmt.Errorf("r1_metadata_unsupported_operation")
	}
}
