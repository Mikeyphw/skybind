package policy

import (
	"bufio"
	"context"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

// AndroidFacts is a conservative observer. It reports network facts only when
// the live kernel route and corresponding link type can be corroborated.
// It never guesses metering (which requires Android connectivity APIs).
func AndroidFacts(cachePath string) Facts {
	f := Facts{Network: Unknown}
	route, err := os.Open("/proc/net/route")
	if err == nil {
		defer route.Close()
		sc := bufio.NewScanner(route)
		for sc.Scan() {
			fields := strings.Fields(sc.Text())
			if len(fields) < 4 || fields[1] != "00000000" || fields[0] == "Iface" {
				continue
			}
			iface := fields[0]
			flags, e := strconv.ParseUint(fields[3], 16, 64)
			if e != nil || flags&1 == 0 {
				continue
			}
			link, e := os.ReadFile(filepath.Join("/sys/class/net", iface, "operstate"))
			if e != nil || strings.TrimSpace(string(link)) != "up" {
				continue
			}
			switch {
			case strings.HasPrefix(iface, "wlan"), strings.HasPrefix(iface, "wifi"):
				f.Network = WiFi
			case strings.HasPrefix(iface, "rmnet"), strings.HasPrefix(iface, "ccmni"), strings.HasPrefix(iface, "pdp"):
				f.Network = Cellular
			default:
				f.Network = Unknown
			}
			break
		}
	}
	if b, e := os.ReadFile("/sys/class/power_supply/battery/capacity"); e == nil {
		if n, err := strconv.Atoi(strings.TrimSpace(string(b))); err == nil && n >= 0 && n <= 100 {
			f.Battery = &n
		}
	}
	if b, e := os.ReadFile("/sys/class/power_supply/battery/status"); e == nil {
		s := strings.ToLower(strings.TrimSpace(string(b)))
		if s == "charging" || s == "full" || s == "discharging" || s == "not charging" {
			v := s == "charging" || s == "full"
			f.Charging = &v
		}
	}
	var st syscall.Statfs_t
	if err := syscall.Statfs(cachePath, &st); err == nil {
		n := int64(st.Bavail) * int64(st.Bsize)
		if n >= 0 {
			f.CacheFreeBytes = &n
		}
	}
	if b, e := os.ReadFile("/proc/uptime"); e == nil {
		parts := strings.Fields(string(b))
		if len(parts) > 0 {
			secs, e := strconv.ParseFloat(parts[0], 64)
			if e == nil && secs >= 0 {
				f.BootAt = time.Now().Add(-time.Duration(secs * float64(time.Second)))
			}
		}
	}
	// Metered state is obtained from Android's *active default network* only.
	// A Wi-Fi interface by itself does not prove an unmetered connection.
	if runtime.GOOS == "android" && f.Network != Unknown && f.Network != Offline {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		cmd := exec.CommandContext(ctx, "/system/bin/dumpsys", "connectivity")
		cmd.Env = []string{"PATH=/system/bin:/system/xbin"}
		cmd.Stderr = io.Discard
		pipe, err := cmd.StdoutPipe()
		if err == nil && cmd.Start() == nil {
			out, e := io.ReadAll(io.LimitReader(pipe, (1<<20)+1))
			if len(out) > 1<<20 || e != nil {
				_ = cmd.Process.Kill()
			}
			waitErr := cmd.Wait()
			if e == nil && waitErr == nil && ctx.Err() == nil && len(out) <= 1<<20 {
				f.Metered = parseActiveMetered(out)
			}
		}
	}
	// NetworkAt is deliberately not set by this stateless observer: only the
	// daemon-lifetime sampler may establish an observed transition timestamp.
	return f
}

var sampler struct {
	sync.Mutex
	network  Network
	metering string
	since    time.Time
}

// SampleAndroidFacts persists the instant a network class was first observed
// by this daemon. Unknown changes reset readiness instead of inventing uptime.
func SampleAndroidFacts(cachePath string) Facts {
	f := AndroidFacts(cachePath)
	sampler.Lock()
	defer sampler.Unlock()
	stamp := "unknown"
	if f.Metered != nil {
		if *f.Metered {
			stamp = "metered"
		} else {
			stamp = "unmetered"
		}
	}
	if sampler.network != f.Network || sampler.metering != stamp || sampler.since.IsZero() {
		sampler.network = f.Network
		sampler.metering = stamp
		sampler.since = time.Now()
	}
	if f.Network != Unknown && f.Network != Offline {
		f.NetworkAt = sampler.since
	}
	return f
}

// parseActiveMetered never guesses from a nearby non-default network. The
// active network id must match exactly one NetworkAgentInfo and its single
// capabilities declaration. Any incomplete or ambiguous evidence is unknown.
var activeDefaultRE = regexp.MustCompile(`(?m)^\s*Active default network:\s*(?:Network\s*)?(\d+)\b`)
var agentIDRE = regexp.MustCompile(`\bnetwork\{(\d+)\}`)

func parseActiveMetered(raw []byte) *bool {
	if len(raw) == 0 || len(raw) > 1<<20 {
		return nil
	}
	text := string(raw)
	matches := activeDefaultRE.FindAllStringSubmatch(text, -1)
	if len(matches) != 1 {
		return nil
	}
	id := matches[0][1]
	lines := strings.Split(text, "\n")
	agents := 0
	result := false
	found := false
	for i, line := range lines {
		if !strings.Contains(line, "NetworkAgentInfo") {
			continue
		}
		ids := agentIDRE.FindStringSubmatch(line)
		if ids == nil || ids[1] != id {
			continue
		}
		agents++
		if agents > 1 {
			return nil
		}
		// NetworkAgentInfo capabilities are bounded to its block, never another
		// agent's capabilities or a VPN/underlying network.
		for j := i; j < len(lines) && j < i+18; j++ {
			if j > i && strings.Contains(lines[j], "NetworkAgentInfo") {
				break
			}
			capLine := lines[j]
			at := strings.Index(capLine, "Capabilities:")
			if at < 0 {
				continue
			}
			capLine = capLine[at+len("Capabilities:"):]
			if found {
				return nil
			}
			found = true
			// A bounded word token prevents unrelated capability descriptions from
			// advertising NOT_METERED for this network.
			result = true
			for _, token := range strings.FieldsFunc(capLine, func(r rune) bool { return !(r >= 'A' && r <= 'Z' || r == '_' || r >= '0' && r <= '9') }) {
				if token == "NOT_METERED" {
					result = false
				}
			}
		}
	}
	if agents != 1 || !found {
		return nil
	}
	return &result
}
