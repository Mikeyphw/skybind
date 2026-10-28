#!/bin/sh
# Source-qualification host policy: fail closed except for the observed native
# Android/ARM64 Go race-detector limitation. This is not a device acceptance seal.
set -eu

# Never let an ambient GOOS/GOARCH cross-target masquerade as a native test.
target_os="$(go env GOOS)"
target_arch="$(go env GOARCH)"
host_os="$(go env GOHOSTOS)"
host_arch="$(go env GOHOSTARCH)"
if [ -z "$target_os" ] || [ -z "$target_arch" ] || [ -z "$host_os" ] || [ -z "$host_arch" ]; then
    echo BLOCKED_API04_H1_MISSING_GO_HOST_IDENTITY >&2
    exit 2
fi
if [ "$target_os/$target_arch" != "$host_os/$host_arch" ]; then
    echo "BLOCKED_API04_H1_NON_NATIVE_TEST_TARGET:$target_os/$target_arch:host=$host_os/$host_arch" >&2
    exit 2
fi

# The exact relevant Go packages stay mandatory on every supported native host.
# Android/ARM64 runs repeated uncached tests; this is *not* a substitute for
# race-detector evidence, which remains OPEN until run on a supported host.
case "$host_os/$host_arch" in
    android/arm64)
        echo API04_H1_RACE_NOT_RUN_UNSUPPORTED_NATIVE_ANDROID_ARM64
        go test -p 2 -count=3 \
            ./internal/mounts/lifecycle \
            ./internal/daemon \
            ./internal/control \
            ./internal/featureapi \
            ./internal/featuregateway
        echo API04_H1_NATIVE_ANDROID_ARM64_REPEATED_TESTS_PASS_RACE_GATE_DEFERRED
        ;;
    linux/amd64|linux/arm64|darwin/amd64|darwin/arm64|freebsd/amd64|windows/amd64)
        go test -race -count=1 \
            ./internal/mounts/lifecycle \
            ./internal/daemon \
            ./internal/control \
            ./internal/featureapi \
            ./internal/featuregateway
        echo API04_H1_RACE_DETECTOR_PASS_ON_SUPPORTED_HOST
        ;;
    *)
        echo "BLOCKED_API04_H1_UNQUALIFIED_RACE_PLATFORM:$host_os/$host_arch" >&2
        exit 2
        ;;
esac
