#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
python3 -m unittest discover -s tests/qualification -p 'test_q05p3_kernelsu_install.py' -v
python3 -m unittest discover -s tests/platform -p 'test_hooks.py' -v
printf '%s\n' 'SB-Q05P3 SOURCE_ONLY_PASS: KernelSU sourced installer behavior; physical install NOT RETESTED; G01-G08 BLOCKED; FINAL SEAL NOT_ISSUED'
