"""SB-Q05P2: Linux host tests and Android/arm64 compilation are different phases.

This is source-contract validation, NOT a CI run or Android device gate.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT/'.github/workflows/skybind-candidate-integration.yml'

def step(body, name):
    lines = body.splitlines()
    head = f'      - name: {name}'
    start = lines.index(head)
    end = next((i for i in range(start + 1,len(lines)) if lines[i].startswith('      - name: ')),len(lines))
    return '\n'.join(lines[start:end])

def contract(body):
    assert body.count("go-version: '1.27.2'") == 1
    assert 'workflow_dispatch:' in body
    assert 'actions/setup-go@' in body
    assert 'cache: false' in body
    assert 'gh run download 38110749243' in body
    assert 'permissions:\n  contents: read\n  actions: read' in body
    assert body.index('Install selected Go for native Skybind build (no cache)') < body.index('Run pinned native Linux/amd64 Go tests') < body.index('Compile static Go Android/arm64 Skybind native executable')
    host = step(body,'Run pinned native Linux/amd64 Go tests')
    cross = step(body,'Compile static Go Android/arm64 Skybind native executable')
    assert "GOTOOLCHAIN: local" in host and "GOWORK: off" in host
    assert "CGO_ENABLED: '0'" in host
    assert 'GOOS: linux' in host and 'GOARCH: amd64' in host
    assert "go version go1.27.2 linux/amd64" in host
    assert "$(go env GOOS GOARCH CGO_ENABLED)" in host
    assert 'go test -count=1 ./...' in host
    assert 'go build' not in host
    assert "GOTOOLCHAIN: local" in cross and "GOWORK: off" in cross
    assert "CGO_ENABLED: '0'" in cross
    assert 'GOOS: android' in cross and 'GOARCH: arm64' in cross
    assert 'go build -trimpath -buildvcs=false' in cross
    assert "-ldflags='-buildid= -s -w'" in cross
    assert 'go test ' not in cross
    for check in ('GOOS=android','GOARCH=arm64','CGO_ENABLED=0'):
        assert check in cross
    assert "$(go env GOOS GOARCH CGO_ENABLED)" in cross
    assert "skybind-${p}-CANDIDATE-UNQUALIFIED.zip" in body
    assert 'CANDIDATES_UNQUALIFIED' in body
    assert 'release: write' not in body and 'adb install' not in body
    assert 'NOT_ISSUED' in (ROOT/'scripts/dev/integration/q04.inputs.json').read_text()

class CrossCompileCITests(unittest.TestCase):
    def test_host_and_cross_boundaries(self):
        contract(WORKFLOW.read_text())

    def test_cross_target_go_test_is_rejected(self):
        body=WORKFLOW.read_text()
        for wrong in ('          go test ./...\n', '          go test -count=1 ./...\n'):
            mutated=body.replace('          mkdir -p dist/native\n', wrong+'          mkdir -p dist/native\n')
            with self.subTest(wrong=wrong),self.assertRaises(AssertionError):contract(mutated)

    def test_native_target_mismatch_is_rejected(self):
        body=WORKFLOW.read_text()
        for old,new in [('GOOS: linux','GOOS: android'),('GOARCH: amd64','GOARCH: arm64'),("CGO_ENABLED: '0'","CGO_ENABLED: '1'")]:
            mutated=body.replace(old,new,1)
            with self.subTest(old=old),self.assertRaises(AssertionError):contract(mutated)

    def test_go_pin_and_android_build_guards_cannot_drift(self):
        body=WORKFLOW.read_text()
        for old,new in [("go-version: '1.27.2'","go-version: 'stable'"),
                        ('GOARCH: arm64','GOARCH: amd64'),
                        ("-ldflags='-buildid= -s -w'","-ldflags='-s -w'"),
                        ('cache: false','cache: true')]:
            mutated=body.replace(old,new,1)
            with self.subTest(old=old),self.assertRaises(AssertionError):contract(mutated)

    def test_host_go_tests_execute_and_cross_build_is_nonexecuting(self):
        if not shutil_which('go'):
            self.skipTest('Go unavailable; workflow contract checked by other tests')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'go.mod').write_text('module example.org/q05p2\n\ngo 1.23.0\n')
            (root/'main.go').write_text('package main\nfunc main(){}\nfunc answer() int{return 42}\n')
            (root/'main_test.go').write_text('package main\nimport "testing"\nfunc TestAnswer(t *testing.T){if answer()!=42 {t.Fatal("bad")}}\n')
            env=dict(os.environ)
            env.update({'GOTOOLCHAIN':'local','CGO_ENABLED':'0','GOWORK':'off','GOPROXY':'off','GOSUMDB':'off'})
            # Test the *executing* stage on the actual host architecture (Linux CI / Android Termux).
            goenv=subprocess.run(['go','env','GOOS','GOARCH'],env=env,cwd=root,capture_output=True,text=True,check=True).stdout.splitlines()
            host=dict(env,GOOS=goenv[0],GOARCH=goenv[1])
            test=subprocess.run(['go','test','-count=1','./...'],env=host,cwd=root,capture_output=True,text=True,timeout=120)
            self.assertEqual(test.returncode,0,test.stderr)
            target=dict(env,GOOS='android',GOARCH='arm64')
            out=root/'android-sample'
            built=subprocess.run(['go','build','-trimpath','-buildvcs=false',"-ldflags=-buildid= -s -w",'-o',str(out),'.'],env=target,cwd=root,capture_output=True,text=True,timeout=120)
            self.assertEqual(built.returncode,0,built.stderr)
            self.assertTrue(out.is_file())
            metadata=subprocess.run(['go','version','-m',str(out)],env=env,capture_output=True,text=True,check=True).stdout
            self.assertIn('GOOS=android',metadata)
            self.assertIn('GOARCH=arm64',metadata)
            self.assertIn('CGO_ENABLED=0',metadata)

    def test_host_test_failure_is_not_ignored(self):
        if not shutil_which('go'):
            self.skipTest('Go unavailable')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'go.mod').write_text('module example.org/q05p2bad\n\ngo 1.23.0\n')
            (root/'main_test.go').write_text('package sample\nimport "testing"\nfunc TestBad(t *testing.T){t.Fatal("intended fail")}\n')
            env=dict(os.environ,GOTOOLCHAIN='local',CGO_ENABLED='0',GOWORK='off',GOPROXY='off',GOSUMDB='off')
            res=subprocess.run(['go','test','-count=1','./...'],env=env,cwd=root,capture_output=True,text=True,timeout=120)
            self.assertNotEqual(res.returncode,0)
            self.assertIn('intended fail',res.stdout+res.stderr)

def shutil_which(cmd):
    from shutil import which
    return which(cmd)

if __name__=='__main__': unittest.main()
