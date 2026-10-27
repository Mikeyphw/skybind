// Package featuregateway defines API-04 cross-UID admission policy. This is a
// source-only foundation; it starts no listener and delegates no root privilege.
package featuregateway

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"skybind/internal/brokeridentity"
	"skybind/internal/featureapi"
	"syscall"
)

const Schema = "skybind-api04-bkx-readonly-policy-v1"
const CanonicalPolicy = "/data/adb/skybind/api04-bkx-policy-v1.json"
const maxPolicyBytes = 16 * 1024

// Policy is independent of R1's read-only rclone policy and API-02's root-only
// daemon contract. It is not a consumer-supplied request or an auto-grant.
type Policy struct {
	Schema            string `json:"schema"`
	ExplicitlyEnabled bool   `json:"explicitly_enabled"`
	BKX               struct {
		Package        string `json:"package"`
		UID            uint32 `json:"uid"`
		CertSHA256     string `json:"cert_sha256"`
		SELinuxContext string `json:"selinux_context"`
	} `json:"bkx"`
	Operations []string `json:"operations"`
	MountNames []string `json:"mount_names"`
}

// A separate minimum-safe API-04 subset. Mutation/preview/reconcile is not
// authorized until the next phase has device-validated per-operation consent.
var readOnly = map[string]bool{
	"mount.status": true, "mount.health": true,
}
var digest = regexp.MustCompile(`^[0-9a-f]{64}$`)
var mountName = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_-]{0,62}$`)

func (p Policy) Validate() error {
	if p.Schema != Schema || !p.ExplicitlyEnabled ||
		p.BKX.Package != "com.mikeyphw.bkx.android" ||
		p.BKX.UID < 10000 || !digest.MatchString(p.BKX.CertSHA256) ||
		len(p.BKX.SELinuxContext) < 8 || len(p.BKX.SELinuxContext) > 192 ||
		len(p.BKX.SELinuxContext) < len("u:r:") || p.BKX.SELinuxContext[:4] != "u:r:" ||
		bytes.ContainsAny([]byte(p.BKX.SELinuxContext), "\r\n\t\x00") ||
		len(p.Operations) == 0 || len(p.Operations) > len(readOnly) || len(p.MountNames) == 0 || len(p.MountNames) > 32 {
		return errors.New("api04_policy_not_approved")
	}
	seen := map[string]bool{}
	for _, name := range p.Operations {
		class, ok := featureapi.ClassFor(name)
		if !ok || !readOnly[name] || string(class) != "query" || seen[name] {
			return errors.New("api04_operation_not_authorized")
		}
		seen[name] = true
	}
	names := map[string]bool{}
	for _, name := range p.MountNames {
		if !mountName.MatchString(name) || names[name] {
			return errors.New("api04_mount_scope_invalid")
		}
		names[name] = true
	}
	return nil
}
func (p Policy) PackagePin() brokeridentity.PackagePin {
	return brokeridentity.PackagePin{Name: p.BKX.Package, CertSHA256: p.BKX.CertSHA256, SELinuxContext: p.BKX.SELinuxContext}
}
func (p Policy) Allows(op string) bool {
	if p.Validate() != nil || !readOnly[op] {
		return false
	}
	for _, name := range p.Operations {
		if op == name {
			return true
		}
	}
	return false
}

func (p Policy) AllowsMount(name string) bool {
	if !mountName.MatchString(name) {
		return false
	}
	for _, candidate := range p.MountNames {
		if name == candidate {
			return true
		}
	}
	return false
}

// DecodePolicy rejects duplicate nested keys, shadowed signer pins, unknown
// fields, trailing JSON and oversized untrusted material before validation.
func DecodePolicy(raw []byte) (Policy, error) {
	var policy Policy
	if len(raw) == 0 || len(raw) > maxPolicyBytes {
		return policy, errors.New("api04_policy_size")
	}
	if err := rejectDuplicateKeys(raw); err != nil {
		return policy, err
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.DisallowUnknownFields()
	if err := dec.Decode(&policy); err != nil {
		return Policy{}, errors.New("api04_policy_json")
	}
	var unused any
	if err := dec.Decode(&unused); err != io.EOF {
		return Policy{}, errors.New("api04_policy_trailing")
	}
	if err := policy.Validate(); err != nil {
		return Policy{}, err
	}
	return policy, nil
}

func rejectDuplicateKeys(raw []byte) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	var walk func(int) error
	walk = func(depth int) error {
		if depth > 20 {
			return errors.New("api04_policy_depth")
		}
		token, err := dec.Token()
		if err != nil {
			return errors.New("api04_policy_token")
		}
		delim, ok := token.(json.Delim)
		if !ok {
			return nil
		}
		switch delim {
		case '{':
			seen := map[string]bool{}
			for dec.More() {
				tok, e := dec.Token()
				if e != nil {
					return errors.New("api04_policy_key")
				}
				key, ok := tok.(string)
				if !ok || seen[key] {
					return errors.New("api04_policy_duplicate_key")
				}
				seen[key] = true
				if e := walk(depth + 1); e != nil {
					return e
				}
			}
			end, e := dec.Token()
			if e != nil || end != json.Delim('}') {
				return errors.New("api04_policy_object")
			}
		case '[':
			for dec.More() {
				if e := walk(depth + 1); e != nil {
					return e
				}
			}
			end, e := dec.Token()
			if e != nil || end != json.Delim(']') {
				return errors.New("api04_policy_array")
			}
		default:
			return errors.New("api04_policy_delimiter")
		}
		return nil
	}
	if err := walk(0); err != nil {
		return err
	}
	if _, err := dec.Token(); err != io.EOF {
		return errors.New("api04_policy_trailing")
	}
	return nil
}

// LoadCanonical is root-only and refuses alternative policy locations. This
// cannot be invoked by a consumer-selected path or substituted through a link.
func LoadCanonical() (Policy, error) { return LoadAt(CanonicalPolicy) }

// LoadAt exists for safe offline/negative fixture testing. Runtime callers MUST
// use LoadCanonical and require process EUID=0.
func LoadAt(path string) (Policy, error) {
	var absent Policy
	if os.Geteuid() != 0 || !filepath.IsAbs(path) || filepath.Clean(path) != path {
		return absent, errors.New("api04_policy_root_only")
	}
	parent := filepath.Dir(path)
	dir, err := os.Lstat(parent)
	if err != nil || !dir.IsDir() || dir.Mode().Perm() != 0700 || dir.Mode()&os.ModeSymlink != 0 {
		return absent, errors.New("api04_policy_directory_untrusted")
	}
	owner, ok := dir.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != 0 {
		return absent, errors.New("api04_policy_directory_owner")
	}
	prior, err := os.Lstat(path)
	if err != nil || !prior.Mode().IsRegular() || prior.Size() < 1 || prior.Size() > maxPolicyBytes || prior.Mode().Perm() != 0600 {
		return absent, errors.New("api04_policy_file_untrusted")
	}
	stat, ok := prior.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != 0 || stat.Nlink != 1 {
		return absent, errors.New("api04_policy_file_owner")
	}
	file, err := os.Open(path)
	if err != nil {
		return absent, err
	}
	defer file.Close()
	opened, err := file.Stat()
	if err != nil || !os.SameFile(prior, opened) {
		return absent, errors.New("api04_policy_open_race")
	}
	data, err := io.ReadAll(io.LimitReader(file, maxPolicyBytes+1))
	if err != nil || int64(len(data)) != opened.Size() {
		return absent, errors.New("api04_policy_read_race")
	}
	after, err := os.Lstat(path)
	if err != nil || !os.SameFile(prior, after) || !prior.ModTime().Equal(after.ModTime()) {
		return absent, errors.New("api04_policy_changed")
	}
	return DecodePolicy(data)
}
