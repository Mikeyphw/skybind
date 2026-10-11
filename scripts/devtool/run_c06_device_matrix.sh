#!/usr/bin/env bash
# Explicit opted-in Devtool physical-device workflow. Not part of source apply.
set -euo pipefail
cd "$(dirname "$0")/../.."
: "${SKYBIND_DEVICE_TEST_OPT_IN:=}"
[ "$SKYBIND_DEVICE_TEST_OPT_IN" = "1" ] || { echo 'PHYSICAL_DEVICE_NOT_ATTESTED: explicit test opt-in absent' >&2;exit 3; }
: "${SKYBIND_DEVICE_SERIAL:?physical Android serial required}"
: "${SKYBIND_TEST_MOUNT:?configured test mount destination required}"
: "${SKYBIND_TEST_PROVIDER:?pinned NewFuture or bclone source provider required}"
case "$SKYBIND_TEST_PROVIDER" in newfuture|bclone) ;; *) echo 'unrecognized runtime provider' >&2; exit 3;;esac
command -v adb >/dev/null || { echo 'ADB_NOT_AVAILABLE' >&2;exit 3; }
mkdir -p build/evidence/android
chmod 0700 build/evidence/android
umask 077
python3 scripts/dev/device/skybind_device.py \
  --serial "$SKYBIND_DEVICE_SERIAL" \
  --path "$SKYBIND_TEST_MOUNT" \
  --out "build/evidence/android/raw-${SKYBIND_TEST_PROVIDER}-$(date -u +%Y%m%dT%H%M%S)-$$.json"
echo 'RAW_DEVICE_RECEIPT_ONLY; not a final gate, requires independent Devtool run-store linkage'
