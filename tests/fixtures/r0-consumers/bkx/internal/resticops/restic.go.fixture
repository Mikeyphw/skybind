package resticops

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync/atomic"
	"time"

	"bkx/internal/berror"
	"bkx/internal/models"
	"bkx/internal/rcloneops"
	"bkx/internal/runstore"
)

var ErrCancelled = errors.New("restic backup cancelled")

type Runner interface {
	Run(args []string, env []string) (stdout []byte, stderr []byte, err error)
}

// StreamingRunner is implemented by runners that can surface JSON-lines progress
// while a long-running Restic command is still executing. Test runners may keep
// implementing Runner only; RestoreSnapshot falls back to buffered parsing.
type StreamingRunner interface {
	RunStreaming(args []string, env []string, cancelled func() bool, onStdoutLine func([]byte)) (stderr []byte, err error)
}

type ExecRunner struct{ Path string }

func (r ExecRunner) Run(args []string, env []string) ([]byte, []byte, error) {
	cmd := exec.Command(r.Path, args...)
	cmd.Env = env
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	err := cmd.Run()
	return stdout.Bytes(), stderr.Bytes(), err
}

func (r ExecRunner) RunStreaming(args []string, env []string, cancelled func() bool, onStdoutLine func([]byte)) ([]byte, error) {
	cmd := exec.Command(r.Path, args...)
	cmd.Env = env
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	var stderr bytes.Buffer
	cmd.Stderr = &stderr
	if err := cmd.Start(); err != nil {
		return stderr.Bytes(), err
	}
	var cancelledByCaller atomic.Bool
	done := make(chan struct{})
	if cancelled != nil {
		go func() {
			ticker := time.NewTicker(100 * time.Millisecond)
			defer ticker.Stop()
			for {
				select {
				case <-done:
					return
				case <-ticker.C:
					if cancelled() {
						cancelledByCaller.Store(true)
						_ = cmd.Process.Kill()
						return
					}
				}
			}
		}()
	}
	scanner := bufio.NewScanner(stdout)
	scanner.Buffer(make([]byte, 64*1024), 4*1024*1024)
	for scanner.Scan() {
		if onStdoutLine != nil {
			line := append([]byte(nil), scanner.Bytes()...)
			onStdoutLine(line)
		}
	}
	scanErr := scanner.Err()
	waitErr := cmd.Wait()
	close(done)
	if cancelledByCaller.Load() {
		return stderr.Bytes(), ErrCancelled
	}
	if scanErr != nil {
		return stderr.Bytes(), scanErr
	}
	return stderr.Bytes(), waitErr
}

type Options struct {
	Runner    Runner
	Environ   []string
	RunStore  *runstore.Store
	RunID     string
	RunOrigin *runstore.SavedJobOrigin
	Cancelled func() bool
	Progress  func(ProgressEvent)
}

type ProgressEvent struct {
	Stage      string   `json:"stage"`
	Files      int64    `json:"files"`
	Bytes      int64    `json:"bytes"`
	TotalFiles int64    `json:"total_files,omitempty"`
	TotalBytes int64    `json:"total_bytes,omitempty"`
	Progress   *float64 `json:"progress,omitempty"`
}

type Plan struct {
	Engine     string   `json:"engine"`
	Repository string   `json:"repository"`
	Sources    []string `json:"sources"`
	Excludes   []string `json:"excludes"`
	Tags       []string `json:"tags"`
	Verify     bool     `json:"verify"`
	DryRun     bool     `json:"dry_run"`
	Warnings   []string `json:"warnings"`
}

type BackupResult struct {
	Success            bool     `json:"success"`
	Engine             string   `json:"engine"`
	Repository         string   `json:"repository"`
	SnapshotID         string   `json:"snapshot_id,omitempty"`
	FilesProcessed     int64    `json:"files_processed"`
	BytesProcessed     int64    `json:"bytes_processed"`
	DataAdded          int64    `json:"data_added"`
	VerificationPassed *bool    `json:"verification_passed,omitempty"`
	Warnings           []string `json:"warnings"`
	DurationMS         int64    `json:"duration_ms"`
}

