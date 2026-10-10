#!/system/bin/sh
# Root-manager late boot service; daemon owns its singleton lock and state.
MODDIR=${0%/*}
[ -f "$MODDIR/disable" ] && exit 0
CLI="$MODDIR/system/bin/skybind"
[ -x "$CLI" ] && [ ! -L "$CLI" ] || exit 1
# Never launch an executable selected from PATH or download a replacement.
"$CLI" daemon </dev/null >/dev/null 2>&1 &
exit 0
