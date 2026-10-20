"""Source-only M3 empty-registry and fail-closed receipt regressions."""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load(relative):
    spec = importlib.util.spec_from_file_location('m3_registry_gate', ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

GATE = load('scripts/dev/android/m3_registry_contract_source_gate.py')

class M3EmptyRegistryContract(unittest.TestCase):
    def test_source_contract(self):
        self.assertEqual(GATE.verify(ROOT)['state'], 'PASS_M3_REGISTRY_CONTRACT_SOURCE_ONLY')

    def test_preimage_nullable_clone_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for rel in ('internal/jobs/jobs.go', 'internal/jobs/jobs_test.go',
                'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/LiveReadSnapshotReader.kt',
                'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadSession.kt',
                'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveReadGatewayTest.kt',
                'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt',
                'scripts/dev/android/m2_live_device.py'):
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dest)
            go=root/'internal/jobs/jobs.go'
            go.write_text(go.read_text().replace('append([]Job{}, r.Jobs...)',
                'append([]Job(nil), r.Jobs...)'))
            with self.assertRaises(GATE.Violation):
                GATE.verify(root)

    def test_missing_array_silently_defaulted_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for rel in ('internal/jobs/jobs.go', 'internal/jobs/jobs_test.go',
                'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/LiveReadSnapshotReader.kt',
                'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/RootReadSession.kt',
                'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveReadGatewayTest.kt',
                'android-app/app/src/androidTest/java/io/github/mikeyphw/skybind/LiveM3PreviewAcceptanceTest.kt',
                'scripts/dev/android/m2_live_device.py'):
                dest=root/rel
                dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT/rel,dest)
            reader=root/'android-app/app/src/main/java/io/github/mikeyphw/skybind/bridge/LiveReadSnapshotReader.kt'
            reader.write_text(reader.read_text().replace('require(registry.has("jobs"))',
                'val missing = registry.optJSONArray("jobs") ?: JSONArray()'))
            with self.assertRaises(GATE.Violation):
                GATE.verify(root)