type RepositoryResult struct {
	Success    bool   `json:"success"`
	Engine     string `json:"engine"`
	Repository string `json:"repository"`
	Created    bool   `json:"created"`
}

type summaryMessage struct {
	MessageType         string `json:"message_type"`
	SnapshotID          string `json:"snapshot_id"`
	TotalFilesProcessed int64  `json:"total_files_processed"`
	TotalBytesProcessed int64  `json:"total_bytes_processed"`
	DataAdded           int64  `json:"data_added"`
}

type statusMessage struct {
	MessageType string  `json:"message_type"`
	FilesDone   int64   `json:"files_done"`
	BytesDone   int64   `json:"bytes_done"`
	PercentDone float64 `json:"percent_done"`
}

func ResolveRunner(options Options) (Runner, error) {
	if options.Runner != nil {
		return options.Runner, nil
	}
	env := options.Environ
	if len(env) == 0 {
		env = os.Environ()
	}
	path := strings.TrimSpace(environmentValue(env, "BKX_RESTIC_PATH"))
	if path == "" {
		located, err := exec.LookPath("restic")
		if err != nil {
			return nil, berror.External("restic is required for incremental snapshot backups", map[string]any{"tool": "restic", "action": "Install restic and ensure it is available on PATH, or set BKX_RESTIC_PATH."})
		}
		path = located
	}
	absolute, err := filepath.Abs(path)
	if err != nil {
		return nil, berror.External("restic runtime path is invalid", map[string]any{"tool": "restic", "reason": err.Error()})
	}
	info, err := os.Stat(absolute)
	if err != nil || info.IsDir() || info.Mode()&0o111 == 0 {
		return nil, berror.External("restic runtime is not executable", map[string]any{"tool": "restic", "path": absolute})
	}
	return ExecRunner{Path: absolute}, nil
}

// NormalizeRepository accepts local filesystem repositories and BKX canonical
// rclone://remote/path repositories. Native restic rclone: syntax is kept out
// of saved specs so credentials/userinfo cannot be smuggled through backend URLs.
func NormalizeRepository(raw string) (string, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return "", berror.Validation("Restic repository must not be empty", nil)
	}
	if rcloneops.IsLocation(value) {
		canonical, err := rcloneops.CanonicalURI(value)
		if err != nil {
			return "", berror.Validation("Invalid rclone Restic repository", map[string]any{"repository": value, "reason": err.Error()})
		}
		return canonical, nil
	}
	lower := strings.ToLower(value)
	if strings.Contains(value, "://") || strings.HasPrefix(lower, "rclone:") || strings.HasPrefix(lower, "s3:") || strings.HasPrefix(lower, "sftp:") || strings.HasPrefix(lower, "b2:") || strings.HasPrefix(lower, "azure:") || strings.HasPrefix(lower, "gs:") {
		return "", berror.Validation("BKX remote Restic repositories must use rclone://remote/path; provider credentials stay in rclone configuration", map[string]any{"repository": value})
	}
	abs, err := filepath.Abs(value)
	if err != nil {
		return "", berror.Validation("Invalid local Restic repository path", map[string]any{"repository": value, "reason": err.Error()})
	}
	return filepath.Clean(abs), nil
}

func NormalizeLocalRepository(raw string) (string, error) {
	repository, err := NormalizeRepository(raw)
	if err != nil {
		return "", err
	}
	if rcloneops.IsLocation(repository) {
		return "", berror.Validation("Expected a local Restic repository path", map[string]any{"repository": repository})
	}
	return repository, nil
}

func commandRepository(repository string) (string, error) {
	if !rcloneops.IsLocation(repository) {
		return repository, nil
	}
	native, err := rcloneops.NormalizeLocation(repository)
	if err != nil {
		return "", err
	}
	return "rclone:" + native, nil
}

