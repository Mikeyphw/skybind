# Test fail-closed Go JSON event interpretation without invoking Go.
import json
from pathlib import Path
import tempfile
import unittest
from scripts.dev.diagnostics.go_all_packages import parse_events

PKG = 'skybind/internal/fixture'

class PerPackageEventContract(unittest.TestCase):
    def parse(self, events, has_tests=True, rc=0):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'go.jsonl'
            p.write_text(''.join(json.dumps(e)+'\n' for e in events))
            return parse_events(p, PKG, has_tests, rc)

    def start(self):
        return {'Action':'start','Package':PKG}

    def terminal(self, action, *, pkg=PKG, test=None, output=None):
        e={'Action':action, 'Package':pkg}
        if test is not None: e['Test']=test
        if output is not None: e['Output']=output
        return e

    def test_success_requires_exactly_one_package_terminal_pass(self):
        self.assertTrue(self.parse([self.start(), self.terminal('pass')])['valid'])
        self.assertFalse(self.parse([self.start()])['valid'])
        self.assertFalse(self.parse([self.start(),self.terminal('pass'),self.terminal('pass')])['valid'])

    def test_test_fail_cannot_be_overridden_by_package_pass(self):
        events=[self.start(),self.terminal('fail',test='TestFailure'),self.terminal('pass')]
        self.assertFalse(self.parse(events)['valid'])
        self.assertFalse(self.parse([self.start(),self.terminal('pass')],rc=1)['valid'])

    def test_other_package_or_invalid_json_never_passes(self):
        self.assertFalse(self.parse([self.start(),self.terminal('pass',pkg='other/package')])['valid'])
        self.assertFalse(self.parse([{'Action':'pass','Package':PKG}, {'Action':'unknown','Package':PKG}])['valid'])

    def test_missing_tests_skip_requires_no_test_files(self):
        self.assertTrue(self.parse([self.start(),self.terminal('skip')],has_tests=False)['valid'])
        self.assertFalse(self.parse([self.start(),self.terminal('skip')],has_tests=True)['valid'])

    def test_go_waitdelay_blocks_even_zero_process_exit(self):
        events=[self.start(),self.terminal('output',output='exec: WaitDelay expired before I/O complete'),self.terminal('pass')]
        self.assertFalse(self.parse(events)['valid'])

if __name__=='__main__':
    unittest.main()
