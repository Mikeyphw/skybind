#!/usr/bin/env bash
# SB-Q14R2: Run manually on the owner's trusted Termux device.
set -euo pipefail
repo="${1:-Mikeyphw/skybind}"
case "$repo" in */*) ;; *) echo 'Expected OWNER/REPO' >&2; exit 2;; esac
command -v openssl >/dev/null || { echo 'openssl is required' >&2; exit 2; }
command -v gh >/dev/null || { echo 'gh CLI is required' >&2; exit 2; }
trust="$HOME/.config/skybind/trust"
priv="$trust/q14-ci-private.pem"
pub="$trust/q14-ci-public.pem"
umask 077
mkdir -p "$trust"
chmod 700 "$trust"
if [[ -e "$priv" || -e "$pub" ]]; then
  echo "Refusing to replace existing key; inspect $trust and rotate deliberately." >&2
  exit 2
fi
openssl genpkey -algorithm ED25519 -out "$priv"
openssl pkey -in "$priv" -pubout -out "$pub"
chmod 600 "$priv"
chmod 644 "$pub"
# Secret is never passed as an argument or printed to logs.
base64 < "$priv" | tr -d '\n' | gh secret set SKYBIND_Q14_ED25519_KEY_B64 -R "$repo"
# Public key fingerprint is an integrity pin for CI comparison, NOT independent custody.
fingerprint="$(sha256sum "$pub" | cut -d' ' -f1)"
gh variable set SKYBIND_Q14_SIGNER_PUBLIC_SHA256 -R "$repo" --body "$fingerprint"
printf 'Q14R2 private key configured for %s\nPublic trust anchor: %s\nPublic key SHA256: %s\nKeep the private PEM out of Git and back it up securely.\n' "$repo" "$pub" "$fingerprint"