func environmentValue(env []string, key string) string {
	prefix := key + "="
	for i := len(env) - 1; i >= 0; i-- {
		if strings.HasPrefix(env[i], prefix) {
			return strings.TrimPrefix(env[i], prefix)
		}
	}
	return ""
}

func setEnvironmentValue(env []string, key, value string) []string {
	prefix := key + "="
	out := make([]string, 0, len(env)+1)
	for _, item := range env {
		if !strings.HasPrefix(item, prefix) {
			out = append(out, item)
		}
	}
	return append(out, key+"="+value)
}

func lookupEnvironmentValue(env []string, key string) (string, bool) {
	prefix := key + "="
	for i := len(env) - 1; i >= 0; i-- {
		if strings.HasPrefix(env[i], prefix) {
			value := strings.TrimPrefix(env[i], prefix)
			return value, strings.TrimSpace(value) != ""
		}
	}
	return "", false
}

func removeEnvironmentKeys(env []string, keys ...string) []string {
	blocked := map[string]bool{}
	for _, key := range keys {
		blocked[key+"="] = true
	}
	out := make([]string, 0, len(env))
	for _, item := range env {
		remove := false
		for prefix := range blocked {
			if strings.HasPrefix(item, prefix) {
				remove = true
				break
			}
		}
		if !remove {
			out = append(out, item)
		}
	}
	return out
}

// repositoryInvocation translates BKX's non-secret repository URI into the
// restic process form and injects only runtime/config paths for rclone. The
// rclone config contents (OAuth tokens, provider secrets) are never copied into
// a job, run snapshot, command argument, or diagnostic.
func repositoryInvocation(repository string, baseEnv []string) (string, []string, []string, error) {
	commandRepo, err := commandRepository(repository)
	if err != nil {
		return "", nil, nil, err
	}
	env := append([]string(nil), baseEnv...)
	if len(env) == 0 {
		env = os.Environ()
	}
	if !rcloneops.IsLocation(repository) {
		return commandRepo, nil, env, nil
	}
	runtime, err := rcloneops.RuntimeFromEnviron(env)
	if err != nil {
		return "", nil, nil, berror.External("rclone is required for this Restic repository", map[string]any{"tool": "rclone", "repository": repository, "reason": err.Error()})
	}
	if runtime.Config != "" {
		info, statErr := os.Stat(runtime.Config)
		if statErr != nil || info.IsDir() || info.Size() == 0 {
			return "", nil, nil, berror.External("rclone config is unavailable for this Restic repository", map[string]any{"tool": "rclone", "repository": repository})
		}
		env = setEnvironmentValue(env, "RCLONE_CONFIG", runtime.Config)
	}
	return commandRepo, []string{"-o", "rclone.program=" + runtime.Executable}, env, nil
}

