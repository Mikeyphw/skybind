// Package policy evaluates bounded, read-only device facts. Unknown facts
// fail closed whenever a mount requires the corresponding resource.
package policy

import (
	"errors"
	"fmt"
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
	Name                 string            `json:"name"`
	Description          string            `json:"description"`
	CacheMode            string            `json:"cache_mode"`
	MaxBytes             int64             `json:"max_bytes"`
	MaxAgeSeconds        int64             `json:"max_age_seconds"`
	DirCacheSeconds      int64             `json:"dir_cache_seconds"`
	PollSeconds          int64             `json:"poll_seconds"`
	ReadOnly             bool              `json:"read_only"`
	Options              map[string]string `json:"options"`
	Recommended          bool              `json:"recommended,omitempty"`
	SuggestedMaxBytes    int64             `json:"suggested_max_bytes,omitempty"`
	RecommendationReason string            `json:"recommendation_reason,omitempty"`
}

// The legacy "offline" preset is retained for existing registries. Neither
// offline nor offline-ready guarantees that every file is completely cached.
var profiles = []Profile{
	{Name: "streaming", Description: "Media seeking and read-ahead; native VFS eviction.", CacheMode: "full", MaxBytes: 4 << 30, MaxAgeSeconds: 86400, DirCacheSeconds: 600, PollSeconds: 60},
	{Name: "balanced", Description: "Everyday file browsing and occasional edits.", CacheMode: "full", MaxBytes: 2 << 30, MaxAgeSeconds: 43200, DirCacheSeconds: 300, PollSeconds: 60},
	{Name: "documents", Description: "Smaller cache and more responsive folder refresh for documents.", CacheMode: "full", MaxBytes: 1 << 30, MaxAgeSeconds: 14400, DirCacheSeconds: 120, PollSeconds: 60},
	{Name: "minimal", Description: "Low local footprint; reduced cache retention.", CacheMode: "minimal", MaxBytes: 512 << 20, MaxAgeSeconds: 3600, DirCacheSeconds: 60, PollSeconds: 120},
	{Name: "read-only", Description: "Prevent filesystem writes; keep bounded read cache.", CacheMode: "full", MaxBytes: 1 << 30, MaxAgeSeconds: 21600, DirCacheSeconds: 300, PollSeconds: 60, ReadOnly: true},
	{Name: "offline-ready", Description: "Long retention for intermittent connectivity; not verified offline pinning.", CacheMode: "full", MaxBytes: 8 << 30, MaxAgeSeconds: 604800, DirCacheSeconds: 3600, PollSeconds: 0},
	{Name: "offline", Description: "Legacy cached-access preset; NOT guaranteed complete offline files.", CacheMode: "full", MaxBytes: 8 << 30, MaxAgeSeconds: 604800, DirCacheSeconds: 3600, PollSeconds: 0},
}

func Profiles() []Profile {
	out := make([]Profile, 0, len(profiles))
	for _, p := range profiles {
		p.Options = map[string]string{
			"vfs_cache_mode":     p.CacheMode,
			"vfs_cache_max_size": fmt.Sprintf("%d", p.MaxBytes),
			"vfs_cache_max_age":  (time.Duration(p.MaxAgeSeconds) * time.Second).String(),
			"dir_cache_time":     (time.Duration(p.DirCacheSeconds) * time.Second).String(),
			"poll_interval":      (time.Duration(p.PollSeconds) * time.Second).String(),
		}
		out = append(out, p)
	}
	return out
}
func Resolve(m config.Mount) (Profile, error) {
	if m.VFSProfile == "custom" || m.VFSProfile == "" {
		return Profile{Name: "custom", CacheMode: m.CacheMode, MaxBytes: m.CacheMaxBytes, MaxAgeSeconds: m.CacheMaxAgeSeconds, DirCacheSeconds: m.DirCacheSeconds, PollSeconds: m.PollSeconds, ReadOnly: m.ReadOnly}, nil
	}
	for _, p := range profiles {
		if p.Name == m.VFSProfile {
			return p, nil
		}
	}
	return Profile{}, errors.New("unknown VFS profile")
}

// Pressure is advice only; VFS max-size is a soft cache eviction target, not
// a hard guarantee and never authorizes deletion of unknown dirty files.
type Pressure struct {
	State       string `json:"state"`
	Percent     int    `json:"percent,omitempty"`
	HighPercent int    `json:"high_percent,omitempty"`
	LowPercent  int    `json:"low_percent,omitempty"`
	Reason      string `json:"reason"`
}

func AssessPressure(used, max int64, high, low int) Pressure {
	if used < 0 || max <= 0 || high <= 0 || high > 100 || low < 0 || low >= high {
		return Pressure{State: "unknown", Reason: "insufficient_cache_measurements"}
	}
	p := int(used * 100 / max)
	if p > 10000 {
		p = 10000
	}
	out := Pressure{State: "normal", Percent: p, HighPercent: high, LowPercent: low, Reason: "native_vfs_eviction_only"}
	if p >= high {
		out.State = "high"
	}
	return out
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
