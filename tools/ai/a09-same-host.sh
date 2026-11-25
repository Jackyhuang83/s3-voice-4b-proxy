#!/usr/bin/env bash
# Single-host A09-Lite: reuse voice.cncloudx.com and existing Cloudflare Tunnel.
# Commands: sudo bash tools/ai/a09-same-host.sh apply|status|rollback
set -Eeuo pipefail
set +x
umask 077
exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/a09_same_host.py" "${1:-status}"
