// Package namespace implements read-only Android mount namespace evidence.
// Observations never authorize a bind merely because another path is visible.
package namespace

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

const maxScanPIDs = 4096
const maxScanGroups = 512
const maxMountinfoBytes = 1 << 20

type Visibility string

const (
	VisibleAtTarget  Visibility = "visible_at_target"
	VisibleAtAlias   Visibility = "visible_at_alias"
	IdentityMismatch Visibility = "identity_mismatch"
	NotVisible       Visibility = "not_visible"
	Unavailable      Visibility = "unavailable"
)

type Signature struct {
	Target  string `json:"target"`
	FS      string `json:"fs"`
	Source  string `json:"source"`
	MountID string `json:"mount_id"`
}
type Member struct {
	PID   int    `json:"pid"`
	UID   int    `json:"uid"`
	User  int    `json:"android_user"`
	Comm  string `json:"comm"`
	Class string `json:"class"`
}
type Group struct {
	Namespace   string     `json:"namespace"`
	Members     []Member   `json:"members"`
	Protected   bool       `json:"protected"`
	Complete    bool       `json:"complete"`
	Visibility  Visibility `json:"visibility"`
	Observed    Signature  `json:"observed"`
	MatchedPath string     `json:"matched_path,omitempty"`
	Reason      string     `json:"reason"`
}
type Snapshot struct {
	Target   string    `json:"target"`
	Source   Signature `json:"source"`
	Complete bool      `json:"complete"`
	Scanned  int       `json:"scanned"`
	Groups   []Group   `json:"groups"`
	Problems []string  `json:"problems,omitempty"`
}
type Scanner struct{ Proc string }

