// Package policy evaluates bounded, read-only device facts. Unknown facts
// fail closed whenever a mount requires the corresponding resource.
package policy

import (
	"errors"
	"skybind/internal/mounts/config"
	"time"
)

type Network string

const (
	Unknown  Network = "unknown"
	Offline  Network = "offline"
	Cellular Network = "cellular"
	WiFi     Network = "wifi"
)

type Facts struct {
	Network        Network   `json:"network"`
	Metered        *bool     `json:"metered,omitempty"`
	Charging       *bool     `json:"charging,omitempty"`
	Battery        *int      `json:"battery_percent,omitempty"`
	CacheFreeBytes *int64    `json:"cache_free_bytes,omitempty"`
	BootAt         time.Time `json:"boot_at,omitempty"`
	NetworkAt      time.Time `json:"network_at,omitempty"`
}
type Decision struct {
	Allowed bool   `json:"allowed"`
	Reason  string `json:"reason"`
	Facts   Facts  `json:"facts"`
}

func Evaluate(m config.Mount, f Facts, now time.Time) Decision {
	reject := func(s string) Decision { return Decision{false, s, f} }
	if now.IsZero() {
		return reject("clock_unavailable")
	}
	switch m.NetworkMode {
	case "", "any":
		if f.Network == Unknown || f.Network == "" {
			return reject("network_unknown")
		}
		if f.Network == Offline {
			return reject("network_offline")
		}
	case "wifi":
		if f.Network != WiFi {
			return reject("wifi_required")
		}
	case "unmetered":
		if f.Network == Unknown || f.Network == Offline || f.Network == "" || f.Metered == nil || *f.Metered {
			return reject("unmetered_not_proven")
		}
	case "offline-allowed": // User explicitly authorized VFS cached access without a network.
	default:
		return reject("invalid_network_policy")
	}
	if m.ChargingOnly && (f.Charging == nil || !*f.Charging) {
		return reject("charging_not_proven")
	}
	if m.MinBatteryPercent > 0 && (f.Battery == nil || *f.Battery < m.MinBatteryPercent) {
		return reject("battery_below_minimum_or_unknown")
	}
	if m.MinCacheFreeBytes > 0 && (f.CacheFreeBytes == nil || *f.CacheFreeBytes < m.MinCacheFreeBytes) {
		return reject("cache_free_space_unproven")
	}
	if m.BootSettleSeconds > 0 && (f.BootAt.IsZero() || now.Sub(f.BootAt) < time.Duration(m.BootSettleSeconds)*time.Second) {
		return reject("boot_settling")
	}
	if m.NetworkSettleSeconds > 0 && (f.NetworkAt.IsZero() || now.Sub(f.NetworkAt) < time.Duration(m.NetworkSettleSeconds)*time.Second) {
		return reject("network_settling")
	}
	return Decision{true, "ready", f}
}

type Profile struct {
	Name                 string `json:"name"`
	CacheMode            string `json:"cache_mode"`
	MaxBytes             int64  `json:"max_bytes"`
	MaxAgeSeconds        int64  `json:"max_age_seconds"`
	DirCacheSeconds      int64  `json:"dir_cache_seconds"`
	PollSeconds          int64  `json:"poll_seconds"`
	Recommended          bool   `json:"recommended,omitempty"`
	SuggestedMaxBytes    int64  `json:"suggested_max_bytes,omitempty"`
	RecommendationReason string `json:"recommendation_reason,omitempty"`
}

var profiles = []Profile{{Name: "streaming", CacheMode: "full", MaxBytes: 4 << 30, MaxAgeSeconds: 86400, DirCacheSeconds: 600, PollSeconds: 60}, {Name: "balanced", CacheMode: "full", MaxBytes: 2 << 30, MaxAgeSeconds: 43200, DirCacheSeconds: 300, PollSeconds: 60}, {Name: "offline", CacheMode: "full", MaxBytes: 8 << 30, MaxAgeSeconds: 604800, DirCacheSeconds: 3600, PollSeconds: 0}, {Name: "minimal", CacheMode: "minimal", MaxBytes: 512 << 20, MaxAgeSeconds: 3600, DirCacheSeconds: 60, PollSeconds: 120}}

func Profiles() []Profile { return append([]Profile(nil), profiles...) }
func Resolve(m config.Mount) (Profile, error) {
	if m.VFSProfile == "custom" || m.VFSProfile == "" {
		return Profile{Name: "custom", CacheMode: m.CacheMode, MaxBytes: m.CacheMaxBytes, MaxAgeSeconds: m.CacheMaxAgeSeconds, DirCacheSeconds: m.DirCacheSeconds, PollSeconds: m.PollSeconds}, nil
	}
	for _, p := range profiles {
		if p.Name == m.VFSProfile {
			return p, nil
		}
	}
	return Profile{}, errors.New("unknown VFS profile")
}

// Advice is a non-authoritative recommendation, not a change to the user's
// mount configuration. Unknown device facts result in no recommendation.
type Advice struct {
	Known             bool   `json:"known"`
	Profile           string `json:"profile,omitempty"`
	SuggestedMaxBytes int64  `json:"suggested_max_bytes,omitempty"`
	Reason            string `json:"reason"`
}

func Recommend(memoryBytes, freeBytes int64) Advice {
	if memoryBytes <= 0 || freeBytes <= 0 {
		return Advice{Reason: "memory_or_storage_unknown"}
	}
	// Leave at least half of the observed free space untouched. A lower RAM
	// device favours the minimal cache; recommendations never mutate settings.
	cap := freeBytes / 2
	if cap < 256<<20 {
		return Advice{Known: true, Profile: "minimal", SuggestedMaxBytes: cap, Reason: "low_free_storage"}
	}
	profile := "balanced"
	limit := int64(2) << 30
	reason := "balanced_resources"
	if memoryBytes < 3<<30 {
		profile = "minimal"
		limit = 512 << 20
		reason = "limited_memory"
	}
	if memoryBytes >= 6<<30 && freeBytes >= 12<<30 {
		profile = "streaming"
		limit = 4 << 30
		reason = "ample_memory_and_storage"
	}
	if cap < limit {
		limit = cap
	}
	return Advice{Known: true, Profile: profile, SuggestedMaxBytes: limit, Reason: reason}
}
