"""Fail-closed separation of the original 57 CFS1 operations and API04 extensions.

The original 45-obligation / 57-operation planning ledger is immutable.
These two exact native guarded-stop operations are approved later extensions;
the live catalog is NOT allowed to grow by an unreviewed operation.
"""
import json
from pathlib import Path

APPROVED_EXTENSIONS = {
    "mount.stop.preview": {
        "name": "mount.stop.preview",
        "operation_class": "preview",
        "description": "Preview exact owned FUSE mount identity and configuration revision for guarded stop",
        "implementing_overlay": "API04-P3-H1",
        "webui_consumers": "API04 admission and private daemon only",
    },
    "mount.stop.guarded": {
        "name": "mount.stop.guarded",
        "operation_class": "run",
        "description": "Stop owned FUSE mount only after consuming exact revision-bound preview proof",
        "implementing_overlay": "API04-P3-H1",
        "webui_consumers": "API04 mutation gateway only",
    },
}

def require(ok, code):
    if not ok:
        raise AssertionError(code)

def validate_live_catalog(root: Path, *, live=None, historical=None):
    root = Path(root)
    if historical is None:
        historical = json.loads((root/'docs/roadmap/SKYBIND_DEVTOOL_OVERLAY_INDEX.json').read_text())['all_57_typed_operations']
    canonical_path = root/'docs/contracts/typed-operations.json'
    embedded_path = root/'internal/control/operations.json'
    # These are deliberately byte-identical frozen + extension catalogs.
    require(canonical_path.read_bytes() == embedded_path.read_bytes(), 'TYPED_CATALOG_BYTES_DIFFER')
    if live is None:
        live = json.loads(embedded_path.read_text())
    require(isinstance(historical, list) and len(historical) == 57, 'ORIGINAL_57_LEDGER_CHANGED')
    historical_by_name = {e['name']: e for e in historical}
    require(len(historical_by_name) == 57, 'ORIGINAL_57_NAMES_DUPLICATED')
    require(live.get('schema_version') == 1 and live.get('product') == 'Skybind', 'CATALOG_IDENTITY_CHANGED')
    operations = live.get('operations')
    require(isinstance(operations, list), 'CATALOG_OPERATIONS_INVALID')
    by_name = {e['name']: e for e in operations}
    require(len(by_name) == len(operations), 'CATALOG_NAMES_DUPLICATED')
    require(live.get('total') == len(operations), 'CATALOG_COUNT_MISMATCH')
    require(set(by_name) == set(historical_by_name) | set(APPROVED_EXTENSIONS), 'UNAPPROVED_CATALOG_OPERATION')
    for name, original in historical_by_name.items():
        for field in ('name','operation_class','description','implementing_overlay','webui_consumers'):
            require(by_name[name].get(field) == original.get(field), f'ORIGINAL_OPERATION_DRIFT:{name}:{field}')
    for name, approved in APPROVED_EXTENSIONS.items():
        require(by_name[name] == approved, f'APPROVED_EXTENSION_DRIFT:{name}')
    return historical_by_name, by_name
