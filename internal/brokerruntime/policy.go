// Package brokerruntime composes the existing R1 broker with an explicit,
// root-owned operator policy. It does not invent a second grant store or
// accept self-asserted package/module identities from consumer requests.
package brokerruntime

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"syscall"
	"time"

	"skybind/internal/brokeridentity"
)

const Schema = "skybind-r1-operator-policy-v1"
const CanonicalPolicy = "/data/adb/skybind/consumer-policy-v1.json"

// Rule is an operator-approved maximum, not a request sent by a consumer.
// Requests may only narrow the approved scope; individual grants remain tied
// to an attested process incarnation and expire after at most five minutes.
type Rule struct {
	Consumer   string   `json:"consumer"`
	Remote     string   `json:"remote"`
	Prefix     string   `json:"prefix"`
	Operations []string `json:"operations"`
}
type BKXPin struct {
	Package        string `json:"package"`
	UID            uint32 `json:"uid"`
	CertSHA256     string `json:"cert_sha256"`
	SELinuxContext string `json:"selinux_context"`
}
type ChrootPin struct {
	ManifestSHA256 string `json:"manifest_sha256"`
	SELinuxContext string `json:"selinux_context"`
}
type Policy struct {
	Schema            string    `json:"schema"`
	ABI               int       `json:"abi_major"`
	ExplicitlyEnabled bool      `json:"explicitly_enabled"`
	BKX               BKXPin    `json:"bkx"`
	Chrootctl         ChrootPin `json:"chrootctl"`
	Rules             []Rule    `json:"rules"`
}

var certRE = regexp.MustCompile(`^[0-9a-f]{64}$`)
var packageRE = regexp.MustCompile(`^[A-Za-z][A-Za-z0-9_.]{2,254}$`)
var remoteRE = regexp.MustCompile(`^[A-Za-z0-9_.-]{1,128}$`)
var allowed = map[string]bool{"system.capabilities": true, "rclone.version": true, "rclone.listremotes": true, "rclone.lsjson": true, "rclone.size": true}

func validPrefix(v string) bool {
	if len(v) > 4096 || strings.HasPrefix(v, "/") || strings.ContainsAny(v, "\\%?#\x00\r\n") {
		return false
	}
	if v == "" {
		return true
	}
	for _, s := range strings.Split(v, "/") {
		if s == "" || s == "." || s == ".." {
			return false
		}
	}
	return true
}
func validContext(v string) bool {
	return len(v) >= 8 && len(v) <= 192 && strings.HasPrefix(v, "u:r:") && !strings.ContainsAny(v, "\r\n\t\x00")
}
func (p Policy) Validate() error {
	if p.Schema != Schema || p.ABI != 1 || !p.ExplicitlyEnabled || p.BKX.UID < 10000 || !packageRE.MatchString(p.BKX.Package) || !certRE.MatchString(p.BKX.CertSHA256) || !validContext(p.BKX.SELinuxContext) || !certRE.MatchString(p.Chrootctl.ManifestSHA256) || !validContext(p.Chrootctl.SELinuxContext) || len(p.Rules) == 0 || len(p.Rules) > 16 {
		return errors.New("r1_operator_policy_not_approved")
	}
	seen := map[string]bool{}
	for _, r := range p.Rules {
		if r.Consumer != "bkx" && r.Consumer != "chrootctl" {
			return errors.New("r1_unknown_consumer")
		}
		if !remoteRE.MatchString(r.Remote) || !validPrefix(r.Prefix) || len(r.Operations) == 0 || len(r.Operations) > 5 {
			return errors.New("r1_invalid_scope")
		}
		ops := map[string]bool{}
		for _, op := range r.Operations {
			if !allowed[op] || ops[op] {
				return errors.New("r1_write_or_duplicate_operation_denied")
			}
			ops[op] = true
		}
		key := fmt.Sprintf("%s\x00%s\x00%s", r.Consumer, r.Remote, r.Prefix)
		if seen[key] {
			return errors.New("r1_duplicate_scope")
		}
		seen[key] = true
	}
	return nil
}

