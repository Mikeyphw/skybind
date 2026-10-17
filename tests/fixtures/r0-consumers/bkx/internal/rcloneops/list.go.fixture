package rcloneops

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type Entry struct {
	Name    string    `json:"Name"`
	Path    string    `json:"Path"`
	Size    int64     `json:"Size"`
	ModTime time.Time `json:"ModTime"`
	IsDir   bool      `json:"IsDir"`
}

func (r Runtime) List(ctx context.Context, location string) ([]Entry, error) {
	if !IsLocation(location) {
		return nil, fmt.Errorf("rclone list requires an rclone:// remote location")
	}
	if err := r.requireConfigForRemote(location); err != nil {
		return nil, err
	}
	resolved, err := commandLocation(location)
	if err != nil {
		return nil, err
	}
	args := append([]string{"lsjson", resolved, "--max-depth", "1", "--no-mimetype"}, r.baseArgs()...)
	out, err := r.commandOutput(ctx, args)
	if err != nil {
		return nil, err
	}
	var entries []Entry
	if err := json.Unmarshal(out, &entries); err != nil {
		return nil, fmt.Errorf("decode rclone lsjson output: %w", err)
	}
	for index := range entries {
		if strings.TrimSpace(entries[index].Name) == "" || strings.ContainsRune(entries[index].Path, '\x00') {
			return nil, fmt.Errorf("rclone returned an invalid remote entry")
		}
		if entries[index].Size < 0 {
			entries[index].Size = 0
		}
	}
	sort.Slice(entries, func(i, j int) bool {
		if entries[i].IsDir != entries[j].IsDir {
			return entries[i].IsDir
		}
		return strings.ToLower(entries[i].Name) < strings.ToLower(entries[j].Name)
	})
	return entries, nil
}

func (r Runtime) Stat(ctx context.Context, value string) (Entry, error) {
	if !IsLocation(value) {
		absolute, err := filepath.Abs(value)
		if err != nil {
			return Entry{}, err
		}
		info, err := os.Stat(absolute)
		if err != nil {
			return Entry{}, err
		}
		return Entry{Name: info.Name(), Path: absolute, Size: max64(info.Size(), 0), ModTime: info.ModTime(), IsDir: info.IsDir()}, nil
	}
	if err := r.requireConfigForRemote(value); err != nil {
		return Entry{}, err
	}
	resolved, err := commandLocation(value)
	if err != nil {
		return Entry{}, err
	}
	args := append([]string{"lsjson", resolved, "--stat", "--no-mimetype"}, r.baseArgs()...)
	out, err := r.commandOutput(ctx, args)
	if err != nil {
		return Entry{}, err
	}
	var entry Entry
	if err := json.Unmarshal(out, &entry); err != nil {
		return Entry{}, fmt.Errorf("decode rclone stat output: %w", err)
	}
	if entry.Name == "" {
		entry.Name = BaseName(value)
	}
	if entry.Size < 0 {
		entry.Size = 0
	}
	return entry, nil
}

func (r Runtime) commandOutput(ctx context.Context, args []string) ([]byte, error) {
	command := execCommandContext(ctx, r.Executable, args...)
	var stderr bytes.Buffer
	command.Stderr = &stderr
	out, err := command.Output()
	if err != nil {
		diagnostic := r.sanitizeDiagnostic(stderr.String())
		if diagnostic != "" {
			return nil, fmt.Errorf("%w: %s", commandError("rclone", err), diagnostic)
		}
		return nil, commandError("rclone", err)
	}
	return out, nil
}
