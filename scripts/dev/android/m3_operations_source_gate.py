#!/usr/bin/env python3
"""M3 consolidated app operations source-only security contract (NO APK/ADB)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')

class Violation(Exception):
    pass

def require(value, message):
    if not value:
        raise Violation(message)

def verify(root=ROOT):
    def read(relative):
        path = root / relative
        require(path.is_file() and not path.is_symlink(), 'M3_FILE_MISSING:' + str(relative))
        return path.read_text()
    service = read(BASE/'bridge/RootReadBridgeService.kt')
    session = read(BASE/'bridge/RootReadSession.kt')
    vm = read(BASE/'bridge/SkybindSessionViewModel.kt')
    ui = read(BASE/'ui/SkybindApp.kt')
    model = read(BASE/'model/SkybindReadModel.kt')
    reader = read(BASE/'bridge/LiveReadSnapshotReader.kt')
    aidl = read(Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl'))
    app = read(BASE/'MainActivity.kt')
    instrument = read(Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt'))
    runner = read(Path('scripts/dev/android/m2_live_device.py'))
    launcher = read(Path('scripts/devtool/ci_artifacts_device.py'))
    dag = read(Path('.devtool.toml'))
    def tokens(label, value, required):
        for phrase in required:
            require(phrase in value, label + ':' + phrase)
    tokens('BINDER_EXACT_METHODS', aidl, ('String query(', 'String previewJob(', 'String startPreparedJob(',
        'String cancelOwnedRun(', 'void forgetSession('))
    tokens('PROOF_NOT_CLIENT_CONTROLLED', service, (
        'authenticatedCaller()', 'Process.myUid() != 0', 'Binder.getCallingUid()',
        'getPackagesForUid(caller)', 'signing.apkContentsSigners',
        'rpc(method, "query", checkedReadArguments(method, arguments))',
        'rpc("job.run.preview", "preview", JSONObject().put("name", jobName))',
        'kind !in setOf("check", "copy")', 'result.optBoolean("destructive", true)',
        'tickets[ticket] = Ticket(session, jobName, proof, now + 90_000L)',
        'tickets.remove(previewId)', 'ticket.session != session',
        'rpc("job.run", "run", JSONObject()', 'put("proof", ticket.proof)',
        'if (session !in liveSessions)', 'ownedRuns[id] = session',
        'ownedRuns[runId] != session', 'liveSessions.remove(session)',
        'if (session in forgottenSessions)', 'forgottenSessions.add(session)',
        'rpc("operation.cancel", "cancel", JSONObject().put("id", runId))',
        'tickets.entries.removeAll { it.value.session == session }',
        'ownedRuns.entries.removeAll { it.value == session }',
        'socket.peerCredentials.uid != 0', 'verifySocketLayout()',
        'if (payload.size > 65536)', 'if (out.size() + n > 262144)',
        'response.optString("request_id") != id',
    ))
    # Prevent leaking daemon-issued reusable proof through Android Binder to unprivileged UI.
    returned = service.split('return JSONObject().put("id", ticket)', 1)
    require(len(returned) == 2 and 'put("proof"' not in returned[1].split('override fun startPreparedJob', 1)[0],
            'PROOF_RETURNED_TO_UNPRIVILEGED_APP')
    # Require all run/cancel dispatches to be in their exact, bound methods.
    require(service.count('rpc("job.run", "run"') == 1 and
            service.count('rpc("operation.cancel", "cancel"') == 1,
            'UNREVIEWED_MUTATING_METHOD')
    for unsafe in ('Shell.cmd(', 'Runtime.getRuntime()', 'su -c', 'RootService.stop(',
                   '"remote.transfer.start"', '"jobs.apply"', '"config.apply"',
                   '"mount.start"', '"sync" ||', '"sync", "copy"'):
        require(unsafe not in service, 'UNREVIEWED_PRIVILEGE:' + unsafe)
    tokens('SESSION_SCOPE', session, ('sessionId = UUID.randomUUID().toString()',
        'api.previewJob(current, name)', 'api.startPreparedJob(current, preview.id)',
        'api.cancelOwnedRun(current, id)', 'it.forgetSession(oldSession)',
        'if (remote !== api || sessionId != current)', 'reader = LiveReadSnapshotReader()'))
    tokens('USER_GESTURE_REQUIRED', vm, ('fun previewJob(name: String)',
        'fun confirmPreparedJob()', 'fun cancelOwnedRun(id: String)',
        'val preview = preparedJob ?: return', 'preparedJob = null // one-shot UI action',
        'id !in ownedRunIds', 'fun dismissJobPreview()', 'clearOperations()',
        'delay(3_000L)', 'updateOperationsSnapshot(token)'))
    connect = vm.split('fun connect() {', 1)[1].split('fun previewJob(name:', 1)[0]
    require('startPreparedJob(' not in connect and 'cancelOwnedRun(' not in connect,
            'IMPLICIT_JOB_EXECUTION_ON_CONNECT')
    tokens('USER_CONFIRMATION', ui, ('job-confirm-dialog', 'job-copy-consent',
        'job-confirm-start', 'job-dismiss-preview', 'definition.kind in setOf("check", "copy")',
        'enabled = owned && !busy && job.state == JobState.RUNNING'))
    tokens('DATA_SOURCE', reader, ('jobs.getJSONObject("registry")',
        'JobDefinition(name, kind, obj.getBoolean("enabled"))',
        'require(definitions.map { it.name }.toSet().size == definitions.size)',
        'nonnegative("eta_seconds")', 'nonnegative("files_done")'))
    tokens('FAIL_CLOSED', model, ('definitions = emptyList()', 'fun failClosed()', 'val actionable: Boolean'))
    tokens('MAIN_UI_WIRING', app, ('onPreviewJob = session::previewJob',
        'onConfirmJob = session::confirmPreparedJob', 'onCancelOwnedRun = session::cancelOwnedRun'))
    tokens('ACTUAL_DAEMON_PREVIEW', instrument, ('class LiveM3PreviewAcceptanceTest',
        'session.previewJob(selected.name)', 'SKYBIND_M3_BLOCKED_NO_ELIGIBLE_JOB',
        'session.close()', 'SKYBIND_M3_FAILED_STALE_JOBS'))
    for marker in ('session.startPreparedJob(', 'session.cancelOwnedRun('):
        require(marker not in instrument, 'DEVICE_PREVIEW_TEST_WOULD_MUTATE:' + marker)
    tokens('DEVICE_RUNNER', runner, ('parse_m3_preview', 'm3_preview_device_qualified=False',
        "doc['m3_preview_device_qualified'] = True", 'PASS_M3_REAL_DAEMON_PREVIEW_ONLY',
        'M3_REAL_DAEMON_JOB_PREVIEW_ONLY_NO_EXECUTION'))
    tokens('CI_AUTHENTICATED', launcher, ("'m3-preview-live': 'm3-preview-live'",
        "'m3-preview-live': 'PASS_M3_REAL_DAEMON_PREVIEW_ONLY'",
        'live.installed_pair(serial, manifest, pin)',
        'live.verify_candidate(folder, args.run_id, sha, pin)',
        'LANE_QUALIFICATION_OVERCLAIM', 'm3_preview_device_qualified=False'))
    tokens('REGISTRY_COMPAT', reader, (
        'registry.getInt("schema_version") == 1', 'registry.getLong("revision") >= 0',
        'require(registry.has("jobs"))', 'registry.isNull("jobs")',
        'SnapshotStageException("jobs.status")'))
    tokens('REGISTRY_SOURCE_GUARD', dag, ('[targets.skybind_release.jobs.m3-registry-contract]',))
    tokens('DEVTOOL', dag, ('m3-operations-source = [',
        '[targets.skybind_release.jobs.m3-operations-contract]',
        '[targets.skybind_release.jobs.m3-operations-unit]',
        '[targets.skybind_release.jobs.m3-operations-security]',
        '[wrapper.commands.m3-operations-source]'))
    return dict(state='PASS_M3_CONSOLIDATED_OPERATIONS_SOURCE_ONLY',
        hosted_android_compiled=False, device_qualified=False,
        write_job_device_qualified=False, m3_preview_device_qualified=False,
        full_m3_qualified=False, release_qualified=False)

if __name__ == '__main__':
    try: print(json.dumps(verify(), sort_keys=True))
    except (Violation, OSError, UnicodeError) as e:
        print(json.dumps({'state':'FAILED_OR_BLOCKED', 'reason':str(e)}, sort_keys=True))
        raise SystemExit(2)