func credentialEnvironment(base []string, ref *string) ([]string, error) {
	env := append([]string(nil), base...)
	if len(env) == 0 {
		env = os.Environ()
	}
	if ref != nil {
		id := *ref
		secretKey, err := models.CredentialEnvironmentKey(id)
		if err != nil {
			return nil, berror.Validation("Invalid Restic credential reference", map[string]any{"credential_ref": id, "reason": err.Error()})
		}
		fileKey, err := models.CredentialFileEnvironmentKey(id)
		if err != nil {
			return nil, berror.Validation("Invalid Restic credential reference", map[string]any{"credential_ref": id, "reason": err.Error()})
		}
		secret, hasSecret := lookupEnvironmentValue(env, secretKey)
		file, hasFile := lookupEnvironmentValue(env, fileKey)
		if hasSecret && hasFile {
			return nil, berror.Validation("Restic credential reference resolves to competing password channels", map[string]any{"credential_ref": id, "password_env": secretKey, "password_file_env": fileKey})
		}
		env = removeEnvironmentKeys(env, "RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE")
		if hasSecret {
			return append(env, "RESTIC_PASSWORD="+secret), nil
		}
		if hasFile {
			return append(env, "RESTIC_PASSWORD_FILE="+strings.TrimSpace(file)), nil
		}
		return nil, berror.Validation("Restic credential reference is unresolved", map[string]any{"credential_ref": id, "expected_env": secretKey})
	}
	_, hasPassword := lookupEnvironmentValue(env, "RESTIC_PASSWORD")
	_, hasPasswordFile := lookupEnvironmentValue(env, "RESTIC_PASSWORD_FILE")
	if hasPassword && hasPasswordFile {
		return nil, berror.Validation("Restic password must use exactly one direct channel", map[string]any{"password_env": "RESTIC_PASSWORD", "password_file_env": "RESTIC_PASSWORD_FILE"})
	}
	if hasPassword || hasPasswordFile {
		return env, nil
	}
	return nil, berror.Validation("Restic requires a password supplied outside the operation spec", map[string]any{"action": "Set RESTIC_PASSWORD/RESTIC_PASSWORD_FILE or use --credential-ref with BKX_CREDENTIAL_<ID>."})
}

func Init(spec models.RepositoryInitSpec, options Options) (RepositoryResult, error) {
	if err := models.ValidateRepositoryInitSpec(spec); err != nil {
		return RepositoryResult{}, berror.Validation("Invalid repository init specification", map[string]any{"reason": err.Error()})
	}
	repo, err := NormalizeRepository(spec.Repository)
	if err != nil {
		return RepositoryResult{}, err
	}
	runner, err := ResolveRunner(options)
	if err != nil {
		return RepositoryResult{}, err
	}
	env, err := credentialEnvironment(options.Environ, spec.CredentialRef)
	if err != nil {
		return RepositoryResult{}, err
	}
	commandRepo, backendArgs, env, err := repositoryInvocation(repo, env)
	if err != nil {
		return RepositoryResult{}, err
	}
	if !rcloneops.IsLocation(repo) {
		if err := os.MkdirAll(filepath.Dir(repo), 0o700); err != nil {
			return RepositoryResult{}, berror.WrapExternal("creating Restic repository parent", filepath.Dir(repo), "filesystem", err)
		}
	}
	args := append([]string{}, backendArgs...)
	args = append(args, "--repo", commandRepo, "init")
	_, stderr, runErr := runner.Run(args, env)
	if runErr != nil {
		return RepositoryResult{}, external("initializing Restic repository", repo, stderr, runErr)
	}
	return RepositoryResult{Success: true, Engine: models.BackupEngineRestic, Repository: repo, Created: true}, nil
}

func PlanBackup(spec models.SnapshotBackupSpec) (Plan, error) {
	normalized, err := normalizeBackup(spec)
	if err != nil {
		return Plan{}, err
	}
	warnings := []string{}
	if rcloneops.IsLocation(normalized.Repository) {
		warnings = append(warnings, "Remote snapshot uses restic's rclone backend; provider credentials remain in rclone configuration.")
	}
	if normalized.Verify {
		warnings = append(warnings, "Repository verification runs after the snapshot; full data-read verification is reserved for repository maintenance.")
	}
	return Plan{Engine: models.BackupEngineRestic, Repository: normalized.Repository, Sources: normalized.Sources, Excludes: normalized.Excludes, Tags: normalized.Tags, Verify: normalized.Verify, DryRun: true, Warnings: warnings}, nil
}

