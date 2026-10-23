#!/usr/bin/env python3
"""M2 read-only native browser contracts; no APK builds, root, ADB or secrets."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('android-app/app/src/main/java/io/github/mikeyphw/skybind')
TEST = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/RemoteBrowserTest.kt')
class Violation(Exception): pass

def need(value, code):
    if not value: raise Violation(code)

def verify(root=ROOT):
    def get(rel):
        f=root/rel
        need(f.is_file() and not f.is_symlink(), 'MISSING_'+f.name)
        return f.read_text()
    bridge=get(MAIN/'bridge/RootReadBridgeService.kt')
    reader=get(MAIN/'bridge/RemoteBrowseReader.kt')
    model=get(MAIN/'model/RemoteBrowseModel.kt')
    session=get(MAIN/'bridge/RootReadSession.kt')
    vm=get(MAIN/'bridge/SkybindSessionViewModel.kt')
    activity=get(MAIN/'MainActivity.kt')
    ui=get(MAIN/'ui/SkybindApp.kt')
    test=get(TEST)
    # Android's SemanticsNodeInteraction exposes these as members, not
    # package-level androidx.compose.ui.test imports. This broke hosted
    # :app:compileDebugAndroidTestKotlin in GitHub Actions #39196292135.
    android_test_root = Path('android-app/app/src/androidTest/java/io/github/mikeyphw/skybind')
    forbidden_assertion_imports = (
        'import androidx.compose.ui.test.assertExists',
        'import androidx.compose.ui.test.assertDoesNotExist',
    )
    for test_name in ('NativeLifecycleTest.kt', 'NativeUiTest.kt', 'RemoteBrowserTest.kt'):
        test_body = get(android_test_root / test_name)
        need(not any(imp in test_body for imp in forbidden_assertion_imports),
             'UNRESOLVED_COMPOSE_TEST_ASSERTION_IMPORT_' + test_name)
    need('"provider.browse"' in bridge and 'if (op == "provider.browse")' in bridge and
         'BrowseAddress.endpoint(name, path)' in bridge and 'socket.peerCredentials.uid != 0' in bridge and
         'rpc(method, "query", checkedReadArguments(method, arguments))' in bridge and
         'rpc("job.run", "run", JSONObject()' in bridge and
         'if (op !in allowed || raw == null' in bridge,
         'BROWSE_ROOT_ALLOWLIST_UNSAFE')
    for forbidden in ('"remote.transfer.start"', '"provider.crypt.password.set"'):
        need(forbidden not in bridge, 'UNBOUNDED_ROOT_BRIDGE_'+forbidden)
    need('"config.apply"' not in bridge.split('private fun checkedReadArguments(', 1)[1].split('private fun checkedMountState(', 1)[0], 'CONFIG_WRITE_IN_BROWSER_QUERY_ALLOWLIST')
    # NATIVE-02 mount methods are separate typed preview/confirm calls, not an
    # excuse to mutate provider.browse query class. M3 jobs remain separate.
    need('tickets.remove(previewId)' in bridge and
         'ticket.session != session' in bridge and
         'ownedRuns[runId] != session' in bridge, 'M3_MUTATION_NOT_SESSION_SCOPED')
    need('BrowseAddress.endpoint(remote, path)' in reader and 'provider.browse' in reader and
         'response.opt("ok") == true' in reader and 'data.length() <= 500)' in reader and
         'require(reported == name || reported == childPath)' in reader,
         'BROWSER_RESPONSE_NOT_FAIL_CLOSED')
    need('it != "." && it != ".."' in model and 'next.length <= 512' in model and
         'fun forSnapshot' in model and '!snapshot.online' in model,
         'BROWSE_PATH_OR_DISCONNECT_UNSAFE')
    need('suspend fun browse(' in session and 'val api = remote ?:' in session and
         'withContext(Dispatchers.IO)' in session, 'UNPAIRED_BROWSE_ALLOWED')
    need('val token = ++browseGeneration' in vm and 'token == browseGeneration && snapshot.online' in vm and
         'browseAt(remoteName, next)' in vm and 'clearBrowser()' in vm and
         'browser.entries.none { it.name == name && it.directory }' in vm,
         'STALE_FOLDER_RESULT_OR_NON_FOLDER_ACCESS')
    need('onBrowseRemote = session::selectRemote' in activity and
         'onBrowseFolder = session::openFolder' in activity,
         'BROWSE_NOT_WIRED_TO_UI')
    for token in ('browser.forSnapshot(safe)', '"browser-path"', '"browser-up"',
                  '"browser-switch-remote"', '"folder-${entry.name}"', '"browser-write-disabled"'):
        need(token in ui,'UI_BROWSER_MISSING_'+token)
    native_ui=get(TEST.parent/'NativeUiTest.kt')
    # Real API-36 device acceptance: 18/19 PASS. The offline browser does not
    # render its search field, so asserting a disabled node is invalid.
    browser_section = ui.split('@Composable private fun BrowserPage(', 1)
    need(len(browser_section) == 2, 'BROWSER_COMPOSABLE_MISSING')
    browser_section = browser_section[1].split('@Composable private fun JobsPage(', 1)[0]
    offline_at = browser_section.find('if (!s.online) {')
    select_at = browser_section.find('} else if (browse.remote == null) {')
    search_at = browser_section.find('testTag("browser-search")')
    need(0 <= offline_at < select_at < search_at and
         'InfoPanel("Remote browser unavailable"' in browser_section and
         browser_section.count('testTag("browser-search")') == 1,
         'DISCONNECTED_BROWSER_MUST_HIDE_SEARCH')
    need('fun unpairedStateHidesStaleServerData' in native_ui and
         'compose.onNodeWithTag("browser-search").assertDoesNotExist()' in native_ui and
         'compose.onNodeWithTag("browser-search").assertIsNotEnabled()' not in native_ui,
         'OFFLINE_SEARCH_TEST_EXPECTATION_MUST_MATCH_UI')
    need('enabled = false' in ui and 'fun rejectsEscapesAndUntrustedListing' in test and
         'fun disconnectedStateHidesFormerContents' in test,
         'BROWSE_NEGATIVE_TESTS_MISSING')
    return {'state':'PASS_M2_REMOTE_BROWSER_SOURCE_ONLY','read_only':True,
            'folder_navigation':True,'stale_response_guard':True,'android_device_tested':False,
            'release_qualified':False}

if __name__ == '__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (Violation,OSError,UnicodeError) as e:
        print(json.dumps({'state':'FAILED_OR_BLOCKED','reason':str(e)},sort_keys=True))
        raise SystemExit(2)
