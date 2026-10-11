#!/system/bin/sh
# Invoked by supported module-manager installer with MODPATH set.
set -eu
[ -n "${MODPATH:-}" ] || { echo 'Skybind: missing module installer destination' >&2; exit 1; }
[ -d "$MODPATH" ] || { echo 'Skybind: missing module directory' >&2; exit 1; }
# No downloads, mutable runtime selection, or migration during install.
[ -f "$MODPATH/module.prop" ] || { echo 'Skybind: missing module identity' >&2; exit 1; }
for f in "$MODPATH/system/bin/skybind" "$MODPATH/system/bin/rclone" "$MODPATH/system/vendor/bin/fusermount3"; do
 [ -f "$f" ] && [ ! -L "$f" ] || { echo "Skybind: missing or linked executable: $f" >&2; exit 1; }
 chmod 0755 "$f"
done
for f in action.sh service.sh post-fs-data.sh uninstall.sh; do
 [ -f "$MODPATH/$f" ] && [ ! -L "$MODPATH/$f" ] || exit 1
 chmod 0755 "$MODPATH/$f"
done
ui_print '- Skybind: fixed runtime/module layout verified'