func CanonicalScanner() Scanner { return Scanner{Proc: "/proc"} }
func (s Scanner) base() string {
	if s.Proc == "" {
		return "/proc"
	}
	return s.Proc
}
func parseMountinfo(data []byte) []Signature {
	out := []Signature{}
	sc := bufio.NewScanner(strings.NewReader(string(data)))
	sc.Buffer(make([]byte, 4096), maxMountinfoBytes)
	for sc.Scan() {
		pair := strings.SplitN(sc.Text(), " - ", 2)
		if len(pair) != 2 {
			continue
		}
		l := strings.Fields(pair[0])
		r := strings.Fields(pair[1])
		if len(l) < 5 || len(r) < 2 {
			continue
		}
		rep := strings.NewReplacer(`\040`, ` `, `\011`, `\t`, `\012`, `\n`, `\134`, `\`)
		out = append(out, Signature{Target: rep.Replace(l[4]), FS: r[0], Source: rep.Replace(r[1]), MountID: l[0]})
	}
	return out
}
func classify(m Member) string {
	c := strings.ToLower(m.Comm)
	for _, v := range []string{"zygote", "usap", "mediaprovider", "externalstorage", "system_server", "vold", "storagemanager", "sdcard", "fuse_bpf"} {
		if strings.Contains(c, v) {
			return "protected"
		}
	}
	if m.UID == 0 || m.UID == 1000 || m.UID == 1023 {
		return "protected"
	}
	if m.UID >= 10000 {
		return "app"
	}
	return "system_or_unknown"
}
func aliases(user int) []string {
	return []string{fmt.Sprintf("/storage/emulated/%d", user), fmt.Sprintf("/mnt/user/%d/primary", user), "/storage/self/primary"}
}
func sameSource(a, b Signature) bool {
	return strings.HasPrefix(a.FS, "fuse") && a.FS == b.FS && a.Source != "" && a.Source == b.Source
}
func classifyVisibility(g *Group, items []Signature, wanted Signature) {
	if !g.Complete {
		g.Visibility = Unavailable
		g.Reason = "incomplete namespace evidence"
		return
	}
	var exact []Signature
	for _, m := range items {
		if m.Target == wanted.Target {
			exact = append(exact, m)
		}
	}
	if len(exact) > 1 {
		g.Visibility = IdentityMismatch
		g.Reason = "ambiguous stacked mounts at exact target"
		return
	}
	if len(exact) == 1 {
		m := exact[0]
		g.Observed = m
		if sameSource(m, wanted) {
			g.Visibility = VisibleAtTarget
			g.Reason = "matching source at exact target"
		} else {
			g.Visibility = IdentityMismatch
			g.Reason = "target occupied by other filesystem"
		}
		return
	}
	for _, member := range g.Members {
		for _, alias := range aliases(member.User) {
			if alias == wanted.Target {
				continue
			}
			for _, m := range items {
				if m.Target == alias && sameSource(m, wanted) {
					g.Visibility = VisibleAtAlias
					g.MatchedPath = alias
					g.Observed = m
					g.Reason = "alias only; exact target not visible"
					return
				}
			}
		}
	}
	g.Visibility = NotVisible
	g.Reason = "expected source not found at exact target"
}

func (s Scanner) Scan(ctx context.Context, source Signature) (Snapshot, error) {
	if !filepath.IsAbs(source.Target) || filepath.Clean(source.Target) != source.Target || !strings.HasPrefix(source.FS, "fuse") || source.MountID == "" || source.Source == "" {
		return Snapshot{}, errors.New("expected FUSE source identity is incomplete")
	}
	root := s.base()
	list, e := os.ReadDir(root)
	if e != nil {
		return Snapshot{}, e
	}
	out := Snapshot{Target: source.Target, Source: source, Complete: true, Groups: []Group{}}
	groups := map[string]*Group{}
	mountdata := map[string][]Signature{}
	for _, ent := range list {
		if ctx.Err() != nil {
			return Snapshot{}, ctx.Err()
		}
		pid, e := strconv.Atoi(ent.Name())
		if e != nil || pid <= 0 {
			continue
		}
		out.Scanned++
		if out.Scanned > maxScanPIDs {
			out.Complete = false
			out.Problems = append(out.Problems, "pid scan budget exhausted")
			break
		}
		path := filepath.Join(root, ent.Name())
		link, e := os.Readlink(filepath.Join(path, "ns/mnt"))
		if e != nil {
			out.Complete = false
			continue
		}
		g := groups[link]
		if g == nil {
			if len(groups) >= maxScanGroups {
				out.Complete = false
				out.Problems = append(out.Problems, "namespace group budget exhausted")
				break
			}
			g = &Group{Namespace: link, Complete: true, Members: []Member{}}
			groups[link] = g
		}
		status, e := os.ReadFile(filepath.Join(path, "status"))
		if e != nil {
			g.Complete = false
			out.Complete = false
			continue
		}
		uid := -1
		for _, ln := range strings.Split(string(status), "\n") {
			if strings.HasPrefix(ln, "Uid:") {
				f := strings.Fields(ln)
				if len(f) > 1 {
					uid, _ = strconv.Atoi(f[1])
				}
				break
			}
		}
		b, e := os.ReadFile(filepath.Join(path, "comm"))
		if e != nil || uid < 0 {
			g.Complete = false
			out.Complete = false
			continue
		}
		user := 0
		if uid >= 100000 {
			user = uid / 100000
		}
		m := Member{PID: pid, UID: uid, User: user, Comm: strings.TrimSpace(string(b))}
		m.Class = classify(m)
		if m.Class != "app" {
			g.Protected = true
		}
		g.Members = append(g.Members, m)
		if _, ok := mountdata[link]; !ok {
			raw, e := os.ReadFile(filepath.Join(path, "mountinfo"))
			if e != nil || len(raw) > maxMountinfoBytes {
				g.Complete = false
				out.Complete = false
				continue
			}
			mountdata[link] = parseMountinfo(raw)
		}
	}
	keys := make([]string, 0, len(groups))
	for k := range groups {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		g := groups[k]
		if len(g.Members) == 0 {
			g.Complete = false
		}
		sort.Slice(g.Members, func(i, j int) bool { return g.Members[i].PID < g.Members[j].PID })
		classifyVisibility(g, mountdata[k], source)
		out.Groups = append(out.Groups, *g)
	}
	if !out.Complete {
		out.Problems = append(out.Problems, "proc unreadable or changed; mutation forbidden")
	}
	return out, nil
}
