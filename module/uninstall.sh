#!/system/bin/sh
# Normal removal always RETAINS /data/adb/skybind (config, cache, logs).
MODDIR=${0%/*}
CLI="$MODDIR/system/bin/skybind"
if [ -x "$CLI" ] && [ ! -L "$CLI" ]; then
 "$CLI" uninstall-stop || {
  echo 'Skybind: safe stop could not be proven; persistent state retained' >&2
  exit 1
 }
fi
# Intentionally no rm -rf, pkill, killall, umount -l, or shared namespace teardown.
echo 'Skybind persistent user data retained under /data/adb/skybind'
exit 0
