package rcloneops

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"sync"
	"time"
)

type Size struct {
	Files int64 `json:"count"`
	Bytes int64 `json:"bytes"`
}

type Progress struct {
	FilesDone  int64
	FilesTotal int64
	BytesDone  int64
	BytesTotal int64
}

type TransferOptions struct {
	Overwrite       bool
	Verify          bool
	SyncDeleteLimit int
	Cancelled       func() bool
	Progress        func(Progress)
}

type TransferResult struct {
	Files    int64
	Bytes    int64
	Warnings []string
}

type statsDocument struct {
	Bytes          int64 `json:"bytes"`
	Transfers      int64 `json:"transfers"`
	TotalBytes     int64 `json:"totalBytes"`
	TotalTransfers int64 `json:"totalTransfers"`
}

type logDocument struct {
	Stats *statsDocument `json:"stats"`
}

type transferMapping struct {
	source      string
	destination string
	sourceEntry Entry
}

func (r Runtime) Size(ctx context.Context, location string) (Size, error) {
	if err := r.requireConfigForRemote(location); err != nil {
		return Size{}, err
	}
	resolved, err := commandLocation(location)
	if err != nil {
		return Size{}, err
	}
	args := append([]string{"size", resolved, "--json"}, r.baseArgs()...)
	out, err := r.commandOutput(ctx, args)
	if err != nil {
		return Size{}, err
	}
	var result Size
	if err := json.Unmarshal(out, &result); err != nil {
		return Size{}, fmt.Errorf("decode rclone size output: %w", err)
	}
	if result.Files < 0 || result.Bytes < 0 {
		return Size{}, fmt.Errorf("rclone returned invalid negative size totals")
	}
	return result, nil
}

func (r Runtime) Measure(ctx context.Context, location string) (Entry, Size, error) {
	entry, err := r.Stat(ctx, location)
	if err != nil {
		return Entry{}, Size{}, err
	}
	if !entry.IsDir {
		return entry, Size{Files: 1, Bytes: max64(entry.Size, 0)}, nil
	}
	size, err := r.Size(ctx, location)
	if err != nil {
		return Entry{}, Size{}, err
	}
	return entry, size, nil
}

func (r Runtime) Transfer(ctx context.Context, mode string, sources []string, destination string, options TransferOptions) (TransferResult, error) {
	if len(sources) == 0 {
		return TransferResult{}, fmt.Errorf("rclone transfer requires at least one source")
	}
	if mode != "push" && mode != "pull" && mode != "sync" {
		return TransferResult{}, fmt.Errorf("unsupported rclone transfer mode %q", mode)
	}
	if mode == "sync" && len(sources) != 1 {
		return TransferResult{}, fmt.Errorf("rclone sync requires exactly one source")
	}
	all := append(append([]string(nil), sources...), destination)
	if err := r.requireConfigForRemote(all...); err != nil {
		return TransferResult{}, err
	}

	mappings := make([]transferMapping, 0, len(sources))
	seenTargets := map[string]string{}
	total := Size{}
	for _, source := range sources {
		entry, size, err := r.Measure(ctx, source)
		if err != nil {
			return TransferResult{}, fmt.Errorf("inspect rclone transfer source: %w", err)
		}
		if mode == "sync" && !entry.IsDir {
			return TransferResult{}, fmt.Errorf("rclone sync requires a directory source")
		}
		total.Files += size.Files
		total.Bytes += size.Bytes
		target := destination
		if mode != "sync" && (!entry.IsDir || len(sources) > 1) {
			target, err = destinationChild(destination, BaseName(source))
			if err != nil {
				return TransferResult{}, err
			}
		}
		targetKey, err := transferTargetKey(target)
		if err != nil {
			return TransferResult{}, err
		}
		if prior, exists := seenTargets[targetKey]; exists {
			return TransferResult{}, fmt.Errorf("rclone transfer would write multiple sources to %s (%s and %s)", target, prior, source)
		}
		seenTargets[targetKey] = source
		mappings = append(mappings, transferMapping{source: source, destination: target, sourceEntry: entry})
	}
	emitTransferProgress(options, Progress{FilesTotal: total.Files, BytesTotal: total.Bytes})

	var done TransferResult
	for _, mapping := range mappings {
		if cancelled(options.Cancelled) {
			return TransferResult{}, context.Canceled
		}
		src, err := commandLocation(mapping.source)
		if err != nil {
			return TransferResult{}, err
		}
		dst, err := commandLocation(mapping.destination)
		if err != nil {
			return TransferResult{}, err
		}
		command := "copy"
		if mode == "sync" {
			command = "sync"
		} else if !mapping.sourceEntry.IsDir {
			command = "copyto"
		}
		args := []string{command, src, dst}
		args = append(args, r.baseArgs()...)
		args = append(args,
			"--use-json-log",
			"--stats", "500ms",
			"--stats-log-level", "NOTICE",
			"--log-level", "NOTICE",
			"--retries", "3",
			"--low-level-retries", "5",
		)
		if !options.Overwrite && mode != "sync" {
			args = append(args, "--ignore-existing")
		}
		if mode == "sync" {
			limit := options.SyncDeleteLimit
			if limit <= 0 {
				limit = 1000
			}
			args = append(args, "--max-delete", fmt.Sprintf("%d", limit))
		}
		last, warnings, err := r.runCommand(ctx, args, options.Cancelled, func(current statsDocument) {
			emitTransferProgress(options, Progress{
				FilesDone:  done.Files + current.Transfers,
				FilesTotal: total.Files,
				BytesDone:  done.Bytes + current.Bytes,
				BytesTotal: total.Bytes,
			})
		})
		if err != nil {
			return TransferResult{}, err
		}
		done.Warnings = append(done.Warnings, warnings...)
		done.Files += max64(last.Transfers, last.TotalTransfers)
		done.Bytes += max64(last.Bytes, last.TotalBytes)
		if options.Verify {
			verifyArgs := []string{"check", src, dst, "--download"}
			if mode != "sync" {
				verifyArgs = append(verifyArgs, "--one-way")
			}
			verifyArgs = append(verifyArgs, r.baseArgs()...)
			verifyArgs = append(verifyArgs, "--log-level", "ERROR")
			if _, warnings, err := r.runCommand(ctx, verifyArgs, options.Cancelled, nil); err != nil {
				return TransferResult{}, fmt.Errorf("rclone verification failed: %w", err)
			} else {
				done.Warnings = append(done.Warnings, warnings...)
			}
		}
	}
	emitTransferProgress(options, Progress{FilesDone: done.Files, FilesTotal: total.Files, BytesDone: done.Bytes, BytesTotal: total.Bytes})
	return done, nil
}