func Backup(spec models.SnapshotBackupSpec, options Options) (BackupResult, error) {
	started := time.Now()
	normalized, err := normalizeBackup(spec)
	if err != nil {
		return BackupResult{}, err
	}
	if normalized.DryRun {
		return BackupResult{Success: true, Engine: models.BackupEngineRestic, Repository: normalized.Repository, Warnings: []string{}, DurationMS: time.Since(started).Milliseconds()}, nil
	}
	runner, err := ResolveRunner(options)
	if err != nil {
		return BackupResult{}, err
	}
	env, err := credentialEnvironment(options.Environ, normalized.CredentialRef)
	if err != nil {
		return BackupResult{}, err
	}
	commandRepo, backendArgs, env, err := repositoryInvocation(normalized.Repository, env)
	if err != nil {
		return BackupResult{}, err
	}
	runID := options.RunID
	if runID == "" {
		runID = randomRunID()
	}
	options.RunID = runID
	destination := normalized.Repository
	if options.RunStore != nil {
		snapshot := map[string]any{
			"engine": models.BackupEngineRestic, "repository": normalized.Repository,
			"sources": append([]string(nil), normalized.Sources...), "excludes": append([]string(nil), normalized.Excludes...),
			"includes": append([]string(nil), normalized.Includes...), "tags": append([]string(nil), normalized.Tags...),
			"verify": normalized.Verify, "dry_run": false,
		}
		if normalized.CredentialRef != nil {
			snapshot["credential_ref"] = *normalized.CredentialRef
		}
		if _, err := options.RunStore.RecordStartWithOrigin(runID, "backup", normalized.Sources, &destination, nil, snapshot, options.RunOrigin); err != nil {
			return BackupResult{}, err
		}
		_, _ = options.RunStore.RecordPhase(runID, "preparing")
	}
	complete := func(status string, result *BackupResult, opErr error) {
		if options.RunStore == nil {
			return
		}
		var files, bytes *int64
		var msg *string
		if result != nil {
			files = ptr(result.FilesProcessed)
			bytes = ptr(result.BytesProcessed)
		}
		if opErr != nil {
			text := opErr.Error()
			msg = &text
		}
		_, _ = options.RunStore.RecordCompletion(runID, status, files, bytes, msg)
	}
	if options.Cancelled != nil && options.Cancelled() {
		complete("cancelled", nil, ErrCancelled)
		return BackupResult{}, ErrCancelled
	}
	args := []string{"--json"}
	args = append(args, backendArgs...)
	args = append(args, "--repo", commandRepo, "backup")
	for _, pattern := range normalized.Excludes {
		args = append(args, "--exclude", pattern)
	}
	for _, tag := range normalized.Tags {
		args = append(args, "--tag", tag)
	}
	args = append(args, normalized.Sources...)
	emit(options, "snapshotting", 0, 0)
	unlockBase := append([]string{}, backendArgs...)
	unlockBase = append(unlockBase, "--repo", commandRepo)
	stdout, stderr, runErr := runWithStaleLockRecovery(runner, args, env, unlockBase, options.Cancelled, func(stage string) {
		emit(options, stage, 0, 0)
	}, func(line []byte) { emitBackupProgressLine(line, options) })
	if runErr != nil {
		if errors.Is(runErr, ErrCancelled) {
			complete("cancelled", nil, ErrCancelled)
			return BackupResult{}, ErrCancelled
		}
		wrapped := external("creating Restic snapshot", normalized.Repository, stderr, runErr)
		complete("failed", nil, wrapped)
		return BackupResult{}, wrapped
	}
	summary, err := parseBackupJSON(stdout, options)
	if err != nil {
		complete("failed", nil, err)
		return BackupResult{}, err
	}
	result := BackupResult{Success: true, Engine: models.BackupEngineRestic, Repository: normalized.Repository, SnapshotID: summary.SnapshotID, FilesProcessed: summary.TotalFilesProcessed, BytesProcessed: summary.TotalBytesProcessed, DataAdded: summary.DataAdded, Warnings: []string{}}
	if normalized.Verify {
		emit(options, "verifying", result.FilesProcessed, result.BytesProcessed)
		checkArgs := append([]string{}, backendArgs...)
		checkArgs = append(checkArgs, "--repo", commandRepo, "check")
		_, checkErrText, checkErr := runWithStaleLockRecovery(runner, checkArgs, env, unlockBase, options.Cancelled, func(stage string) {
			emit(options, stage, result.FilesProcessed, result.BytesProcessed)
		}, nil)
		ok := checkErr == nil
		result.VerificationPassed = &ok
		if checkErr != nil {
			if errors.Is(checkErr, ErrCancelled) {
				result.Success = false
				result.DurationMS = time.Since(started).Milliseconds()
				complete("cancelled", &result, ErrCancelled)
				return result, ErrCancelled
			}
			wrapped := external("checking Restic repository", normalized.Repository, checkErrText, checkErr)
			result.Success = false
			result.DurationMS = time.Since(started).Milliseconds()
			complete("failed", &result, wrapped)
			return result, wrapped
		}
	}
	result.DurationMS = time.Since(started).Milliseconds()
	emit(options, "finalizing", result.FilesProcessed, result.BytesProcessed)
	complete("success", &result, nil)
	return result, nil
}

