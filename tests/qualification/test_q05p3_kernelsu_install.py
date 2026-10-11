"""SB-Q05P3: standalone model of a sourced KernelSU module customize hook.

Tests intentionally do NOT claim physical KernelSU/Android device qualification.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / 'module/customize.sh'
FILES = ('module.prop','system/bin/skybind','system/bin/rclone',
         'system/vendor/bin/fusermount3','action.sh','service.sh',
         'post-fs-data.sh','uninstall.sh')


def make_module(root):
    path = root/'stage'
    path.mkdir()
    for file in FILES:
        p=path/file
        p.parent.mkdir(parents=True,exist_ok=True)
        p.write_text('fixture\n')
        p.chmod(0o600)
    return path


def shell(module=None, *, options='', inject='', hook=HOOK):
    # Installer sources customize.sh and then iterates REPLACE/REMOVE.
    code=f'''set {options}
ui_print() {{ printf '%s\\n' "$*"; }}
abort() {{ printf 'ABORT:%s\\n' "$*" >&2; exit 38; }}
{inject}
BEFORE=$-
. "{hook}"
AFTER=$-
[ "$BEFORE" = "$AFTER" ] || exit 77
[ -z "$REPLACE" ] && [ -z "$REMOVE" ] || exit 79
for TARGET in $REPLACE; do printf 'UNEXPECTED REPLACE: %s\\n' "$TARGET"; exit 78; done
for TARGET in $REMOVE; do printf 'UNEXPECTED REMOVE: %s\\n' "$TARGET"; exit 78; done
printf 'KERNELSU_INSTALLER_CONTINUED flags=%s\\n' "$AFTER"
'''
    env={'MODPATH': str(module)} if module is not None else {}
    import os
    return subprocess.run(['/bin/sh','-c',code],env={**os.environ,**env},text=True,capture_output=True,timeout=10)


class KernelSUSourcedInstaller(unittest.TestCase):
    def test_logged_error_is_reproducible_with_old_shell_option_leak(self):
        # Synthetic old hook reproduces missing REPLACE after sourcing.
        with tempfile.TemporaryDirectory() as d:
            script=Path(d)/'unsafe.sh'
            script.write_text('set -eu\nui_print "- Skybind: fixed runtime/module layout verified"\n')
            result=subprocess.run(['/bin/sh','-c',f'ui_print() {{ echo "$*"; }}; . "{script}"; for x in $REPLACE; do :; done'],capture_output=True,text=True,timeout=10)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('REPLACE',result.stderr)

    def test_sourced_installer_continues_even_when_vars_unset(self):
        with tempfile.TemporaryDirectory() as d:
            mod=make_module(Path(d))
            result=shell(mod, options='+eu', inject='unset REPLACE REMOVE')
            self.assertEqual(result.returncode,0,result.stderr+result.stdout)
            self.assertIn('KERNELSU_INSTALLER_CONTINUED',result.stdout)
            for f in FILES[1:]:
                self.assertEqual((mod/f).stat().st_mode&0o777,0o755,f)

    def test_do_not_change_caller_errexit_nounset_settings(self):
        with tempfile.TemporaryDirectory() as d:
            mod=make_module(Path(d))
            for flags in ('-u', '-e', '-eu', '+eu'):
                with self.subTest(flags=flags):
                    result=shell(mod,options=flags,inject='unset REPLACE REMOVE')
                    self.assertEqual(result.returncode,0,result.stderr+result.stdout)

    def test_missing_or_linked_inputs_call_installer_abort(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); mod=make_module(root)
            result=shell(options='+eu')
            self.assertEqual(result.returncode,38,result.stderr)
            (mod/'system/bin/rclone').unlink()
            result=shell(mod,options='+eu')
            self.assertEqual(result.returncode,38,result.stderr)
            self.assertIn('missing or linked executable',result.stderr)
            (mod/'system/bin/rclone').symlink_to('skybind')
            result=shell(mod,options='+eu')
            self.assertEqual(result.returncode,38,result.stderr)
            self.assertIn('missing or linked executable',result.stderr)

    def test_symlink_module_identity_and_hook_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            mod=make_module(Path(d))
            (mod/'module.prop').unlink()
            (mod/'module.prop').symlink_to('action.sh')
            self.assertEqual(shell(mod).returncode,38)
            (mod/'module.prop').unlink()
            (mod/'module.prop').write_text('id=skybind\n')
            (mod/'uninstall.sh').unlink()
            (mod/'uninstall.sh').symlink_to('action.sh')
            self.assertEqual(shell(mod).returncode,38)

    def test_chmod_failure_fatal_even_without_caller_errexit(self):
        with tempfile.TemporaryDirectory() as d:
            mod=make_module(Path(d))
            result=shell(mod,options='+eu',inject='chmod() { return 1; }')
            self.assertEqual(result.returncode,38,result.stderr)
            self.assertIn('cannot set executable permissions',result.stderr)

    def test_ci_and_devtool_include_regression_without_promotion(self):
        content=HOOK.read_text()
        self.assertNotIn('set -eu', '\n'.join(s for s in content.splitlines() if not s.lstrip().startswith('#')))
        self.assertIn("REPLACE=''",content)
        self.assertIn("REMOVE=''",content)
        self.assertNotIn('rm -rf', '\n'.join(s for s in content.splitlines() if not s.lstrip().startswith('#')))
        ci=(ROOT/'.github/workflows/skybind-candidate-integration.yml').read_text()
        self.assertIn("test_q05p3_kernelsu_install.py",ci)
        self.assertIn('workflow_dispatch:',ci)
        self.assertNotIn('adb install',ci)
        cfg=(ROOT/'.devtool.toml').read_text()
        self.assertIn('[targets.skybind.jobs.q05p3-kernelsu-install-contract]',cfg)
        policy=json.loads((ROOT/'scripts/dev/runtime/source.selection.json').read_text())
        self.assertEqual(policy['final_seal'],'NOT_ISSUED')
        self.assertEqual(policy['gate_g01'],'BLOCKED')
        self.assertFalse(policy['physical_device_tested']) if 'physical_device_tested' in policy else None


if __name__ == '__main__': unittest.main()
