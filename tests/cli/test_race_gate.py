#!/usr/bin/env python3
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
SCRIPT=ROOT / 'scripts/devtool/check_go_race.sh'

class TargetedRaceValidation(unittest.TestCase):
    def run_helper(self, goos, arch, cgo, test_rc=0):
        with tempfile.TemporaryDirectory() as td:
            p=pathlib.Path(td)
            fake=p/'go'
            fake.write_text('''#!/bin/sh
case "$1:$2" in
  env:GOOS) printf '%s\n' "$FAKE_GOOS" ;;
  env:GOARCH) printf '%s\n' "$FAKE_GOARCH" ;;
  env:CGO_ENABLED) printf '%s\n' "$FAKE_CGO" ;;
  test:-race) printf 'race-invoked\n' >> "$FAKE_RECORD"; exit "${FAKE_TEST_RC:-0}" ;;
  *) printf 'unexpected go invocation %s %s\n' "$1" "$2" >&2; exit 98 ;;
esac
''')
            fake.chmod(0o700)
            rec=p/'calls'
            env=os.environ.copy()
            env.update(PATH=str(p)+os.pathsep+env.get('PATH',''),FAKE_GOOS=goos,FAKE_GOARCH=arch,FAKE_CGO=cgo,FAKE_TEST_RC=str(test_rc),FAKE_RECORD=str(rec))
            result=subprocess.run(['bash',str(SCRIPT),'./internal/control'],cwd=ROOT,env=env,capture_output=True,text=True)
            return result, rec.read_text() if rec.exists() else ''

    def test_android_arm64_skips_unsupported_race_only(self):
        result,calls=self.run_helper('android','arm64','1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('RACE_NOT_RUN_UNSUPPORTED_HOST',result.stdout)
        self.assertEqual(calls,'')

    def test_disabled_cgo_is_not_reported_as_race_pass(self):
        result,calls=self.run_helper('linux','amd64','0')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('RACE_NOT_RUN_UNSUPPORTED_HOST',result.stdout)
        self.assertEqual(calls,'')

    def test_supported_linux_race_is_executed(self):
        result,calls=self.run_helper('linux','amd64','1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('RACE_EXECUTING',result.stdout)
        self.assertEqual(calls,'race-invoked\n')

    def test_supported_race_failure_blocks_validation(self):
        result,calls=self.run_helper('linux','amd64','1',17)
        self.assertEqual(result.returncode,17,result.stderr)
        self.assertEqual(calls,'race-invoked\n')

    def test_android_arm64_skips_even_with_disabled_cgo(self):
        result,calls=self.run_helper('android','arm64','0')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(calls,'')

if __name__=='__main__':unittest.main()