func normalizeBackup(spec models.SnapshotBackupSpec) (models.SnapshotBackupSpec, error) {
	if strings.TrimSpace(spec.Engine) == "" {
		spec.Engine = models.BackupEngineRestic
	}
	if err := models.ValidateSnapshotBackupSpec(spec); err != nil {
		return spec, berror.Validation("Invalid Restic snapshot backup specification", map[string]any{"reason": err.Error()})
	}
	if len(spec.Includes) > 0 {
		return spec, berror.Validation("Restic include filters are not enabled yet; use explicit sources plus exclusions", map[string]any{"includes": spec.Includes})
	}
	repo, err := NormalizeRepository(spec.Repository)
	if err != nil {
		return spec, err
	}
	spec.Repository = repo
	seen := map[string]bool{}
	sources := make([]string, 0, len(spec.Sources))
	for _, raw := range spec.Sources {
		abs, err := filepath.Abs(strings.TrimSpace(raw))
		if err != nil {
			return spec, berror.Validation("Invalid snapshot source path", map[string]any{"source": raw})
		}
		abs = filepath.Clean(abs)
		st, err := os.Stat(abs)
		if err != nil {
			if os.IsNotExist(err) {
				return spec, berror.NotFound("Snapshot source does not exist: "+abs, map[string]any{"source": abs})
			}
			return spec, berror.WrapExternal("checking snapshot source", abs, "filesystem", err)
		}
		if !st.IsDir() && !st.Mode().IsRegular() {
			return spec, berror.Validation("Snapshot source must be a file or directory", map[string]any{"source": abs})
		}
		if seen[abs] {
			return spec, berror.Validation("Duplicate snapshot sources are not allowed", map[string]any{"source": abs})
		}
		seen[abs] = true
		sources = append(sources, abs)
	}
	spec.Sources = sources
	return spec, nil
}

func parseBackupJSON(data []byte, options Options) (summaryMessage, error) {
	var summary summaryMessage
	for _, line := range bytes.Split(data, []byte{'\n'}) {
		line = bytes.TrimSpace(line)
		if len(line) == 0 {
			continue
		}
		var head struct {
			MessageType string `json:"message_type"`
		}
		if json.Unmarshal(line, &head) != nil {
			continue
		}
		switch head.MessageType {
		case "status":
			var status statusMessage
			if json.Unmarshal(line, &status) == nil {
				emit(options, "snapshotting", status.FilesDone, status.BytesDone)
			}
		case "summary":
			_ = json.Unmarshal(line, &summary)
		}
	}
	if summary.MessageType != "summary" || strings.TrimSpace(summary.SnapshotID) == "" {
		return summary, berror.External("Restic backup completed without a snapshot summary", map[string]any{"tool": "restic"})
	}
	return summary, nil
}

