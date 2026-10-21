#!/usr/bin/env python3
"""Operate the real R1 read-only gateway on a rooted Termux Android device.

'identity' OBSERVES device state, never approves it. 'policy' accepts independently
approved values from the operator. 'gateway' runs a source-bound hosted binary,
explicitly, interactively, and only for as long as the operator terminal lives.
No consumer tokens are copied into Termux, disk, intents, or logs.
"""
from __future__ import annotations
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import sys

GH_REPO = 'Mikeyphw/skybind'
RUN_NAME = 'Skybind R1 consumer gateway and module diagnostics (unqualified)'
ARTIFACT = 'skybind-r1-consumer-diagnostics-unqualified'
GATEWAY = 'skybind-r1-gateway-android-arm64'
MODULE_CHECK = 'skybind-r1-module-check-android-arm64'
COMMIT = re.compile(r'[0-9a-f]{40}\Z')
DIGEST = re.compile(r'[0-9a-f]{64}\Z')
CONTEXT = re.compile(r'u:r:[A-Za-z0-9_]+:s[0-9]+(?::c[0-9]+(?:,c[0-9]+)*)?\Z')
REMOTE = re.compile(r'[A-Za-z][A-Za-z0-9_-]{0,62}\Z')
APPPATH = re.compile(r'/data/app/[A-Za-z0-9_./@+~=-]+/base\.apk\Z')
POLICY_PATH='/data/adb/skybind/consumer-policy-v1.json'
OPS=('system.capabilities','rclone.version','rclone.listremotes','rclone.lsjson','rclone.size')

def call(argv, timeout=90, *, input=None, capture=True):
    return subprocess.run(argv, input=input, capture_output=capture, text=True,
                          timeout=timeout, check=False)

def root(command, timeout=30):
    r=call(['su','-c',command],timeout=timeout)
    if r.returncode:
        raise RuntimeError('Root command failed (no change presumed); check authorization')
    return r.stdout.strip()

def identity(_args):
    for pkg in ('io.github.mikeyphw.skybind','com.mikeyphw.bkx.android'):
        print(f'[{pkg}]')
        try:
            print(root('pm list packages -U ' + shlex.quote(pkg)))
            proc=root('pidof '+shlex.quote(pkg))
            if proc:
                pid=int(proc.split()[0]);label=root(f'cat /proc/{pid}/attr/current').rstrip('\x00\r\n')
                print(f'PID {pid} · process context: {label}')
            if pkg=='io.github.mikeyphw.skybind':
                paths=root('pm path '+shlex.quote(pkg)).splitlines()
                for line in paths:
                    if line.startswith('package:') and line.endswith('/base.apk'):
                        print('Installed APK:',line.split(':',1)[1])
                        print('Installed bytes:',root('sha256sum '+shlex.quote(line.split(':',1)[1])).split()[0])
        except Exception as e:
            print('Unobserved:',str(e)[:100])
    print('[chrootctl]')
    for name,path in [('package manifest', '/data/adb/modules/chrootctl/config/chrootctl/module-package-manifest.json'),
                      ('installed executable','/data/adb/modules/chrootctl/runtime/arm64-v8a/chrootctl')]:
        try:
            print(name,root('sha256sum '+shlex.quote(path)).split()[0])
        except Exception:
            print(name,'NOT OBSERVED')
    print('OBSERVATIONS ONLY: review independent build/signing provenance before approving any value.')
    return 0

def validate_pin(a):
    if not DIGEST.fullmatch(a.bkx_cert) or not DIGEST.fullmatch(a.module_seal):
        raise ValueError('Approved signer/module seal must be lowercase 64-character SHA256')
    if not CONTEXT.fullmatch(a.bkx_context) or not CONTEXT.fullmatch(a.module_context):
        raise ValueError('Malformed SELinux pin')
    if a.bkx_uid < 10000 or a.bkx_uid > 2**31-1:
        raise ValueError('Invalid BKX UID')
    if not REMOTE.fullmatch(a.remote):
        raise ValueError('Remote must be an approved simple name')
    if len(a.prefix)>4096 or a.prefix.startswith('/') or any(c in a.prefix for c in '\\:%?#\x00\r\n') or any(p in ('','.','..') for p in a.prefix.split('/')) and a.prefix!='':
        raise ValueError('Invalid relative prefix')

def policy(a):
    validate_pin(a)
    body={'schema':'skybind-r1-operator-policy-v1','abi_major':1,'explicitly_enabled':True,
          'bkx':{'package':'com.mikeyphw.bkx.android','uid':a.bkx_uid,'cert_sha256':a.bkx_cert,'selinux_context':a.bkx_context},
          'chrootctl':{'manifest_sha256':a.module_seal,'selinux_context':a.module_context},
          'rules':[{'consumer':consumer,'remote':a.remote,'prefix':a.prefix,'operations':list(OPS)} for consumer in ('bkx','chrootctl')]}
    raw=(json.dumps(body,separators=(',',':'),sort_keys=True)+'\n').encode()
    if len(raw)>32768:
        raise ValueError('Policy too large')
    encoded=base64.b64encode(raw).decode('ascii')
    # Base64 and trusted fixed pathname are the ONLY interpolated shell data.
    # Refuse a symlink parent; write a new private temporary policy then atomically rename.
    script=("set -eu; umask 077; d=/data/adb/skybind; "
           "if [ -L \"$d\" ]; then exit 2; fi; "
           "mkdir -p \"$d\"; chown 0:0 \"$d\"; chmod 0700 \"$d\"; "
           "p=\"$d/consumer-policy-v1.json\"; "
           "if [ -L \"$p\" ]; then exit 2; fi; "
           "t=\"$d/.consumer-policy-v1.new\"; "
           "if [ -e \"$t\" ] || [ -L \"$t\" ]; then exit 2; fi; "
           "printf %s "+shlex.quote(encoded)+" | base64 -d > \"$t\"; "
           "chown 0:0 \"$t\"; chmod 0600 \"$t\"; "
           "mv \"$t\" \"$p\"; chmod 0600 \"$p\"")
    root(script)
    print('Root-owned R1 policy installed:',POLICY_PATH)
    print('No grants or services were started. Inspect the policy and launch the gateway explicitly.')
    return 0

