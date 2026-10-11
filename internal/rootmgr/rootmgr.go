// Package rootmgr reports root-manager capabilities without guessing from
// the presence of su alone. Operations remain daemon-owned.
package rootmgr

import (
	"os"
	"path/filepath"
)

type Capability struct {
	Name       string `json:"name"`
	Identified bool   `json:"identified"`
	Evidence   string `json:"evidence"`
}
type Status struct {
	Root            bool         `json:"root"`
	ModulePresent   bool         `json:"module_present"`
	Manager         string       `json:"manager"`
	Confirmed       bool         `json:"confirmed"`
	Candidates      []Capability `json:"candidates"`
	DeviceQualified bool         `json:"device_qualified"`
}
type Detector interface{ Status() (Status, error) }
type CanonicalDetector struct{}

func (CanonicalDetector) Status() (Status, error) { return Detect("/data/adb", os.Geteuid() == 0) }
func Detect(base string, root bool) (Status, error) {
	result := Status{Root: root, Manager: "unknown", Candidates: []Capability{}, DeviceQualified: false}
	probe := []struct{ name, path string }{{"Magisk", "magisk"}, {"KernelSU", "ksu"}, {"KernelSU Next", "ksu-next"}, {"APatch", "ap"}}
	for _, x := range probe {
		path := filepath.Join(base, x.path)
		st, e := os.Lstat(path)
		confirmed := e == nil && st.IsDir() && st.Mode()&os.ModeSymlink == 0
		result.Candidates = append(result.Candidates, Capability{Name: x.name, Identified: confirmed, Evidence: x.path})
		if confirmed {
			if result.Manager != "unknown" {
				result.Manager = "ambiguous"
				result.Confirmed = false
			} else {
				result.Manager = x.name
				result.Confirmed = true
			}
		}
	}
	if st, e := os.Lstat(filepath.Join(base, "modules/skybind/module.prop")); e == nil && st.Mode().IsRegular() && st.Mode()&os.ModeSymlink == 0 {
		result.ModulePresent = true
	}
	return result, nil
}
