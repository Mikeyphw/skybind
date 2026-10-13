#!/system/bin/sh
# M8 optional *read-only* Android smoke screen. Run as root after installing
# personal ZIP: su -c "sh $PWD/scripts/dev/integration/m8_device_smoke.sh"
# No mount starts/stops, no cache clears, no remote writes, no persistent logs.
set -u
umask 077
SB=${SKYBIND_BIN:-/data/adb/modules/skybind/system/bin/skybind}
PASS=0
FAIL=0
check() {
  name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS %s\n' "$name"
    PASS=$((PASS+1))
  else
    printf 'FAIL %s\n' "$name"
    FAIL=$((FAIL+1))
  fi
}
if [ "$(id -u)" != 0 ]; then
  echo 'Run as root via su -c. No checks were performed.' >&2
  exit 2
fi
check 'installed skybind executable' test -x "$SB"
if [ ! -x "$SB" ]; then
  echo 'Module missing. Stop; do not install or modify anything automatically.' >&2
  exit 2
fi
check 'native CLI version' "$SB" version
check 'verified static runtime' "$SB" runtime-status
check 'authenticated daemon capabilities' "$SB" capabilities
check 'read-only mount registry query' "$SB" mount list
check 'read-only job query' "$SB" jobs list
printf '\nNon-destructive checks: %d passed, %d failed.\n' "$PASS" "$FAIL"
printf '%s\n' 'Manual device tests remain: idle Stop/Restart; busy-upload refusal; Wi-Fi reconnect; airplane-mode verified offline file; draft conflict; backup round trip; reboot; ordinary-app file access.'
printf '%s\n' 'Keep prior KernelSU ZIP for rollback. No changes were made by this script.'
[ "$FAIL" -eq 0 ]