def current_source(repo):
    r=call(['git','-C',str(repo),'rev-parse','HEAD'])
    if r.returncode or not COMMIT.fullmatch(r.stdout.strip()):
        raise RuntimeError('Git source unavailable')
    return r.stdout.strip()

def gateway(a):
    sha=current_source(a.skybind)
    if sha != a.expected_sha or not COMMIT.fullmatch(sha):
        raise RuntimeError('Local source does not match independently selected commit')
    if not CONTEXT.fullmatch(a.authority_context) or not APPPATH.fullmatch(a.authority_apk) or not DIGEST.fullmatch(a.authority_apk_sha256) or a.authority_uid <10000:
        raise ValueError('Authority UID/label/APK path/byte seal approval invalid')
    r=call(['gh','api',f'repos/{GH_REPO}/actions/runs/{a.run_id}'])
    if r.returncode:
        raise RuntimeError('GitHub hosted diagnostic run unavailable')
    meta=json.loads(r.stdout)
    if meta.get('head_sha')!=sha or meta.get('conclusion')!='success' or meta.get('name')!=RUN_NAME or meta.get('event')!='workflow_dispatch':
        raise RuntimeError('Hosted diagnostic source/workflow mismatch')
    with tempfile.TemporaryDirectory(prefix='skybind-r1-live-') as temp:
        dest=Path(temp)
        r=call(['gh','run','download',str(a.run_id),'-R',GH_REPO,'--name',ARTIFACT,'--dir',temp],timeout=180)
        if r.returncode:
            raise RuntimeError('Source-bound diagnostics artifact download failed')
        source=dest/'source.json';sums=dest/'SHA256SUMS.txt'
        if source.is_symlink() or not source.is_file() or source.stat().st_size>4096 or sums.is_symlink() or not sums.is_file() or sums.stat().st_size>2048:
            raise RuntimeError('Unsafe artifact manifest')
        manifest=json.loads(source.read_text())
        if manifest!={'schema':'skybind-r1-consumer-diagnostic-artifact-v1','source_sha':sha,'external_provider_qualified':False,'release_qualified':False}:
            raise RuntimeError('Artifact source claim mismatch')
        entries={}
        for line in sums.read_text().splitlines():
            bits=line.split()
            if len(bits)!=2 or bits[1] not in (GATEWAY,MODULE_CHECK) or bits[1] in entries or not DIGEST.fullmatch(bits[0]):
                raise RuntimeError('Artifact SHA manifest unsafe')
            entries[bits[1]]=bits[0]
        if set(entries)!={GATEWAY,MODULE_CHECK}:
            raise RuntimeError('Artifact SHA manifest incomplete')
        for name,digest in entries.items():
            p=dest/name
            if p.is_symlink() or not p.is_file() or p.stat().st_size<4096 or p.stat().st_size>80<<20 or hashlib.sha256(p.read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Artifact bytes mismatch')
        exe=dest/GATEWAY
        exe.chmod(0o700)
        arguments=[str(exe),'--operator-approve','--policy',POLICY_PATH,
                   '--authority-uid',str(a.authority_uid), '--authority-context',a.authority_context,
                   '--authority-apk',a.authority_apk,'--authority-apk-sha256',a.authority_apk_sha256]
        print('Entering the live root operator gateway. Start the Skybind foreground bridge from its app.')
        print('Then use: approve PID bkx|chrootctl REMOTE PREFIX|- rclone.lsjson 60')
        print('Use receipts/revoke/quit in this terminal. This is a real interactive broker, not a preflight.',flush=True)
        # Preserve the interactive terminal; no shell redirection or background exec.
        run=subprocess.run(['su','-c','exec '+' '.join(shlex.quote(v) for v in arguments)],check=False)
        return run.returncode

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('identity',help='OBSERVE installed identities only')
    s=sub.add_parser('policy',help='Explicitly approve and install a root-owned policy')
    s.add_argument('--bkx-uid',type=int,required=True)
    s.add_argument('--bkx-cert',required=True)
    s.add_argument('--bkx-context',required=True)
    s.add_argument('--module-seal',required=True)
    s.add_argument('--module-context',required=True)
    s.add_argument('--remote',required=True)
    s.add_argument('--prefix',default='')
    s=sub.add_parser('gateway',help='Verify GitHub artifact then start an interactive root gateway')
    s.add_argument('--skybind',type=Path,default=Path.home()/'Code/skybind')
    s.add_argument('--run-id',type=int,required=True)
    s.add_argument('--expected-sha',required=True)
    s.add_argument('--authority-uid',type=int,required=True)
    s.add_argument('--authority-context',required=True)
    s.add_argument('--authority-apk',required=True)
    s.add_argument('--authority-apk-sha256',required=True)
    a=p.parse_args()
    try:
        return {'identity':identity,'policy':policy,'gateway':gateway}[a.command](a)
    except (ValueError,RuntimeError,subprocess.TimeoutExpired,OSError,json.JSONDecodeError) as e:
        print('R1_BLOCKED:',str(e)[:240],file=sys.stderr)
        return 2
if __name__=='__main__':
    raise SystemExit(main())
