"""Target isolation and fixture provenance regressions; no Android commands."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/dev/android'))
import m3_adb_fixture as f

class RemoteFixtureTests(unittest.TestCase):
    def test_target_serial_rejects_shell_metacharacters(self):
        for serial in ['; rm -rf /','x y','../oops','\n','']:
            with self.subTest(serial=serial),self.assertRaises(f.Blocked):
                f.run_adb(serial,'get-state')

    def test_remote_adb_not_implicit_host(self):
        class Result:
            returncode=0
            stdout='device\n'
        with patch.object(f.subprocess,'run',return_value=Result()) as called:
            self.assertEqual(f.run_adb('emulator-5554','get-state'),'device')
            self.assertEqual(called.call_args.args[0],['adb','-s','emulator-5554','get-state'])

    def test_remote_rpc_restricts_operations(self):
        with self.assertRaisesRegex(f.Blocked,'OPERATION_NOT_ALLOWLISTED'):
            f.rpc('emulator-5554','jobs.run',{})

    def test_remote_registry_accepts_only_verified_check_and_copy(self):
        obj={'registry':{'schema_version':1,'revision':5,'jobs':None},'runs':[]}
        with patch.object(f,'rpc',return_value=obj):
            self.assertEqual(f.registry('emulator-5554')[0]['jobs'],[])
        obj['registry']['jobs']=[{'name':'unrelated','kind':'sync'}]
        with patch.object(f,'rpc',return_value=obj),self.assertRaisesRegex(f.Blocked,'SYNC'):
            f.registry('emulator-5554')
        obj['registry']['jobs']=[{'name':'M3DisposableCheck','kind':'copy'}]
        with patch.object(f,'rpc',return_value=obj),self.assertRaisesRegex(f.Blocked,'IDENTITY_CONFLICT'):
            f.registry('emulator-5554')
        obj['registry']['jobs']=[f.check.definition()]
        obj['runs']=[{'name':'M3DisposableCheck','state':'RUNNING'}]
        with patch.object(f,'rpc',return_value=obj),self.assertRaisesRegex(f.Blocked,'RUN_ACTIVE'):
            f.registry('emulator-5554')

    def test_bounded_exact_membership_and_hashes(self):
        for kind,n in [('check',64),('copy',64)]:
            root,dirs,hashes=f.fixture_paths(kind,n,'prepared')
            self.assertEqual(len(dirs),3)
            self.assertTrue(all(str(p).startswith(str(root)+'/') for p in hashes))
            self.assertEqual(len(hashes),2*n+1 if kind=='check' else n+2)
        for kind,low,high in [('check',63,4097),('copy',63,1025)]:
            for n in [low,high]:
                with self.assertRaisesRegex(f.Blocked,'FILE_COUNT_INVALID'):
                    f.fixture_paths(kind,n,'prepared')
        prepared=f.fixture_paths('copy',64,'prepared')[2]
        completed=f.fixture_paths('copy',64,'complete')[2]
        self.assertEqual(len(completed)-len(prepared),64)
        self.assertEqual({p:v for p,v in completed.items() if p in prepared},prepared)

    def test_remote_scan_refuses_extra_and_symlink(self):
        _,dirs,hashes=f.fixture_paths('copy',64,'prepared')
        with patch.object(f,'shelltest',return_value=True), \
             patch.object(f,'root',return_value='\n'.join(sorted(dirs|set(hashes)|{'/unreviewed'}))):
            with self.assertRaisesRegex(f.Blocked,'FOREIGN_OR_MISSING'):
                f.scan('emulator-5554','copy',64,'prepared')
        commands=[]
        def fake_root(serial,command,timeout=90,stage='ROOT_COMMAND'):
            commands.append(command)
            if '-type l' in command:return '/storage/emulated/0/Download/.skybind-m3-copy/source/fake-link'
            return '\n'.join(sorted(dirs|set(hashes)))
        with patch.object(f,'shelltest',return_value=True),patch.object(f,'root',side_effect=fake_root):
            with self.assertRaisesRegex(f.Blocked,'SYMLINK'):
                f.scan('emulator-5554','copy',64,'prepared')

    def test_probe_prefers_verified_su_and_falls_back_to_root_adbd(self):
        from types import SimpleNamespace
        def fake_su(serial,*args,**kw):
            if 'su -c' in args[-1]:
                return SimpleNamespace(returncode=0,stdout='0\n',stderr='')
            raise AssertionError('unexpected root method')
        with patch.object(f,'run_adb',side_effect=fake_su) as adb:
            self.assertEqual(f.root_mode('emulator-5554'),'su')
            self.assertEqual(adb.call_count,1)
        def fake_adbd(serial,*args,**kw):
            if 'su -c' in args[-1]:
                return SimpleNamespace(returncode=1,stdout='',stderr='su: not found')
            return SimpleNamespace(returncode=0,stdout='0\n',stderr='')
        with patch.object(f,'run_adb',side_effect=fake_adbd) as adb:
            self.assertEqual(f.root_mode('emulator-5554'),'adbd')
            self.assertEqual(adb.call_count,2)
        def unrooted(serial,*args,**kw):
            return SimpleNamespace(returncode=1,stdout='',stderr='permission denied')
        with patch.object(f,'run_adb',side_effect=unrooted):
            with self.assertRaisesRegex(f.Blocked,'TARGET_ROOT_UID_NOT_VERIFIED'):
                f.root_mode('emulator-5554')

    def test_root_shell_preserves_json_and_never_calls_adb_root(self):
        command=f.CLI+" operation jobs.preview '{\"candidate\":{\"jobs\":[]}}'"
        for mode,needle in [('su',"su -c "),('adbd','/system/bin/sh -c ')]:
            with self.subTest(mode=mode),patch.dict(f._ROOT_MODE,{'emulator-5554':mode},clear=True), \
                 patch.object(f,'run_adb',return_value='ok') as adb:
                self.assertEqual(f.root('emulator-5554',command,stage='RPC_JOBS_PREVIEW'),'ok')
                args=adb.call_args.args
                self.assertEqual(args[0],'emulator-5554')
                self.assertEqual(args[1],'shell')
                self.assertTrue(args[2].startswith(needle))
                self.assertIn('jobs.preview',args[2])
                self.assertEqual(adb.call_args.kwargs['stage'],'RPC_JOBS_PREVIEW')
                self.assertNotIn('adb root',args[2])
                # shlex.split models Android's shell argv parsing after adb shell.
                import shlex
                self.assertEqual(shlex.split(args[2])[-1],command)

    def test_adb_failure_reports_stage_without_leaking_stdout(self):
        from types import SimpleNamespace
        failed=SimpleNamespace(returncode=127,stdout='token=secret_credentials',stderr='su: not found')
        with patch.object(f.subprocess,'run',return_value=failed):
            with self.assertRaisesRegex(f.Blocked,'stage=ROOT_SU_UID_PROBE exit=127 category=NOT_FOUND') as caught:
                f.run_adb('emulator-5554','shell','su -c x',stage='ROOT_SU_UID_PROBE')
        self.assertNotIn('secret_credentials',str(caught.exception))

    def test_target_records_root_mode_on_selected_serial_only(self):
        from types import SimpleNamespace
        def fake(serial,*args,**kw):
            if args == ('get-state',): return 'device'
            if args == ('shell','getprop ro.build.fingerprint'): return 'build/test'
            raise AssertionError(args)
        with patch.dict(f._ROOT_MODE,{},clear=True),patch.object(f,'run_adb',side_effect=fake), \
             patch.object(f,'root_mode',return_value='adbd'):
            self.assertEqual(len(f.target('emulator-5554')),64)
            self.assertEqual(f._ROOT_MODE,{'emulator-5554':'adbd'})

    def test_no_implicit_mutation(self):
        from types import SimpleNamespace
        with patch.object(f,'target',return_value='a'*64), \
             patch.object(f,'registry',return_value=({'revision':3,'jobs':[]},[])), \
             patch.object(f,'stage') as stage:
            self.assertEqual(f.run(SimpleNamespace(serial='emulator-5554',action='inspect',apply=False,files=512,copy_phase='prepared')),0)
            with self.assertRaisesRegex(f.Blocked,'EXPLICIT_--apply_REQUIRED'):
                f.run(SimpleNamespace(serial='emulator-5554',action='prepare-check',apply=False,files=512,copy_phase='prepared'))
            stage.assert_not_called()

if __name__=='__main__': unittest.main()
