package rcloneops

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

type Runtime struct {
	Executable string
	Config     string
}

type RuntimeInfo struct {
	Version string
}

func RuntimeFromEnvironment() (Runtime, error) {
	return RuntimeFromEnviron(os.Environ())
}

// RuntimeFromEnviron resolves BKX's rclone runtime from an explicit environment.
// Restic uses this so its child rclone process receives the same app-private
// runtime/config bindings as direct BKX transfers without reading secret config
// contents into operation specifications or diagnostics.
func RuntimeFromEnviron(environ []string) (Runtime, error) {
	lookup := func(key string) string {
		prefix := key + "="
		for i := len(environ) - 1; i >= 0; i-- {
			if strings.HasPrefix(environ[i], prefix) {
				return strings.TrimSpace(strings.TrimPrefix(environ[i], prefix))
			}
		}
		return ""
	}
	candidate := lookup("BKX_RCLONE_PATH")
	if candidate == "" {
		located, err := exec.LookPath("rclone")
		if err != nil {
			return Runtime{}, fmt.Errorf("rclone runtime is unavailable")
		}
		candidate = located
	}
	absolute, err := filepath.Abs(candidate)
	if err != nil {
		return Runtime{}, fmt.Errorf("resolve rclone runtime: %w", err)
	}
	info, err := os.Stat(absolute)
	if err != nil || info.IsDir() || info.Mode()&0o111 == 0 {
		return Runtime{}, fmt.Errorf("rclone runtime is not executable: %s", absolute)
	}
	config := lookup("BKX_RCLONE_CONFIG")
	if config != "" {
		configAbs, err := filepath.Abs(config)
		if err != nil {
			return Runtime{}, fmt.Errorf("resolve rclone config: %w", err)
		}
		config = configAbs
	}
	return Runtime{Executable: absolute, Config: config}, nil
}

func Available() bool {
	_, err := RuntimeFromEnvironment()
	return err == nil
}

func Configured() bool {
	runtime, err := RuntimeFromEnvironment()
	if err != nil {
		return false
	}
	return runtime.Configured()
}

func (r Runtime) Configured() bool {
	names, err := r.ConfiguredRemoteNames()
	return err == nil && len(names) > 0
}

func (r Runtime) Probe(ctx context.Context) (RuntimeInfo, error) {
	probeCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	args := append([]string{"version"}, r.baseArgs()...)
	out, err := exec.CommandContext(probeCtx, r.Executable, args...).CombinedOutput()
	if err != nil {
		return RuntimeInfo{}, commandError("rclone version", err)
	}
	first := strings.TrimSpace(strings.SplitN(string(out), "\n", 2)[0])
	if !strings.HasPrefix(first, "rclone v") {
		return RuntimeInfo{}, fmt.Errorf("unexpected rclone version output")
	}
	return RuntimeInfo{Version: strings.TrimPrefix(first, "rclone ")}, nil
}

func (r Runtime) requireConfigForRemote(values ...string) error {
	remotes := remoteNamesUsedBy(values...)
	if len(remotes) == 0 {
		return nil
	}
	if r.Config == "" {
		return nil // normal CLI installs may rely on rclone's standard config path
	}
	configured, err := r.ConfiguredRemoteNames()
	if err != nil {
		return err
	}
	for remote := range remotes {
		if !configured[remote] {
			return fmt.Errorf("rclone remote %q is not configured in BKX rclone config; import or refresh rclone.conf before using this remote", remote)
		}
	}
	return nil
}

func (r Runtime) ConfiguredRemoteNames() (map[string]bool, error) {
	if r.Config == "" {
		return nil, fmt.Errorf("BKX rclone config path is not configured")
	}
	info, err := os.Stat(r.Config)
	if err != nil || info.IsDir() || info.Size() == 0 {
		return nil, fmt.Errorf("rclone config is unavailable; import rclone.conf in BKX before using a remote")
	}
	data, err := os.ReadFile(r.Config)
	if err != nil {
		return nil, fmt.Errorf("read BKX rclone config: %w", err)
	}
	return remoteNamesInConfig(string(data)), nil
}

func remoteNamesUsedBy(values ...string) map[string]bool {
	remotes := map[string]bool{}
	for _, value := range values {
		parsed, err := parseLocation(value)
		if err == nil {
			remotes[parsed.remote] = true
		}
	}
	return remotes
}

func remoteNamesInConfig(text string) map[string]bool {
	result := map[string]bool{}
	for _, raw := range strings.Split(text, "\n") {
		line := strings.TrimSpace(raw)
		if len(line) < 3 || !strings.HasPrefix(line, "[") || !strings.Contains(line, "]") {
			continue
		}
		name := strings.TrimSpace(line[1:strings.Index(line, "]")])
		if safeRemoteName.MatchString(name) {
			result[name] = true
		}
	}
	return result
}

func (r Runtime) baseArgs() []string {
	if r.Config == "" {
		return nil
	}
	return []string{"--config", r.Config}
}

func commandError(action string, err error) error {
	var exit *exec.ExitError
	if errors.As(err, &exit) {
		return fmt.Errorf("%s exited with status %d", action, exit.ExitCode())
	}
	return fmt.Errorf("%s: %w", action, err)
}

var secretDiagnosticPattern = regexp.MustCompile(`(?i)(token|password|client_secret|access_token|refresh_token|client_id|secret_access_key|access_key_id)\s*(=|:)\s*("[^"]*"|'[^']*'|[^&\s,}]+)`)

func (r Runtime) sanitizeDiagnostic(value string) string {
	text := strings.TrimSpace(value)
	if r.Config != "" {
		text = strings.ReplaceAll(text, r.Config, "<rclone-config>")
	}
	text = secretDiagnosticPattern.ReplaceAllString(text, "$1$2<redacted>")
	return text
}
