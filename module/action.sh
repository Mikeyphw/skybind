#!/system/bin/sh
MODDIR=${0%/*}
CLI="$MODDIR/system/bin/skybind"
[ -x "$CLI" ] && [ ! -L "$CLI" ] || exit 1
# Read-only action: display real status, never blind-start or blind-unmount.
"$CLI" platform-status
