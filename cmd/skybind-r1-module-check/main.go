// Root-only, read-only live chrootctl process provenance check. This does not
// start chrootctl, issue grants, or touch a repository. A missing process is
// blocked, never silently treated as PASS.
package main

import (
	"encoding/json"
	"flag"
	"os"
	"skybind/internal/brokeridentity"
	"skybind/internal/brokeripc"
	"strings"
)

type result struct {
	Schema            string `json:"schema"`
	State             string `json:"state"`
	Reason            string `json:"reason,omitempty"`
	ProcessAttested   bool   `json:"chrootctl_process_attested"`
	Granted           bool   `json:"grants_issued"`
	ProviderQualified bool   `json:"external_provider_qualified"`
	ReleaseQualified  bool   `json:"release_qualified"`
}

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	r := result{Schema: "skybind-r1-live-chrootctl-process-v1", State: "BLOCKED"}
	defer func() { _ = json.NewEncoder(os.Stdout).Encode(r) }()
	f := flag.NewFlagSet("skybind-r1-module-check", flag.ContinueOnError)
	f.SetOutput(os.Stderr)
	pid := f.Int("pid", 0, "already running installed chrootctl PID")
	seal := f.String("approved-manifest-sha256", "", "independently approved chrootctl manifest SHA256")
	context := f.String("approved-selinux", "", "measured and independently approved SELinux context")
	if os.Geteuid() != 0 || f.Parse(args) != nil || len(f.Args()) != 0 || *pid <= 0 || len(*seal) != 64 || len(*context) < 8 || !strings.HasPrefix(*context, "u:r:") {
		r.Reason = "OPERATOR_APPROVAL_OR_ROOT_REQUIRED"
		return 2
	}
	// LinuxProc is trusted /proc; the module verifier reads the canonical
	// installed manifest and compares the executing PID's exact executable.
	proc := brokeridentity.LinuxProc{}
	reader, e := proc.Read(int32(*pid), "status")
	if e != nil || !strings.Contains(string(reader), "Uid:\t0\t0\t0\t0") && !strings.Contains(string(reader), "Uid: 0 0 0 0") {
		r.Reason = "CHROOTCTL_ROOT_PID_NOT_OBSERVED"
		return 2
	}
	// GID is checked strictly from kernel-owned /proc and must also be zero.
	gid := false
	for _, line := range strings.Split(string(reader), "\n") {
		if !strings.HasPrefix(line, "Gid:") {
			continue
		}
		fields := strings.Fields(strings.TrimPrefix(line, "Gid:"))
		if len(fields) == 4 && fields[0] == "0" && fields[1] == "0" && fields[2] == "0" && fields[3] == "0" {
			gid = true
		}
	}
	if !gid {
		r.Reason = "CHROOTCTL_ROOT_GROUP_NOT_OBSERVED"
		return 2
	}
	v := brokeridentity.RootVerifier{Pin: brokeridentity.ModulePin{Name: "chrootctl", ModuleSealSHA256: *seal, SELinuxContext: *context}, Proc: proc, Modules: brokeridentity.InstalledModuleAttestor{}}
	if _, e = v.VerifyPeer(brokeripc.KernelPeer{PID: int32(*pid), UID: 0, GID: 0}); e != nil {
		r.Reason = "CHROOTCTL_LIVE_SEAL_OR_SELINUX_NOT_ATTESTED"
		return 2
	}
	r.State = "PASS_R1_LIVE_CHROOTCTL_MODULE_PROCESS_ONLY"
	r.ProcessAttested = true
	return 0
}
