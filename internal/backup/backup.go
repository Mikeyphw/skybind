// Package backup implements portable, integrity checked, credential-free
// configuration exports. Restores must use the existing proof-bound registry
// transaction; the backup format is not an alternate privileged state writer.
package backup

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"skybind/internal/mounts/config"
	"skybind/internal/offline"
	"skybind/internal/uisettings"
)

const MaxBytes = 48 << 10 // below protocol's 64 KiB request envelope
const MaxPins = 256

type PinReference struct {
	Mount                string `json:"mount"`
	Path                 string `json:"path"`
	Size                 int64  `json:"size"`
	SHA256               string `json:"sha256"`
	RemoteIdentitySHA256 string `json:"remote_identity_sha256"`
}
type Payload struct {
	Kind          string              `json:"kind"`
	Schema        int                 `json:"schema"`
	GeneratedUnix int64               `json:"generated_unix"`
	Registry      config.Registry     `json:"registry"`
	Preferences   uisettings.Settings `json:"preferences"`
	PinReferences []PinReference      `json:"pin_references"`
}
type Document struct {
	Payload Payload `json:"payload"`
	SHA256  string  `json:"sha256"`
}

func hash(v any) (string, error) {
	b, e := json.Marshal(v)
	if e != nil {
		return "", e
	}
	h := sha256.Sum256(b)
	return hex.EncodeToString(h[:]), nil
}
func HasInlineSecrets(m config.Mount) bool {
	// A remote reference is NOT an rclone.conf credential. Still refuse inline
	// connection strings and obvious password-bearing arguments in public exports.
	r := strings.ToLower(m.Remote)
	for _, s := range []string{"://", "@", "?", "password=", "token=", "secret=", "access_key", "bearer ", "apikey=", "api_key=", "client_secret"} {
		if strings.Contains(r, s) {
			return true
		}
	}
	return false
}
func checkPayload(p Payload) error {
	if p.Kind != "skybind-personal-config" || p.Schema != 1 || p.GeneratedUnix <= 0 || p.GeneratedUnix > time.Now().Add(24*time.Hour).Unix() {
		return errors.New("unsupported backup schema or timestamp")
	}
	b, e := json.Marshal(p.Registry)
	if e != nil {
		return e
	}
	r, e := config.Validate(b)
	if e != nil {
		return fmt.Errorf("invalid backed-up registry: %w", e)
	}
	for _, m := range r.Mounts {
		if HasInlineSecrets(m) {
			return errors.New("mount remote may contain inline credentials; export refused")
		}
	}
	if e = uisettings.Valid(p.Preferences); e != nil {
		return fmt.Errorf("invalid preferences: %w", e)
	}
	if len(p.PinReferences) > MaxPins {
		return errors.New("too many pin references for portable backup")
	}
	seen := make(map[string]struct{}, len(p.PinReferences))
	for _, v := range p.PinReferences {
		if v.Mount == "" || v.Path == "" || v.Size < 0 || len(v.SHA256) != 64 || len(v.RemoteIdentitySHA256) != 64 {
			return errors.New("invalid pin reference")
		}
		if _, e = hex.DecodeString(v.SHA256); e != nil {
			return errors.New("invalid pin checksum")
		}
		if _, e = hex.DecodeString(v.RemoteIdentitySHA256); e != nil {
			return errors.New("invalid remote identity checksum")
		}
		key := v.Mount + "\x00" + v.Path
		if _, ok := seen[key]; ok {
			return errors.New("duplicate pin reference")
		}
		seen[key] = struct{}{}
		// Validate names/paths by the exact same pinned manifest verifier used by M5.
		if e = offline.ValidatePinReference(v.Mount, v.Path); e != nil {
			return fmt.Errorf("invalid pin reference path: %w", e)
		}
	}
	return nil
}
func Build(reg config.Registry, prefs uisettings.Snapshot, pins offline.Manifest) (Document, error) {
	p := Payload{Kind: "skybind-personal-config", Schema: 1, GeneratedUnix: time.Now().Unix(), Registry: reg, Preferences: prefs.Settings, PinReferences: make([]PinReference, 0, len(pins.Pins))}
	for _, pin := range pins.Pins {
		p.PinReferences = append(p.PinReferences, PinReference{pin.Mount, pin.Path, pin.Size, pin.SHA256, pin.RemoteIdentity})
	}
	if e := checkPayload(p); e != nil {
		return Document{}, e
	}
	digest, e := hash(p)
	if e != nil {
		return Document{}, e
	}
	doc := Document{p, digest}
	b, e := json.Marshal(doc)
	if e != nil {
		return Document{}, e
	}
	if len(b) > MaxBytes {
		return Document{}, errors.New("backup exceeds portable transport limit; reduce pin count")
	}
	return doc, nil
}
func Validate(doc Document) error {
	b, e := json.Marshal(doc)
	if e != nil {
		return e
	}
	if len(b) > MaxBytes {
		return errors.New("backup exceeds size limit")
	}
	if e = checkPayload(doc.Payload); e != nil {
		return e
	}
	want, e := hash(doc.Payload)
	if e != nil {
		return e
	}
	if doc.SHA256 != want {
		return errors.New("backup checksum mismatch")
	}
	return nil
}

// Candidate restores mount definitions in a disabled state. Nothing is started
// by importing a document and the M5/M6 files are never modified.
func Candidate(doc Document, revision uint64) ([]byte, error) {
	if e := Validate(doc); e != nil {
		return nil, e
	}
	r := doc.Payload.Registry
	r.Revision = revision
	for i := range r.Mounts {
		r.Mounts[i].Enabled = false
	}
	return json.Marshal(r)
}
