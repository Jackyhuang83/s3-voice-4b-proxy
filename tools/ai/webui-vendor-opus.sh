#!/usr/bin/env bash
# CI/staging ONLY. Never source this script in an interactive SSH shell.
# Install pinned MIT/BSD codec into a checked-out COPY, not a production path.
set -Eeuo pipefail
umask 077
cd "$(dirname "$0")/../.."
root="$PWD"
dest="$root/webui/vendor/libopus"
test ! -e "$dest" || { printf '%s\n' "WEBUI_OPUS_BLOCKED: target already exists, refusing overwrite"; exit 1; }
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
url="https://registry.npmjs.org/libopus-wasm/-/libopus-wasm-0.4.1.tgz"
expected="f645938adcd3381dcae9827ef71248218eaeb8308b6339bd568d1c43a64c5ef8"
curl --fail --location --silent --show-error --retry 2 --max-time 45 "$url" -o "$tmp/codec.tgz"
actual="$(sha256sum "$tmp/codec.tgz" | awk '{print $1}')"
test "$actual" = "$expected" || { printf '%s\n' "WEBUI_OPUS_BLOCKED: official package checksum mismatch"; exit 1; }
tar -xzf "$tmp/codec.tgz" -C "$tmp"
test -f "$tmp/package/dist/index.js"
test -f "$tmp/package/dist/generated/libopus.generated.mjs"
test -f "$tmp/package/LICENSE"
test -f "$tmp/package/THIRD_PARTY_NOTICES.md"
mkdir -p "$dest"
cp -R "$tmp/package/dist" "$dest/"
cp "$tmp/package/LICENSE" "$tmp/package/THIRD_PARTY_NOTICES.md" "$dest/"
chmod -R a+rX "$dest"
printf '%s\n' "WEBUI_OPUS_VENDOR_PASS: libopus-wasm 0.4.1, verified registry SHA256, MIT and BSD notices retained"