func emit(options Options, stage string, files, bytes int64) {
	if options.RunStore != nil && options.RunID != "" {
		phase := "running"
		switch stage {
		case "recovering_stale_lock":
			phase = "preparing"
		case "verifying":
			phase = "verifying"
		case "finalizing":
			phase = "finalizing"
		}
		_, _ = options.RunStore.RecordPhase(options.RunID, phase)
	}
	if options.Progress != nil {
		options.Progress(ProgressEvent{Stage: stage, Files: files, Bytes: bytes})
	}
}

// runWithStaleLockRecovery retries an operation once after asking Restic to
// remove only stale locks. It intentionally never uses `unlock --remove-all`,
// because another BKX/client process may legitimately own a live repository lock.
func runWithStaleLockRecovery(
	runner Runner,
	args []string,
	env []string,
	unlockBase []string,
	cancelled func() bool,
	onRecovery func(string),
	onStdoutLine func([]byte),
) ([]byte, []byte, error) {
	stdout, stderr, runErr := runResticCommand(runner, args, env, cancelled, onStdoutLine)
	if runErr == nil || !isRepositoryLockError(stderr) || (cancelled != nil && cancelled()) {
		return stdout, stderr, runErr
	}
	if onRecovery != nil {
		onRecovery("recovering_stale_lock")
	}
	unlockArgs := append([]string{}, unlockBase...)
	unlockArgs = append(unlockArgs, "unlock")
	_, unlockStderr, unlockErr := runResticCommand(runner, unlockArgs, env, cancelled, nil)
	if unlockErr != nil {
		return stdout, append(stderr, unlockStderr...), runErr
	}
	if onRecovery != nil {
		onRecovery("retrying_operation")
	}
	return runResticCommand(runner, args, env, cancelled, onStdoutLine)
}

// runResticCommand uses Restic's streaming runner whenever available so a
// caller can cancel a long-running backup/check/prune and Android/Tasker can
// receive progress before process completion. Buffered test runners and custom
// integrations continue to work through the legacy Runner contract.
func runResticCommand(runner Runner, args []string, env []string, cancelled func() bool, onStdoutLine func([]byte)) ([]byte, []byte, error) {
	if streaming, ok := runner.(StreamingRunner); ok {
		var stdout bytes.Buffer
		stderr, err := streaming.RunStreaming(args, env, cancelled, func(line []byte) {
			stdout.Write(line)
			stdout.WriteByte('\n')
			if onStdoutLine != nil {
				onStdoutLine(line)
			}
		})
		return stdout.Bytes(), stderr, err
	}
	return runner.Run(args, env)
}

func emitBackupProgressLine(line []byte, options Options) {
	var status statusMessage
	if json.Unmarshal(bytes.TrimSpace(line), &status) == nil && status.MessageType == "status" {
		emit(options, "snapshotting", status.FilesDone, status.BytesDone)
	}
}

func isRepositoryLockError(stderr []byte) bool {
	text := strings.ToLower(string(stderr))
	return strings.Contains(text, "repository is already locked") ||
		strings.Contains(text, "repository already locked") ||
		strings.Contains(text, "unable to create lock")
}
func ptr(v int64) *int64 { return &v }
func randomRunID() string {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err == nil {
		return hex.EncodeToString(b)
	}
	return fmt.Sprintf("restic-%d", time.Now().UnixNano())
}
func external(action, resource string, stderr []byte, err error) error {
	text := strings.TrimSpace(string(stderr))
	details := map[string]any{"tool": "restic", "resource": resource, "reason": err.Error(), "error_type": "tool_exit"}
	if code := toolExitCode(err); code != nil {
		details["tool_exit_code"] = *code
	}
	if text != "" {
		details["stderr"] = text
		details["tool_stderr"] = text
	}
	return berror.External("Restic failed while "+action, details)
}

func toolExitCode(err error) *int {
	type exitCoder interface{ ExitCode() int }
	var coder exitCoder
	if errors.As(err, &coder) {
		code := coder.ExitCode()
		return &code
	}
	return nil
}
