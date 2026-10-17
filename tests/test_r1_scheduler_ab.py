"""Source-level fail-closed qualification tests; no hosted/device/full Go work."""
import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/dev/qualification/r1_scheduler_ab.py'
spec = importlib.util.spec_from_file_location('r1_scheduler_ab', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SchedulerABContract(unittest.TestCase):
    def test_contract_jobs_locked(self):
        self.assertEqual(len(mod.ALL_JOBS), 8)
        self.assertEqual(len(mod.GO_JOBS), 4)
        self.assertIn('skybind_go.isolated-regression', mod.GO_JOBS)

    def test_native_devtool_wrapper_uses_target_local_readonly_job(self):
        import tomllib
        c = tomllib.loads((ROOT/'.devtool.toml').read_text())
        self.assertEqual(c['wrapper']['commands']['r1-scheduler-plan']['workflow'], 'r1-scheduler-plan')
        job = c['targets']['skybind_release']['jobs']['r1-scheduler-plan']
        self.assertTrue(job['metadata']['read_only'])
        self.assertEqual(job['command'], ['python3','../scripts/dev/qualification/r1_scheduler_ab.py','plan'])
        self.assertEqual(c['targets']['skybind_release']['workflows']['r1-scheduler-plan'], ['job:r1-scheduler-plan'])

    def test_policy_matches_qw1(self):
        import tomllib
        c = tomllib.loads((ROOT/'.devtool.toml').read_text())
        self.assertFalse(c['workspace']['scheduler']['parallel'])
        self.assertFalse(c['targets']['skybind_go']['jobs']['isolated-regression']['metadata']['read_only'])

    def test_plan_rejects_missing_or_concurrent_go_jobs(self):
        import subprocess
        def envelope(together=False, missing=False):
            names = sorted(mod.ALL_JOBS)
            if missing:
                names = names[:-1]
            nodes = []
            waves = []
            for i, name in enumerate(names):
                nodes.append(dict(key=f'node{i}', job_key=name, writes_known=True,
                                  read_only=name != 'skybind_go.isolated-regression',
                                  writes=['build/evidence/go-regression-isolated'] if name == 'skybind_go.isolated-regression' else [],
                                  global_reservations=['skybind-go-build-cache'] if name in mod.GO_JOBS else []))
                waves.append({'nodes':[f'node{i}']})
            if together and len(mod.GO_JOBS & set(names)) >= 2:
                gos=[n['key'] for n in nodes if n['job_key'] in mod.GO_JOBS]
                waves=[{'nodes':gos}]+[{'nodes':[n['key']]} for n in nodes if n['key'] not in gos]
            body={'ok':True,'exit_code':0,'data':{'action':'r1-full-regression','targets':['skybind_release'],
                  'schedule':{'parallel_effective':True,'max_parallel_nodes':3,
                              'nodes':nodes,'waves':waves}}}
            return subprocess.CompletedProcess([],0,json.dumps(body),'')
        with mock.patch.object(mod.subprocess, 'run', return_value=envelope()):
            self.assertEqual(mod.plan('candidate')['max_concurrent_go_jobs'], 1)
        for kw in ({'missing':True},{'together':True}):
            with mock.patch.object(mod.subprocess, 'run', return_value=envelope(**kw)):
                with self.assertRaises(mod.GateError):
                    mod.plan('candidate')

    def test_go_receipt_validates_source_and_independent_log_hash(self):
        with tempfile.TemporaryDirectory() as td:
            tmp=Path(td)
            log=tmp/'skybind_example.jsonl'
            log.write_bytes(b'{"Action":"pass"}\n')
            row=dict(package='skybind/example', valid=True, waitdelay=False, timed_out=False,
                     exit_code=0, log=log.name, log_sha256=hashlib.sha256(log.read_bytes()).hexdigest())
            item={'schema':'skybind-go-isolated-regression-v1','source_commit':'a'*40,
                  'complete':True,'qualified':True,'selection_full':True,'source_unchanged':True,
                  'discovered_packages':1,'selected_packages':1,'source_sha256':'c'*64,'results':[row]}
            summary=tmp/'summary.json'
            summary.write_text(json.dumps(item))
            with mock.patch.object(mod,'ROOT',tmp):
                self.assertEqual(mod.check_go_receipt(summary,'a'*40)['package_count'],1)
                for defect in ({'qualified':False},{'selection_full':False},{'source_commit':'b'*40},
                               {'discovered_packages':2}):
                    damaged={**item, **defect}
                    summary.write_text(json.dumps(damaged))
                    with self.assertRaises(mod.GateError):
                        mod.check_go_receipt(summary,'a'*40)
                summary.write_text(json.dumps(item))
                log.write_bytes(b'tampered!')
                with self.assertRaises(mod.GateError):
                    mod.check_go_receipt(summary,'a'*40)

    def test_no_android_or_release_side_effects_in_command(self):
        for mode in ('baseline','candidate'):
            base, flags=mod.command(mode)
            self.assertEqual(base[0],'devtool')
            self.assertNotIn('gradle', base + flags)
            self.assertNotIn('android', base + flags)
            self.assertNotIn('release', base + flags)
        self.assertEqual(mod.command('candidate')[1],['--workflow-parallel','--workflow-max-workers','3'])
        self.assertEqual(mod.command('baseline')[1],['--no-workflow-parallel'])

if __name__ == '__main__':
    unittest.main()
