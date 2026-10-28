package featuregateway

// API-04 P3 is an independently approved, opt-in mutation surface. The P2
// Policy/Guard/EndpointServer remain strictly read-only.
import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"syscall"
)

const MutationSchema = "skybind-api04-mutation-policy-v1"
const CanonicalMutationPolicy = "/data/adb/skybind/api04-mutation-policy-v1.json"
const CanonicalMutationState = "/data/adb/skybind/api04-mutations"
const mutationEndpoint = "\x00skybind-api04-mutations-v1"

var mutationAllow = map[string]bool{"mount.start": true, "mount.stop": true}

type MutationPolicy struct {
	Schema            string   `json:"schema"`
	ExplicitlyEnabled bool     `json:"explicitly_enabled"`
	Operations        []string `json:"operations"`
	MountNames        []string `json:"mount_names"`
}

func (p MutationPolicy) Validate(q Policy) error {
	if p.Schema != MutationSchema || !p.ExplicitlyEnabled || q.Validate() != nil ||
		len(p.Operations) == 0 || len(p.Operations) > 2 || len(p.MountNames) == 0 || len(p.MountNames) > 32 {
		return errors.New("api04_mutation_policy_denied")
	}
	seen := map[string]bool{}
	for _, op := range p.Operations {
		if !mutationAllow[op] || seen[op] {
			return errors.New("api04_mutation_operation_denied")
		}
		seen[op] = true
	}
	names := map[string]bool{}
	for _, name := range p.MountNames {
		if !mountName.MatchString(name) || names[name] || !q.AllowsMount(name) {
			return errors.New("api04_mutation_mount_denied")
		}
		names[name] = true
	}
	return nil
}
func (p MutationPolicy) Allows(op, name string) bool {
	if !mutationAllow[op] || !mountName.MatchString(name) {
		return false
	}
	o, n := false, false
	for _, v := range p.Operations {
		if v == op {
			o = true
		}
	}
	for _, v := range p.MountNames {
		if v == name {
			n = true
		}
	}
	return o && n
}
func DecodeMutationPolicy(b []byte, q Policy) (MutationPolicy, error) {
	var p MutationPolicy
	if len(b) == 0 || len(b) > maxPolicyBytes || rejectDuplicateKeys(b) != nil {
		return p, errors.New("api04_mutation_policy_invalid")
	}
	d := json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if d.Decode(&p) != nil {
		return MutationPolicy{}, errors.New("api04_mutation_policy_invalid")
	}
	var extra any
	if d.Decode(&extra) != io.EOF || p.Validate(q) != nil {
		return MutationPolicy{}, errors.New("api04_mutation_policy_denied")
	}
	return p, nil
}
func LoadMutationCanonical(q Policy) (MutationPolicy, error) {
	if os.Geteuid() != 0 {
		return MutationPolicy{}, errors.New("api04_mutation_root_only")
	}
	return loadMutationAt(CanonicalMutationPolicy, q)
}

// The loader refuses path substitutions, links, wrong owners, modes, and
// replacement between lstat/open/read. Production passes the fixed constant.
func loadMutationAt(path string, q Policy) (MutationPolicy, error) {
	var absent MutationPolicy
	if !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return absent, errors.New("api04_mutation_policy_path")
	}
	dir := filepath.Dir(path)
	parent, err := os.Lstat(dir)
	if err != nil || !parent.IsDir() || parent.Mode().Perm() != 0700 {
		return absent, errors.New("api04_mutation_parent_untrusted")
	}
	ps, ok := parent.Sys().(*syscall.Stat_t)
	if !ok || ps.Uid != uint32(os.Geteuid()) {
		return absent, errors.New("api04_mutation_parent_owner")
	}
	first, err := os.Lstat(path)
	if err != nil || !first.Mode().IsRegular() || first.Mode().Perm() != 0600 || first.Size() < 1 || first.Size() > maxPolicyBytes {
		return absent, errors.New("api04_mutation_file_untrusted")
	}
	st, ok := first.Sys().(*syscall.Stat_t)
	if !ok || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 {
		return absent, errors.New("api04_mutation_file_owner")
	}
	f, err := os.Open(path)
	if err != nil {
		return absent, err
	}
	defer f.Close()
	opened, err := f.Stat()
	if err != nil || !os.SameFile(first, opened) {
		return absent, errors.New("api04_mutation_open_race")
	}
	b, err := io.ReadAll(io.LimitReader(f, maxPolicyBytes+1))
	if err != nil || int64(len(b)) != opened.Size() {
		return absent, errors.New("api04_mutation_read_race")
	}
	after, err := os.Lstat(path)
	if err != nil || !os.SameFile(first, after) || !first.ModTime().Equal(after.ModTime()) {
		return absent, errors.New("api04_mutation_changed")
	}
	return DecodeMutationPolicy(b, q)
}
