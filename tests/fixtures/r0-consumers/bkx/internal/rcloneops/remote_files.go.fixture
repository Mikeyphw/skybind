package rcloneops

import (
	"context"
	"encoding/json"
	"fmt"
	"path"
	"sort"
	"strings"
)

// ParentURI returns the credential-free parent rclone URI for value.
func ParentURI(value string) (string, error) {
	parsed, err := parseLocation(value)
	if err != nil {
		return "", err
	}
	parent := path.Dir("/" + parsed.path)
	if parent == "/" || parent == "." {
		return CanonicalURI("rclone://" + parsed.remote + "/")
	}
	return CanonicalURI("rclone://" + parsed.remote + parent)
}

// Exists checks a remote object without exposing provider credentials in the location.
func (r Runtime) Exists(ctx context.Context, value string) (bool, error) {
	if !IsLocation(value) {
		return false, fmt.Errorf("rclone existence check requires an rclone:// location")
	}
	_, err := r.Stat(ctx, value)
	if err == nil {
		return true, nil
	}
	lower := strings.ToLower(err.Error())
	for _, marker := range []string{"not found", "directory not found", "object not found", "file not found", "doesn't exist", "does not exist"} {
		if strings.Contains(lower, marker) {
			return false, nil
		}
	}
	return false, err
}

// CopyTo copies exactly source to destination. Unlike Transfer it never appends a basename.
// When overwrite is false, --immutable prevents replacing an object that appears after preflight.
func (r Runtime) CopyTo(ctx context.Context, source, destination string, options TransferOptions) (TransferResult, error) {
	if err := r.requireConfigForRemote(source, destination); err != nil {
		return TransferResult{}, err
	}
	if cancelled(options.Cancelled) {
		return TransferResult{}, context.Canceled
	}
	src, err := commandLocation(source)
	if err != nil {
		return TransferResult{}, err
	}
	dst, err := commandLocation(destination)
	if err != nil {
		return TransferResult{}, err
	}
	_, size, err := r.Measure(ctx, source)
	if err != nil {
		return TransferResult{}, fmt.Errorf("inspect rclone copy source: %w", err)
	}
	emitTransferProgress(options, Progress{FilesTotal: size.Files, BytesTotal: size.Bytes})
	args := []string{"copyto", src, dst}
	args = append(args, r.baseArgs()...)
	args = append(args,
		"--use-json-log",
		"--stats", "500ms",
		"--stats-log-level", "NOTICE",
		"--log-level", "NOTICE",
		"--retries", "3",
		"--low-level-retries", "5",
	)
	if !options.Overwrite {
		args = append(args, "--immutable")
	}
	last, warnings, err := r.runCommand(ctx, args, options.Cancelled, func(current statsDocument) {
		emitTransferProgress(options, Progress{
			FilesDone: current.Transfers, FilesTotal: size.Files,
			BytesDone: current.Bytes, BytesTotal: size.Bytes,
		})
	})
	if err != nil {
		return TransferResult{}, err
	}
	allWarnings := append([]string(nil), warnings...)
	if options.Verify {
		verifyArgs := []string{"check", src, dst, "--download", "--one-way"}
		verifyArgs = append(verifyArgs, r.baseArgs()...)
		verifyArgs = append(verifyArgs, "--log-level", "ERROR")
		if _, verifyWarnings, err := r.runCommand(ctx, verifyArgs, options.Cancelled, nil); err != nil {
			return TransferResult{}, fmt.Errorf("rclone verification failed: %w", err)
		} else {
			allWarnings = append(allWarnings, verifyWarnings...)
		}
		destinationEntry, err := r.Stat(ctx, destination)
		if err != nil {
			return TransferResult{}, fmt.Errorf("inspect copied rclone destination: %w", err)
		}
		if !destinationEntry.IsDir && size.Bytes >= 0 && destinationEntry.Size != size.Bytes {
			return TransferResult{}, fmt.Errorf("rclone verification failed: source and destination size differ")
		}
	}
	files := max64(last.Transfers, size.Files)
	bytes := max64(last.Bytes, size.Bytes)
	emitTransferProgress(options, Progress{FilesDone: files, FilesTotal: size.Files, BytesDone: bytes, BytesTotal: size.Bytes})
	return TransferResult{Files: files, Bytes: bytes, Warnings: allWarnings}, nil
}

func (r Runtime) DeleteFile(ctx context.Context, value string) error {
	if !IsLocation(value) {
		return fmt.Errorf("rclone delete requires an rclone:// location")
	}
	if err := r.requireConfigForRemote(value); err != nil {
		return err
	}
	resolved, err := commandLocation(value)
	if err != nil {
		return err
	}
	args := append([]string{"deletefile", resolved}, r.baseArgs()...)
	_, err = r.commandOutput(ctx, args)
	if err != nil {
		lower := strings.ToLower(err.Error())
		if strings.Contains(lower, "not found") || strings.Contains(lower, "does not exist") || strings.Contains(lower, "doesn't exist") {
			return nil
		}
	}
	return err
}

// ListRecursive returns bounded file metadata beneath a remote root without downloading payloads.
func (r Runtime) ListRecursive(ctx context.Context, location string, maxDepth, limit int) ([]Entry, error) {
	if !IsLocation(location) {
		return nil, fmt.Errorf("recursive rclone list requires an rclone:// location")
	}
	if err := r.requireConfigForRemote(location); err != nil {
		return nil, err
	}
	if maxDepth < 0 {
		maxDepth = 0
	}
	if maxDepth > 8 {
		maxDepth = 8
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 2000 {
		limit = 2000
	}
	resolved, err := commandLocation(location)
	if err != nil {
		return nil, err
	}
	args := append([]string{"lsjson", resolved, "--recursive", "--files-only", "--no-mimetype"}, r.baseArgs()...)
	out, err := r.commandOutput(ctx, args)
	if err != nil {
		return nil, err
	}
	var entries []Entry
	if err := json.Unmarshal(out, &entries); err != nil {
		return nil, fmt.Errorf("decode recursive rclone lsjson output: %w", err)
	}
	filtered := make([]Entry, 0, minInt(len(entries), limit))
	for _, entry := range entries {
		clean := strings.Trim(strings.ReplaceAll(entry.Path, "\\", "/"), "/")
		if clean == "" || strings.ContainsRune(clean, '\x00') {
			continue
		}
		depth := strings.Count(clean, "/")
		if depth > maxDepth || entry.IsDir {
			continue
		}
		if entry.Size < 0 {
			entry.Size = 0
		}
		entry.Path = clean
		if entry.Name == "" {
			entry.Name = path.Base(clean)
		}
		filtered = append(filtered, entry)
		if len(filtered) >= limit {
			break
		}
	}
	sort.Slice(filtered, func(i, j int) bool { return strings.ToLower(filtered[i].Path) < strings.ToLower(filtered[j].Path) })
	return filtered, nil
}

func minInt(a, b int) int {
	if a < b {
		return a
	}
	return b
}
