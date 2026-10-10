#!/usr/bin/env bash
# Targeted race checking. Go does not provide -race on Android/arm64.
# Preserve source-only qualification truth: NOT_RUN is not a PASS.
set -euo pipefail
host_os="$(go env GOOS)"
host_arch="$(go env GOARCH)"
cgo_enabled="$(go env CGO_ENABLED)"
case "${host_os}/${host_arch}/${cgo_enabled}" in
  linux/amd64/1|linux/arm64/1|darwin/amd64/1|darwin/arm64/1|freebsd/amd64/1)
    echo "SKYBIND_RACE_EXECUTING: ${host_os}/${host_arch} CGO=${cgo_enabled}"
    exec go test -race -count=1 "$@"
    ;;
  *)
    echo "SKYBIND_RACE_NOT_RUN_UNSUPPORTED_HOST: ${host_os}/${host_arch} CGO=${cgo_enabled} (race evidence outstanding; non-race tests remain mandatory)"
    ;;
esac
