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
		// rclone's actual "size --json" emits count, bytes, sizeless and fs.
		// The latter two are NOT unexpected fields: older fixture-only tests
		// accidentally made the live response fail closed for every real Size.
		target := r.Remote + ":" + r.Path
		out, e := m.Runner.Run(ctx, nil, "--config", paths.RcloneConfig, "size", "--json", "--", target)
		if e != nil || len(out) == 0 || len(out) > 8192 {
			return nil, errors.New("r1_metadata_size_failed")
		}
		dec := json.NewDecoder(bytes.NewReader(out))
		dec.DisallowUnknownFields()
		var parsed struct {
			Count    *int64  `json:"count"`
			Bytes    *int64  `json:"bytes"`
			Sizeless *int64  `json:"sizeless"`
			Fs       *string `json:"fs"`
		}
		if e = dec.Decode(&parsed); e != nil || parsed.Count == nil || parsed.Bytes == nil {
			return nil, errors.New("r1_metadata_bad_size")
		}
		if e = dec.Decode(new(any)); e != io.EOF || *parsed.Count < 0 || *parsed.Bytes < 0 {
			return nil, errors.New("r1_metadata_bad_size")
		}
		// A positive sizeless count means some remote objects have no known
		// size. Preserve that signal instead of silently presenting a complete
		// byte total. rclone's fs must echo our independently validated target.
		var sizeless int64
		if parsed.Sizeless != nil {
			sizeless = *parsed.Sizeless
		}
		if sizeless < 0 || sizeless > *parsed.Count || (parsed.Fs != nil && *parsed.Fs != target) {
			return nil, errors.New("r1_metadata_bad_size")
		}
		// Never expose the engine-reported fs identifier; the caller already
		// knows its operator-approved remote and path.
		return json.Marshal(struct {
			Count    int64 `json:"count"`
			Bytes    int64 `json:"bytes"`
			Sizeless int64 `json:"sizeless,omitempty"`
		}{*parsed.Count, *parsed.Bytes, sizeless})
	default:
		return nil, fmt.Errorf("r1_metadata_unsupported_operation")
	}
}
