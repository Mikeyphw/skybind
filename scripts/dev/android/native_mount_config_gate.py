#!/usr/bin/env python3
"""NATIVE-03 scoped mount-config security contract; source-only, not APK acceptance."""
from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[3]
MAIN=Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
AIDL=Path('android-app/app/src/main/aidl/io/github/mikeyphw/skybind/bridge/IRootReadBridge.aidl')
class Violation(Exception):pass
def need(ok,reason):
    if not ok:raise Violation(reason)
def verify(root=ROOT):
    def get(rel):
        p=root/rel
        need(p.is_file() and not p.is_symlink(),'MISSING:'+str(rel))
        return p.read_text()
    aidl=get(AIDL);svc=get(MAIN/'bridge/RootReadBridgeService.kt')
    ses=get(MAIN/'bridge/RootReadSession.kt');vm=get(MAIN/'bridge/SkybindSessionViewModel.kt')
    ui=get(MAIN/'ui/SkybindApp.kt');editor=get(MAIN/'ui/MountConfigEditor.kt')
    model=get(MAIN/'model/MountConfigModel.kt');activity=get(MAIN/'MainActivity.kt')
    for name in ('readMountConfiguration','previewCreateMount','previewEditMount',
                 'previewDeleteMount','applyMountConfiguration'):
        need(aidl.count('String '+name+'(')==1 and svc.count('override fun '+name+'(')==1,
             'TYPED_BINDER_METHOD_MISSING:'+name)
    need('String patch(' not in aidl and 'String execute(' not in aidl and
         'String runRaw(' not in aidl and 'String configRpc(' not in aidl,
         'ARBITRARY_CONFIG_RPC_FORBIDDEN')
    for t in ('authenticatedCaller()', 'checkedSession(sessionId)',
              'private fun checkedConfiguredRemotes()', 'remoteName !in checkedConfiguredRemotes()',
              'private fun checkedMountDraft(', 'source.keys().asSequence().toSet() != names',
              'source.length() != names.size', 'private fun checkedRegistry()',
              'session in forgottenSessions', 'if (session !in liveSessions && liveSessions.size >= 32)',
              'configTickets[id] = ConfigTicket(', 'configTickets.remove(previewId)',
              'ticket.session != session', 'ticket.deadline <= SystemClock.elapsedRealtime()',
              'checkedRegistry().getLong("revision") != ticket.revision',
              'if (raw.length > 65_536)', 'if (configTickets.size >= 8)',
              '"config.validate", "query"', '"config.preview", "preview"',
              'rpc("config.apply", "run", JSONObject()',
              'plan.getLong("base_revision") != revision',
              '"candidate_digest"', 'plan.getString("proof")',
              'source.opt(key) !is Boolean', 'source.opt(key) !is Number',
              '!Regex("[0-9]{1,16}").matches(source.opt(key).toString())',
              'if (action == "edit" && spec!!.getString("name") != name)',
              'if (effects.length() !in 1..64)',
              'val ticket = synchronized(gate) { configTickets.remove(previewId) }'):
        need(t in svc,'CONFIG_PRIVILEGE_GUARD_MISSING:'+t)
    config_apply=svc.split('override fun applyMountConfiguration(',1)[1].split('override fun previewRollbackMountConfiguration(',1)[0]
    need('if (ticket.session != session' in config_apply and
         'ticket.deadline <= SystemClock.elapsedRealtime()' in config_apply and
         'configTickets.remove(previewId)' in config_apply and
         'checkedRegistry().getLong("revision") != ticket.revision' in config_apply,
         'CONFIG_APPLY_SESSION_SCOPE_MISSING')
    need(svc.count('rpc("config.apply", "run"')==1 and
         svc.count('rpc("config.preview", "preview"')==1 and
         svc.count('rpc("config.rollback", "run"')==1 and
         '"remote.transfer.start"' not in svc and 'Shell.cmd(' not in svc and
         'Runtime.getRuntime(' not in svc, 'CONFIG_WRITE_LANE_SCOPE_EXPANDED')
    rollback=svc.split('override fun applyRollbackMountConfiguration(',1)[1].split('override fun forgetSession(',1)[0]
    for guard in ('rollbackTickets.remove(previewId)', 'if (ticket.session != session',
                  'ticket.deadline <= SystemClock.elapsedRealtime()',
                  'checkedRegistry().getLong("revision") != ticket.revision',
                  'rpc("config.rollback", "run"', 'JSONObject().put("proof", ticket.proof)'):
        need(guard in rollback, 'ROLLBACK_GUARD_MISSING:'+guard)
    need('String previewRollbackMountConfiguration(' in aidl and
         'String applyRollbackMountConfiguration(' in aidl and
         'configTickets.remove(previewId)' in svc,
         'TYPED_ONE_USE_ROLLBACK_OR_APPLY_MISSING')
    for key in ('"config.validate", "query"', '"field_errors"',
                'candidate.length() - 1', 'field in setOf(', 'code in setOf('):
        need(key in svc, 'STRUCTURED_DAEMON_VALIDATION_MISSING:'+key)
    returned=svc.split('// App gets only a scoped ticket and a human-readable diff, never the daemon proof.',1)
    need(len(returned)==2 and 'put("proof"' not in returned[1].split('override fun applyMountConfiguration',1)[0],
         'DAEMON_PROOF_EXPOSED_TO_APP')
    query=svc.split('private fun checkedReadArguments(',1)[1].split('private fun checkedConfiguredRemotes(',1)[0]
    need('"config.apply"' not in query and '"config.preview"' not in query and
         'rpc(method, "query", checkedReadArguments(method, arguments))' in svc,
         'QUERY_BRIDGE_ESCALATED_TO_WRITE')
    for t in ('api.previewRollbackMountConfiguration(owned)', 'api.applyRollbackMountConfiguration(owned, preview.id)',
              'api.readMountConfiguration(owned)', 'api.previewCreateMount(owned,',
              'api.previewEditMount(owned,', 'api.previewDeleteMount(owned,',
              'api.applyMountConfiguration(owned, preview.id)',
              'remote !== api || sessionId != owned'):
        need(t in ses,'UNVERIFIED_SESSION_CONFIG_RESULT:'+t)
    for t in ('fun previewRegistryRollback()', 'fun confirmRegistryRollback()',
              'fun openMountEditor(', 'bridge.loadMountRegistry()', 'fun updateMountDraft(',
              'configPreview = null', 'fun previewMountConfig()', 'bridge.previewConfig(',
              'fun applyMountConfig()', 'val preview = configPreview ?: return',
              'bridge.applyConfig(preview)', 'coordinator.refresh()',
              'configOperation?.cancel()', 'clearOperations()'):
        need(t in vm,'VIEWMODEL_MISSING_CONFIG_TRANSACTION:'+t)
    connect=vm.split('private fun connectInternal()',1)[1].split('fun openMountEditor(',1)[0]
    need('previewConfig(' not in connect and 'applyConfig(' not in connect and
         'openMountEditor(' not in connect, 'AUTOMATIC_CONFIG_MUTATION_FROM_ROOT_CONNECTION')
    for t in ('fun fieldErrors(): Map<String, String>', 'class ConfigFieldValidation(',
              'fun encode(): String', '"schema_version"', '"revision"', '"mounts"',
              'val low = int(cacheLowPercent, 100)', 'require(low <= high)',
              'fun decode(raw: String): MountRegistryView'):
        need(t in model,'TYPED_MOUNT_SCHEMA_INCOMPLETE:'+t)
    for t in ('"config-field-error-$field"', 'fieldErrors: Map<String, String>',
              'Source', 'Destination', 'Behavior', 'Review', '"config-editor-dialog"',
              '"config-preview"', '"config-consent"', '"config-apply"',
              'enabled = !busy && consent', '"delete"',
              'onChange(draft.copy(', '"config-advanced-toggle"'):
        need(t in editor,'MOUNT_EDITOR_REVIEW_MISSING:'+t)
    for t in ('"mount-rollback"', '"rollback-consent"', '"rollback-confirm"',
              'enabled = approved && !rollbackBusy', '"mount-add"', '"mount-edit-${mount.id}"', '"mount-delete-${mount.id}"',
              'MountConfigEditor(', 'onOpenMountConfig: (String, String) -> Unit', 'if (mountConfigMode != null && mountConfigDraft != null && safe.online)'):
        need(t in ui,'MOUNT_CONFIG_NAVIGATION_MISSING:'+t)
    for t in ('onPreviewRollback = session::previewRegistryRollback',
              'onConfirmRollback = session::confirmRegistryRollback',
              'onDismissRollback = session::dismissRegistryRollback',
              'mountConfigFieldErrors = session.configFieldErrors',
              'onOpenMountConfig = session::openMountEditor', 'onPreviewMountConfig = session::previewMountConfig',
              'onApplyMountConfig = session::applyMountConfig', 'onUpdateMountConfig = session::updateMountDraft'):
        need(t in activity,'MAIN_UI_CONFIG_BINDING_MISSING:'+t)
    return {'state':'PASS_NATIVE_03_CONFIG_SOURCE_SECURITY_ONLY','scope':'TYPED_CONFIG_PREVIEW_APPLY',
            'android_built':False,'device_tested':False,'personal_apk_qualified':False}
if __name__=='__main__':
    try:print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError) as e:
        print(json.dumps({'state':'BLOCKED','reason':str(e)},sort_keys=True));raise SystemExit(2)
