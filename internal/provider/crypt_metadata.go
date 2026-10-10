package provider

import (
	"encoding/json"
	"errors"
	"os"
	"skybind/internal/atomicfile"
	"skybind/internal/protocol"
	"strings"
)

type managedCrypt struct {
	Name             string `json:"name"`
	BackingRemote    string `json:"backing_remote"`
	PasswordRevision uint64 `json:"password_revision"`
	CreatedUnix      int64  `json:"created_unix"`
}
type cryptMetadata struct {
	SchemaVersion  int            `json:"schema_version"`
	Revision       uint64         `json:"password_revision"`
	UntrackedPrior bool           `json:"untracked_prior"`
	Managed        []managedCrypt `json:"managed"`
}

func (m *Manager) loadCryptMetadata() (cryptMetadata, error) {
	data, err := atomicfile.Read(m.dir, "crypt-metadata-v1.json", 1<<18)
	if errors.Is(err, os.ErrNotExist) {
		return cryptMetadata{SchemaVersion: 1, Managed: []managedCrypt{}}, nil
	}
	if err != nil {
		return cryptMetadata{}, err
	}
	var v cryptMetadata
	if err = protocol.StrictBytes(data, &v); err != nil {
		return v, errors.New("invalid crypt metadata")
	}
	if v.SchemaVersion != 1 || len(v.Managed) > 256 {
		return v, errors.New("invalid crypt metadata schema")
	}
	seen := map[string]bool{}
	for _, r := range v.Managed {
		if !remoteName.MatchString(r.Name) || seen[r.Name] || r.CreatedUnix <= 0 || r.PasswordRevision > v.Revision {
			return v, errors.New("invalid crypt provenance entry")
		}
		if _, _, e := splitEndpoint(r.BackingRemote); e != nil {
			return v, errors.New("invalid crypt provenance remote")
		}
		seen[r.Name] = true
	}
	return v, nil
}
func (m *Manager) saveCryptMetadata(v cryptMetadata) error {
	v.SchemaVersion = 1
	data, err := json.Marshal(v)
	if err != nil {
		return err
	}
	return atomicfile.Write(m.dir, "crypt-metadata-v1.json", data)
}
func backingRemote(data []byte, name string) string {
	current := ""
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			current = strings.TrimSuffix(strings.TrimPrefix(line, "["), "]")
			continue
		}
		if current != name {
			continue
		}
		fields := strings.SplitN(line, "=", 2)
		if len(fields) == 2 && strings.TrimSpace(fields[0]) == "remote" {
			return strings.TrimSpace(fields[1])
		}
	}
	return ""
}
func mustConfigForRecovery(dir string) []byte {
	data, _ := atomicfile.Read(dir, "rclone.conf", 1<<18)
	return data
}
