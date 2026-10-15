#!/usr/bin/env python3
"""Install *only* the freshly verified Skybind candidate via KernelSU.

This is an opt-in personal device mutation, NEVER a release qualification.
We preserve ksud stdout and stderr (including stderr progress) as live streams.
"""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path


class ModuleInstallError(RuntimeError):
    pass


def install_verified_zip(archive: Path, *, provider: str, release_verify) -> None:
    archive = Path(archive).absolute()
    if provider not in ('bclone', 'newfuture'):
        raise ModuleInstallError('invalid provider for installation')
    if archive.is_symlink() or not archive.is_file() or archive.suffix != '.zip' or any(p.is_symlink() for p in archive.parents):
        raise ModuleInstallError('installation requires an existing regular ZIP without symlinked parents')
    details = release_verify(archive)
    if details.get('qualification') != 'CANDIDATE_ONLY_NOT_SEALED' or details.get('runtime_provider') != provider:
        raise ModuleInstallError('archive provider/qualification mismatch; refusing installation')
    command = 'ksud module install ' + shlex.quote(str(archive))
    print('[SKYBIND INSTALL] Running KernelSU installer; both stdout and stderr remain visible', flush=True)
    try:
        # -c expects one shell command argument; no shell or redirection on the host.
        # The path is exclusively taken from the verified build, never user input.
        completed = subprocess.run(['su', '-c', command], check=False)
    except FileNotFoundError as exc:
        raise ModuleInstallError('su is unavailable; module was built but not installed') from exc
    if completed.returncode != 0:
        raise ModuleInstallError(f'ksud installation failed (exit {completed.returncode}); verified ZIP retained: {archive}')
    print('[SKYBIND INSTALL] ksud exited successfully; reboot when appropriate. This is NOT a device-qualification seal.', flush=True)
