#!/usr/bin/env python3
"""Detect Kotlin property generated accessors that collide with declared methods.

Source guard for known NATIVE-05 CI failure class; it is NOT a substitute
for hosted Kotlin/AndroidTest compilation or device qualification.
"""
from __future__ import annotations
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[3]
MAIN = Path('android-app/app/src/main/java')
PROPERTIES = re.compile(r'(?m)^\s*(?:private\s+|internal\s+|public\s+|protected\s+|lateinit\s+|override\s+)*var\s+([A-Za-z_][A-Za-z_0-9]*)\s*(?::|by\b|=)')
METHODS = re.compile(r'\bfun\s+(get[A-Z][A-Za-z_0-9]*|set[A-Z][A-Za-z_0-9]*)\s*\(')

class Collision(Exception): pass

# In androidx.compose.ui.test, these are SemanticsNodeInteraction member methods,
# not package-level declarations. Importing them causes AndroidTest Kotlin
# compilation to fail even though ordinary calls like node.assertExists() work.
INVALID_ANDROIDTEST_IMPORTS = re.compile(
    r'(?m)^\s*import\s+androidx\.compose\.ui\.test\.(assertExists|assertDoesNotExist)\s*$'
)

def invalid_androidtest_imports(source: str) -> list[str]:
    return INVALID_ANDROIDTEST_IMPORTS.findall(source)

def find_collisions(source: str) -> list[str]:
    # Simple source guard deliberately errs on denying potential collisions;
    # Android Kotlin compiler remains the ultimate authority.
    methods = set(METHODS.findall(source))
    clashes = []
    for name in PROPERTIES.findall(source):
        # Kotlin synthetic accessors follow the uppercased property name.
        stem = name[0].upper() + name[1:]
        for method in ('get' + stem, 'set' + stem):
            if method in methods and method not in clashes:
                clashes.append(method)
    return clashes

def verify(root: Path=ROOT) -> dict:
    sources = sorted((root / MAIN).rglob('*.kt'))
    if not sources: raise Collision('KOTLIN_SOURCES_MISSING')
    for path in sources:
        if not path.is_file() or path.is_symlink(): raise Collision('SOURCE_NOT_REGULAR')
        clashes = find_collisions(path.read_text(encoding='utf-8'))
        if clashes: raise Collision('KOTLIN_JVM_ACCESSOR_COLLISION:' + str(path.relative_to(root)) + ':' + ','.join(clashes))
    test_sources = sorted((root / 'android-app/app/src/androidTest').rglob('*.kt'))
    if not test_sources: raise Collision('ANDROIDTEST_KOTLIN_SOURCES_MISSING')
    for path in test_sources:
        if not path.is_file() or path.is_symlink(): raise Collision('ANDROIDTEST_SOURCE_NOT_REGULAR')
        bad = invalid_androidtest_imports(path.read_text(encoding='utf-8'))
        if bad:
            raise Collision('ANDROIDTEST_COMPOSE_IMPORT_UNRESOLVED:' +
                            str(path.relative_to(root)) + ':' + ','.join(bad))
    activity = (root / MAIN / 'io/github/mikeyphw/skybind/MainActivity.kt').read_text()
    viewmodel = (root / MAIN / 'io/github/mikeyphw/skybind/bridge/SkybindSessionViewModel.kt').read_text()
    if not ('private fun updateBkxBackgroundPreference(keep: Boolean)' in activity and
            'onBkxKeepBackgroundChanged = ::updateBkxBackgroundPreference' in activity and
            'onAutoConnectChanged = session::updateAutoConnectPreference' in activity and
            'fun updateAutoConnectPreference(enabled: Boolean)' in viewmodel):
        raise Collision('NATIVE_PERSONAL_PREFERENCE_HANDLER_WIRING_DRIFT')
    return {'status': 'PASS_NATIVE_KOTLIN_SETTER_SOURCE_GUARD_ONLY', 'files_checked': len(sources),
            'android_test_files_checked': len(test_sources),
            'android_compiled': False, 'android_test_compiled': False, 'device_qualified': False}

if __name__ == '__main__':
    try: print(json.dumps(verify(),sort_keys=True))
    except (Collision, OSError, UnicodeError) as exc:
        print(json.dumps({'status':'BLOCKED', 'reason':str(exc)},sort_keys=True))
        raise SystemExit(2)
