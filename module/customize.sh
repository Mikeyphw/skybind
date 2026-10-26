#!/system/bin/sh
# Sourced by KernelSU/Magisk/APatch module installers (NOT a child process).
# Never set -e/-u here: shell-option changes would escape into the installer.
# Skybind contributes only its own module paths; it replaces/removes no directories.
REPLACE=''
REMOVE=''

[ -n "${MODPATH:-}" ] || abort 'Skybind: missing module installer destination'
[ -d "$MODPATH" ] && [ ! -L "$MODPATH" ] || abort 'Skybind: invalid module directory'
# No downloads, mutable runtime selection, or migration during install.
[ -f "$MODPATH/module.prop" ] && [ ! -L "$MODPATH/module.prop" ] || abort 'Skybind: missing or linked module identity'
for f in "$MODPATH/system/bin/skybind" "$MODPATH/system/bin/rclone" "$MODPATH/system/bin/skybind-rclone" "$MODPATH/system/bin/skybind-rclone-engine" "$MODPATH/system/vendor/bin/fusermount3"; do
  [ -f "$f" ] && [ ! -L "$f" ] || abort "Skybind: missing or linked executable: $f"
  chmod 0755 "$f" || abort "Skybind: cannot set executable permissions: $f"
done
for f in action.sh service.sh post-fs-data.sh uninstall.sh; do
  [ -f "$MODPATH/$f" ] && [ ! -L "$MODPATH/$f" ] || abort "Skybind: missing or linked module hook: $f"
  chmod 0755 "$MODPATH/$f" || abort "Skybind: cannot set hook permissions: $f"
done
ui_print '- Skybind: fixed runtime/module layout verified'
