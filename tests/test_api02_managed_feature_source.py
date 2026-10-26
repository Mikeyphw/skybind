"""Reject source weakening; complements real Go code/transport tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import importlib.util

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('api02_source_gate', ROOT/'scripts/dev/android/api02_source_gate.py')
GATE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)

class API02SourceContract(unittest.TestCase):
    def test_current(self):GATE.check()
    def test_no_root_bypass(self):
        original=GATE.src
        def damaged(p):
            x=original(p)
            return x.replace('uid != 0','false') if p=='cmd/skybind/feature.go' else x
        with patch.object(GATE,'src',side_effect=damaged),self.assertRaises(AssertionError):GATE.check()
    def test_no_mutation_admission_bypass(self):
        original=GATE.src
        def damaged(p):
            x=original(p)
            return x.replace('j.ByRequest(call.RequestID)','j.Get(call.RequestID)') if p=='internal/daemon/feature_capabilities.go' else x
        with patch.object(GATE,'src',side_effect=damaged),self.assertRaises(AssertionError):GATE.check()
    def test_no_extra_remote_permission(self):
        original=GATE.src
        def damaged(p):
            x=original(p)
            return x.replace('"mount.list":', '"rclone.copy": protocol.Run,\n "mount.list":') if p=='internal/featureapi/feature.go' else x
        with patch.object(GATE,'src',side_effect=damaged),self.assertRaises(AssertionError):GATE.check()
    def test_no_json_duplicate_bypass(self):
        original=GATE.src
        def damaged(p):
            x=original(p)
            return x.replace('rejectDuplicateJSON(req.Arguments)','json.Valid(req.Arguments)') if p=='internal/featureapi/feature.go' else x
        with patch.object(GATE,'src',side_effect=damaged),self.assertRaises(AssertionError):GATE.check()

if __name__=='__main__': unittest.main()
