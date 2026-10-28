// Explicit, local, root-only human approval. No cross-UID caller can invoke
// this CLI through API-04; it has no listener or background service.
package main

import (
	"flag"
	"fmt"
	"os"
	"skybind/internal/featuregateway"
)

func main() { os.Exit(run(os.Args[1:])) }
func run(args []string) int {
	if os.Geteuid() != 0 {
		fmt.Fprintln(os.Stderr, "API04_ROOT_OPERATOR_REQUIRED")
		return 2
	}
	f := flag.NewFlagSet("skybind-api04-approve", flag.ContinueOnError)
	id := f.String("preview-id", "", "server-generated preview ID")
	digest := f.String("preview-sha256", "", "exact digest displayed after preview")
	approve := f.Bool("approve-exact", false, "approve this single preview")
	inspect := f.Bool("inspect", false, "show nonsecret details of the preview")
	operation := f.String("operation", "", "expected operation mount.start|mount.stop")
	mount := f.String("mount", "", "expected approved mount")
	if f.Parse(args) != nil || len(f.Args()) != 0 || *id == "" || (*inspect == *approve) {
		fmt.Fprintln(os.Stderr, "API04_EXACT_APPROVAL_REQUIRED")
		return 2
	}
	store, e := featuregateway.OpenMutationStore()
	if e != nil {
		fmt.Fprintln(os.Stderr, "API04_APPROVAL_STORE_DENIED")
		return 2
	}
	if *inspect {
		record, inspectErr := store.Summary(*id)
		if inspectErr != nil {
			fmt.Fprintln(os.Stderr, "API04_APPROVAL_INSPECT_DENIED")
			return 2
		}
		// Do not display ProcessKey, native daemon proof or arbitrary result.
		fmt.Printf("preview_id=%s\noperation=%s\nmount=%s\nstate=%s\nexpires_unix=%d\npreview_sha256=%s\n", record.ID, record.Operation, record.Mount, record.State, record.Expires, record.Digest)
		return 0
	}
	if *digest == "" || *operation == "" || *mount == "" {
		fmt.Fprintln(os.Stderr, "API04_EXACT_APPROVAL_REQUIRED")
		return 2
	}
	if e = store.ApproveExact(*id, *digest, *operation, *mount); e != nil {
		fmt.Fprintln(os.Stderr, "API04_APPROVAL_DENIED")
		return 2
	}
	fmt.Fprintln(os.Stdout, "API04_APPROVED_SINGLE_PREVIEW:", *id)
	return 0
}