// LoadAt requires a root-owned, non-symlink, mode-0600 policy and trusted
// private parent. It never interprets a file supplied by an IPC consumer.
func LoadAt(path string) (Policy, error) {
	var p Policy
	if !filepath.IsAbs(path) || filepath.Clean(path) != path || strings.Contains(path, "\x00") {
		return p, errors.New("invalid_policy_path")
	}
	parent := filepath.Dir(path)
	dir, e := os.Lstat(parent)
	if e != nil || !dir.IsDir() || dir.Mode()&os.ModeSymlink != 0 || dir.Mode().Perm() != 0700 {
		return p, errors.New("unsafe_policy_parent")
	}
	owner, ok := dir.Sys().(*syscall.Stat_t)
	if !ok || owner.Uid != 0 {
		return p, errors.New("unsafe_policy_parent_owner")
	}
	before, e := os.Lstat(path)
	if e != nil || !before.Mode().IsRegular() || before.Mode().Perm() != 0600 || before.Size() == 0 || before.Size() > 32<<10 {
		return p, errors.New("unsafe_policy_file")
	}
	stat, ok := before.Sys().(*syscall.Stat_t)
	if !ok || stat.Uid != 0 || stat.Nlink != 1 {
		return p, errors.New("unsafe_policy_file_owner")
	}
	f, e := os.Open(path)
	if e != nil {
		return p, e
	}
	defer f.Close()
	opened, e := f.Stat()
	if e != nil || !os.SameFile(before, opened) {
		return p, errors.New("policy_changed_during_open")
	}
	raw, e := io.ReadAll(io.LimitReader(f, 32<<10+1))
	if e != nil || len(raw) > 32<<10 || int64(len(raw)) != opened.Size() {
		return p, errors.New("policy_read_failed")
	}
	after, e := os.Lstat(path)
	if e != nil || !os.SameFile(before, after) || !before.ModTime().Equal(after.ModTime()) {
		return p, errors.New("policy_changed_during_read")
	}
	if e := rejectDuplicateJSONKeys(raw); e != nil {
		return Policy{}, e
	}
	d := json.NewDecoder(bytes.NewReader(raw))
	d.DisallowUnknownFields()
	if e = d.Decode(&p); e != nil {
		return Policy{}, errors.New("invalid_policy_json")
	}
	if e = d.Decode(new(any)); e != io.EOF {
		return Policy{}, errors.New("trailing_policy_json")
	}
	if e = p.Validate(); e != nil {
		return Policy{}, e
	}
	return p, nil
}

// Struct constructors are pure; no production listener or grant is activated
// merely by loading a policy.
func (p Policy) PackagePin() brokeridentity.PackagePin {
	return brokeridentity.PackagePin{Name: p.BKX.Package, CertSHA256: p.BKX.CertSHA256, SELinuxContext: p.BKX.SELinuxContext}
}
func (p Policy) ModulePin() brokeridentity.ModulePin {
	return brokeridentity.ModulePin{Name: "chrootctl", ModuleSealSHA256: p.Chrootctl.ManifestSHA256, SELinuxContext: p.Chrootctl.SELinuxContext}
}

const MaxGrantTTL = time.Minute * 5

// rejectDuplicateJSONKeys checks every nested object, not only the top-level
// struct. encoding/json alone accepts shadowed keys and is unsafe for pins.
func rejectDuplicateJSONKeys(raw []byte) error {
	dec := json.NewDecoder(bytes.NewReader(raw))
	var value func() error
	value = func() error {
		token, e := dec.Token()
		if e != nil {
			return errors.New("invalid_policy_token")
		}
		d, ok := token.(json.Delim)
		if !ok {
			return nil
		}
		switch d {
		case '{':
			seen := map[string]bool{}
			for dec.More() {
				tok, e := dec.Token()
				if e != nil {
					return errors.New("invalid_policy_key")
				}
				key, ok := tok.(string)
				if !ok || seen[key] {
					return errors.New("duplicate_policy_field")
				}
				seen[key] = true
				if e = value(); e != nil {
					return e
				}
			}
			end, e := dec.Token()
			if e != nil || end != json.Delim('}') {
				return errors.New("invalid_policy_object")
			}
		case '[':
			for dec.More() {
				if e = value(); e != nil {
					return e
				}
			}
			end, e := dec.Token()
			if e != nil || end != json.Delim(']') {
				return errors.New("invalid_policy_array")
			}
		default:
			return errors.New("invalid_policy_delimiter")
		}
		return nil
	}
	if e := value(); e != nil {
		return e
	}
	if _, e := dec.Token(); e != io.EOF {
		return errors.New("trailing_or_invalid_policy")
	}
	return nil
}
