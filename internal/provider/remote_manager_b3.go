package provider

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"skybind/internal/paths"
	"skybind/internal/previewproof"
	"strconv"
	"strings"
	"time"
)

type DirectoryCreate struct {
	Endpoint string `json:"endpoint"`
}

func (m *Manager) remoteFingerprint(endpoint string) (string, error) {
	return m.TransferFingerprint(endpoint, endpoint)
}
func (m *Manager) directoryAbsent(ctx context.Context, endpoint string) error {
	name, path, err := splitEndpoint(endpoint)
	if err != nil || path == "" {
		return errors.New("invalid target folder")
	}
	pos := strings.LastIndex(path, "/")
	parent := name + ":"
	leaf := path
	if pos >= 0 {
		parent += path[:pos]
		leaf = path[pos+1:]
	}
	entries, err := m.Browse(ctx, parent)
	if err != nil {
		return errors.New("parent remote folder is not readable")
	}
	for _, entry := range entries {
		if strings.EqualFold(entry.Name, leaf) {
			return errors.New("destination already exists")
		}
	}
	return nil
}
func (m *Manager) MkdirPreview(ctx context.Context, v DirectoryCreate) (any, error) {
	fp, err := m.remoteFingerprint(v.Endpoint)
	if err != nil {
		return nil, err
	}
	if err = m.directoryAbsent(ctx, v.Endpoint); err != nil {
		return nil, err
	}
	token, err := m.proofs.Issue(previewproof.Binding{Action: "remote.mkdir.run", Subject: v.Endpoint, Digest: fp}, 2*time.Minute)
	if err != nil {
		return nil, err
	}
	return map[string]any{"endpoint": v.Endpoint, "proof": token, "expires_seconds": 120, "creates_folder": true}, nil
}
func (m *Manager) MkdirRun(ctx context.Context, v DirectoryCreate, proof string) (any, error) {
	fp, err := m.remoteFingerprint(v.Endpoint)
	if err != nil {
		return nil, err
	}
	if err = m.proofs.Consume(proof, previewproof.Binding{Action: "remote.mkdir.run", Subject: v.Endpoint, Digest: fp}); err != nil {
		return nil, err
	}
	if err = m.directoryAbsent(ctx, v.Endpoint); err != nil {
		return nil, err
	}
	ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
	defer cancel()
	if _, err = m.runner.Run(ctx, nil, "--config", paths.RcloneConfig, "mkdir", "--", v.Endpoint); err != nil {
		return nil, err
	}
	return map[string]any{"created": true, "endpoint": v.Endpoint}, nil
}

// ValidFileMove verifies a *file*, same-remote destination, and a complete
// readable destination directory. A directory or pre-existing file never
// reaches `moveto`; --ignore-existing is used again during execution.
func (m *Manager) ValidFileMove(ctx context.Context, source, destination string) (string, error) {
	a, as, err := splitEndpoint(source)
	if err != nil || as == "" {
		return "", errors.New("invalid move source")
	}
	b, bs, err := splitEndpoint(destination)
	if err != nil || bs == "" || a != b || source == destination {
		return "", errors.New("move requires different paths on same remote")
	}
	fp, err := m.TransferFingerprint(source, destination)
	if err != nil {
		return "", err
	}
	item, err := m.Stat(ctx, source)
	if err != nil || item.IsDir {
		return "", errors.New("move source must be an existing file")
	}
	if err = m.directoryAbsent(ctx, destination); err != nil {
		return "", err
	}
	// Bind the preview to the observed file identity and size; if it changes,
	// execution gets a new fingerprint and the old proof is rejected.
	identity := fp + "|" + source + "|" + item.Name + "|" + strconv.FormatInt(item.Size, 10)
	digest := sha256.Sum256([]byte(identity))
	return hex.EncodeToString(digest[:]), nil
}
