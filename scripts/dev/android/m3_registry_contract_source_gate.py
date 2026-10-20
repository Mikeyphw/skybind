#!/usr/bin/env python3
"""Source-only M3 producer/consumer contract: never installs, invokes root or runs jobs."""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]

class Violation(Exception):
    pass

def verify(root=ROOT):
    def checked(rel, tokens):
        file = root / rel
        if not file.is_file() or file.is_symlink():
            raise Violation("MISSING_CONTRACT_FILE:"+rel)
        data = file.read_text()
        for token in tokens:
            if token not in data:
                raise Violation("M3_REGISTRY_CONTRACT_MISSING:"+rel+":"+token)
        return data

    go = checked('internal/jobs/jobs.go', (
        'func Empty() Registry { return Registry{SchemaVersion: 1, Jobs: []Job{}} }',
        'r.Jobs = append([]Job{}, r.Jobs...)',
        '"registry": clone(s.state.Registry)',
        '"runs": append([]Run{}, s.state.Runs...)'))
    if 'r.Jobs = append([]Job(nil), r.Jobs...)' in go:
        raise Violation('NIL_EMPTY_REGISTRY_RETURNED')
    checked('internal/jobs/jobs_test.go', (
        'TestEmptyJobRegistryIsArrayInStatusAndSnapshot',
        'TestJobRegistryCloneKeepsInputIsolated'))
    reader = checked('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/LiveReadSnapshotReader.kt', (
        'require(registry.has("jobs"))',
        'registry.isNull("jobs")',
        'registry.getInt("schema_version") == 1',
        'registry.getLong("revision") >= 0',
        'SnapshotStageException("jobs.status")'))
    if 'optJSONArray("jobs") ?: JSONArray()' in reader:
        raise Violation('MISSING_JOBS_SILENTLY_ACCEPTED')
    checked('android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadSession.kt', (
        'catch (e: SnapshotStageException)',
        'Snapshot rejected at ${e.operation}'))
    checked('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveReadGatewayTest.kt', (
        'legacyNullEmptyRegistryIsReadOnlyAndOnline',
        'absentJobRegistryIsStillRejected',
        'badJobRegistryRevisionIsStillRejected'))
    checked('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt', (
        'snapshot.link == LinkState.UNSUPPORTED',
        'SKYBIND_M3_BLOCKED_JOBS_STATUS',
        'it.enabled && (it.kind == "check" || it.kind == "copy")',
        'session.previewJob(selected.name)'))
    runner = checked('scripts/dev/android/m2_live_device.py', (
        'SKYBIND_M3_BLOCKED_JOBS_STATUS',
        'SKYBIND_M3_BLOCKED_API_MISMATCH',
        'SKYBIND_M3_BLOCKED_ROOT_AUTH'))
    if 'm3-job-run-live' in runner:
        raise Violation('IMPLICIT_JOB_EXECUTION_LANE')
    return dict(state='PASS_M3_REGISTRY_CONTRACT_SOURCE_ONLY',
                hosted_android_compiled=False,
                m3_preview_device_qualified=False,
                m3_job_execution_device_qualified=False,
                release_qualified=False)

if __name__ == '__main__':
    try: print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as exc:
        print(json.dumps(dict(state='FAILED_OR_BLOCKED', reason=str(exc))))
        raise SystemExit(2)
