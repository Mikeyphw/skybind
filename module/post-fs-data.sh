#!/system/bin/sh
# Root-manager early boot hook: no mounts, no background network operations.
MODDIR=${0%/*}
[ -d "$MODDIR" ] && [ ! -e "$MODDIR/disable" ] || exit 0
exit 0