func destinationChild(destination, child string) (string, error) {
	if IsLocation(destination) {
		return JoinURI(destination, child)
	}
	return joinDestination(destination, child)
}

func transferTargetKey(destination string) (string, error) {
	resolved, err := commandLocation(destination)
	if err != nil {
		return "", err
	}
	return resolved, nil
}

func emitTransferProgress(options TransferOptions, progress Progress) {
	if options.Progress != nil {
		options.Progress(progress)
	}
}

func (r Runtime) runCommand(ctx context.Context, args []string, cancelProbe func() bool, progress func(statsDocument)) (statsDocument, []string, error) {
	commandCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	cmd := execCommandContext(commandCtx, r.Executable, args...)
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return statsDocument{}, nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return statsDocument{}, nil, err
	}
	if err := cmd.Start(); err != nil {
		return statsDocument{}, nil, commandError("start rclone", err)
	}

	var wg sync.WaitGroup
	wg.Add(1)
	go func() {
		defer wg.Done()
		_, _ = io.Copy(io.Discard, stdout)
	}()

	cancelDone := make(chan struct{})
	go func() {
		defer close(cancelDone)
		ticker := time.NewTicker(150 * time.Millisecond)
		defer ticker.Stop()
		for {
			select {
			case <-commandCtx.Done():
				return
			case <-ticker.C:
				if cancelled(cancelProbe) {
					cancel()
					return
				}
			}
		}
	}()

	var last statsDocument
	diagnostic := make([]string, 0, 8)
	scanner := bufio.NewScanner(stderr)
	scanner.Buffer(make([]byte, 64*1024), 1024*1024)
	for scanner.Scan() {
		line := scanner.Text()
		var doc logDocument
		if json.Unmarshal([]byte(line), &doc) == nil && doc.Stats != nil {
			last = *doc.Stats
			if progress != nil {
				progress(last)
			}
			continue
		}
		if text := r.sanitizeDiagnostic(line); text != "" {
			diagnostic = append(diagnostic, text)
			if len(diagnostic) > 8 {
				diagnostic = diagnostic[len(diagnostic)-8:]
			}
		}
	}
	waitErr := cmd.Wait()
	wg.Wait()
	cancel()
	<-cancelDone
	if errors.Is(commandCtx.Err(), context.Canceled) && cancelled(cancelProbe) {
		return last, diagnostic, context.Canceled
	}
	if scannerErr := scanner.Err(); scannerErr != nil && waitErr == nil {
		return last, diagnostic, fmt.Errorf("read rclone progress: %w", scannerErr)
	}
	if waitErr != nil {
		message := strings.Join(diagnostic, " | ")
		if message == "" {
			return last, diagnostic, commandError("rclone", waitErr)
		}
		return last, diagnostic, fmt.Errorf("rclone failed: %s", message)
	}
	return last, diagnostic, nil
}

func cancelled(probe func() bool) bool { return probe != nil && probe() }
func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}
