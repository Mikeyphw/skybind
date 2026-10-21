#!/usr/bin/env python3
"""Source-only guard for opt-in chrootctl process qualification, not a device run."""
from pathlib import Path
import sys
import tomllib
ROOT=Path(__file__).resolve().parents[3]
def checks():
    d=(ROOT/'scripts/dev/android/r1_chrootctl_process_device.py').read_text()
    cfg=tomllib.loads((ROOT/'.devtool.toml').read_text())
    release=cfg['targets']['skybind_release'];job=release['jobs']['r1-chrootctl-live-process-source'];cmd=job['command']
    return {
      'HOSTED_SOURCE_AND_CHECKSUMS':all(x in d for x in ('head_sha','GITHUB_SOURCE_OR_WORKFLOW_MISMATCH','SHA256SUMS.txt','DIAGNOSTIC_BINARY_SHA_MISMATCH')),
      'NO_SILENT_DEVICE_ACTIVATION':all(x in d for x in ('--live','--operator-approve','INVALID_INDEPENDENT_OPERATOR_APPROVAL')),
      'EXACT_PID_AND_NEGATIVES':all(x in d for x in ('--pid','wrong_seal','wrong_context','check_receipt')),
      'NO_BACKUP_OR_GRANT_ACTIONS':all(x not in d for x in ('ksud module install','rclone rcat','rclone delete','grants_issued\':True')),
      'RELEASE_CWD_RESOLUTION':cmd==['python3','-B','../scripts/dev/android/r1_chrootctl_device_source_gate.py'] and release['root']=='release',
    }
def main():
    checks_map=checks()
    for k,ok in checks_map.items():print(('PASS_' if ok else 'FAIL_')+k)
    return 0 if all(checks_map.values()) else 2
if __name__=='__main__':sys.exit(main())
