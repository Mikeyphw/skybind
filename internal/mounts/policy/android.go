package policy

import (
	"bufio"
	"os"
	"path/filepath"
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
	if f.Network != Unknown && f.Network != Offline {
		f.NetworkAt = time.Now().Add(-time.Hour)
	} // readiness observed now, avoid fabricating network age
	return f
}

var sampler struct {
	sync.Mutex
	network Network
	since   time.Time
}

// SampleAndroidFacts persists the instant a network class was first observed
// by this daemon. Unknown changes reset readiness instead of inventing uptime.
func SampleAndroidFacts(cachePath string) Facts {
	f := AndroidFacts(cachePath)
	sampler.Lock()
	defer sampler.Unlock()
	if sampler.network != f.Network {
		sampler.network = f.Network
		sampler.since = time.Now()
	}
	if f.Network != Unknown && f.Network != Offline {
		f.NetworkAt = sampler.since
	}
	return f
}
