#!/system/bin/sh
# Skybind's public rclone command. The pinned native provider is separate from
# this launcher; internal Skybind services execute the native provider directly.
# RCLONE_CONFIG is the DEFAULT. An explicit upstream --config flag still wins.
case "$0" in
  /*) RCLONE_DIR=${0%/*} ;;
  *) echo 'skybind rclone: absolute launcher path required' >&2; exit 127 ;;
esac
RCLONE_ENGINE="$RCLONE_DIR/skybind-rclone-engine"
if [ ! -f "$RCLONE_ENGINE" ] || [ -L "$RCLONE_ENGINE" ] || [ ! -x "$RCLONE_ENGINE" ]; then
  echo 'skybind rclone: native provider unavailable' >&2
  exit 127
fi
RCLONE_CONFIG=/data/adb/skybind/config/rclone.conf
export RCLONE_CONFIG
exec "$RCLONE_ENGINE" "$@"
