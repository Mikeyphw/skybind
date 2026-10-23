#!/usr/bin/env python3
"""NATIVE-02 source-level security contract. Does not certify execution on device."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3]
JAVA=Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
AIDL=Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl')
class Violation(Exception): pass
def need(ok,reason):
    if not ok: raise Violation(reason)
def verify(root=ROOT):
    def get(rel):
        p=root/rel
        need(p.is_file() and not p.is_symlink(),'MISSING:'+str(rel))
        return p.read_text()
    aidl=get(AIDL);svc=get(JAVA/'bridge/RootReadBridgeService.kt')
    ses=get(JAVA/'bridge/RootReadSession.kt');vm=get(JAVA/'bridge/SkybindSessionViewModel.kt')
    ui=get(JAVA/'ui/SkybindApp.kt');activity=get(JAVA/'MainActivity.kt')
    for exact in ('String previewStartMount(String sessionId, String mountName)',
                  'String previewStopMount(String sessionId, String mountName)',
                  'String previewRestartMount(String sessionId, String mountName)',
                  'String previewReconcileMount(String sessionId)',
                  'String confirmMount(String sessionId, String previewId)'):
        need(exact in aidl,'AIDL_TYPED_OPERATION_MISSING')
    need('String previewMount(String sessionId, String action' not in aidl,
         'UNRESTRICTED_ACTION_SELECTOR_IN_BINDER')
    need('authenticatedCaller()' in svc and 'Process.myUid() != 0' in svc and
         'getPackagesForUid(caller)' in svc and 'socket.peerCredentials.uid != 0' in svc,
         'ROOT_IDENTITY_GUARD_MISSING')
    for field in ('private fun previewMountTicket(', 'override fun previewStartMount(',
                  'override fun previewStopMount(', 'override fun previewRestartMount(',
                  'override fun previewReconcileMount(', 'mountTickets.remove(previewId)', 'mountTicket.session != session',
                  'mountTicket.deadline <= SystemClock.elapsedRealtime()',
                  'session in forgottenSessions', 'mountTickets.entries.removeAll { it.value.session == session }',
                  'registry.optLong("revision", -1) != mountTicket.revision',
                  'checkedMountState(mountTicket.name)',
                  'state.optInt("pid", 0) != mountTicket.pid',
                  '"mount.start.preview"', '"preview"', 'mountTicket.proof',
                  '"mount.stop"', '"mount.restart"', '"mount.reconcile"',
                  '"reconcile" else "run"',
                  'if (mountTicket.action == "reconcile")',
                  'socket.shutdownOutput()', 'out.size() + n > 262144'):
        need(field in svc,'LIFECYCLE_SECURITY_GUARD_MISSING:'+field)
    for forbidden in ('Shell.cmd(', 'Runtime.getRuntime(',
                      '"remote.transfer.start"'):
        need(forbidden not in svc,'LIFECYCLE_SCOPE_ESCALATED:'+forbidden)
    need('configTickets.remove(previewId)' in svc and
         'rpc("config.apply", "run", JSONObject()' in svc,
         'CONFIG_AUTHORITY_MUST_BE_PROOF_BOUND')
    need('"run", checkedReadArguments' not in svc and
         'rpc(method, "query", checkedReadArguments(method, arguments))' in svc,
         'UNREVIEWED_QUERY_TO_WRITE_ESCALATION')
    need('fun previewMount(' in ses and 'fun confirmMount(' in ses and
         all('api.preview'+a+'Mount(' in ses for a in ('Start','Stop','Restart','Reconcile')) and
         'remote !== api || sessionId != current' in ses and
         'fun previewMount(' in vm and 'fun confirmPreparedMount()' in vm and
         'preparedMount = null' in vm and 'mountOperation?.cancel()' in vm and
         'bridge.confirmMount(plan)' in vm and 'coordinator.refresh()' in vm,
         'SESSION_MUTATION_IDENTITY_OR_REFRESH_MISSING')
    need('onPreviewMount = session::previewMount' in activity and
         'onConfirmMount = session::confirmPreparedMount' in activity and
         'mount-action-consent' in ui and 'mount-action-confirm' in ui and
         'enabled = !mountBusy && acknowledged' in ui and
         '"mount-reconcile"' in ui and '"mount-stop-${mount.id}"' in ui,
         'EXPLICIT_UI_CONSENT_MISSING')
    need('onPreviewMount(' not in activity and 'session.previewMount(' not in activity,
         'AUTOMATIC_MUTATION_FROM_LIFECYCLE')
    need('rollbackTickets.remove(previewId)' in svc and
         'rpc("config.rollback", "run"' in svc and
         'ticket.session != session' in svc, 'UNREVIEWED_ROLLBACK_SCOPE')
    need('rollbackTickets.remove(previewId)' in svc and
         'rpc("config.rollback", "run"' in svc and
         'ticket.session != session' in svc, 'UNREVIEWED_ROLLBACK_SCOPE')
    return {'state':'PASS_NATIVE_02_STATIC_GUARD_ONLY','backend_mutation':'TYPED_PREVIEW_CONFIRM',
            'android_built':False,'real_device_tested':False,'personal_apk_qualified':False}
if __name__=='__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError) as e:
        print(json.dumps({'state':'BLOCKED','reason':str(e)},sort_keys=True));raise SystemExit(2)
