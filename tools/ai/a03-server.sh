#!/usr/bin/env bash
# S3-Voice-AI A03: install *only* isolated XiaoZhi v0.9.8 server, no public ingress.
# Usage: sudo bash tools/ai/a03-server.sh preflight|install|status|rollback
set -euo pipefail
umask 077
export LC_ALL=C

ACTION=help
if test "$#" -gt 0; then ACTION="$1"; fi
ROOT=/opt/s3-voice-ai
BACKUP=/var/backups/s3-voice-ai
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
# Official tag server_0.9.8; digest verified from upstream GitHub Package Versions.
IMAGE_PIN=ghcr.io/xinnan-tech/xiaozhi-esp32-server@sha256:cd41415f887410080dc2424b5faef651373c72fba37b3979d28e90ee548181af
PROJECT=s3-voice-ai

die() { printf 'A03_BLOCKED: %s\n' "$*" >&2; exit 1; }
ok() { printf 'A03_OK: %s\n' "$*"; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing dependency: $1"; }
known_containers() {
  docker ps --format '{{.Names}}' | grep -E '^(homesphere($|-)|miniprobe($|-)|media-bridge$|qms-postgres$)' | LC_ALL=C sort || true
}
preflight() {
  for cmd in docker curl python3 openssl awk df ss grep; do need "$cmd"; done
  docker info >/dev/null 2>&1 || die "Docker daemon inaccessible"
  docker compose version >/dev/null 2>&1 || die "Docker Compose unavailable"
  docker_major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
  case "$docker_major" in ''|*[!0-9]*) die "unknown Docker Engine version";; esac
  test "$docker_major" -ge 28 || die "Docker Engine before 28 is not acceptable for localhost-only publishing"
  test -f "$SOURCE/deploy/ai/a03/docker-compose.yml" || die "missing reviewed compose file"
  if test -e "$ROOT"; then
    die "$ROOT already exists; do not overwrite an existing deployment (use status)"
  fi
  listeners="$(ss -H -lnt | awk '{print $4}')"
  for port in 18000 18003 18080; do
    if printf '%s\n' "$listeners" | grep -Eq ":$port$"; then
      die "TCP port $port already listening; no service will be touched"
    fi
  done
  mem_kib="$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)"
  test "$mem_kib" -ge 1300000 || die "insufficient free RAM for conservative shared VPS setup"
  disk_kib="$(df -Pk /opt | awk 'NR==2 {print $4}')"
  test "$disk_kib" -ge 6291456 || die "less than 6 GiB disk free under /opt"
  ok "preflight passed; candidate ports 18000/18003/18080 unoccupied; no inbound ports required"
}

check_local() {
  test -f "$ROOT/.env" || die "image lock absent"
  docker compose -p "$PROJECT" -f "$ROOT/docker-compose.yml" --env-file "$ROOT/.env" ps --status running -q server | grep -q . || die "AI server container not running"
  # GET is a health probe, not the device configuration protocol.
  curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null || die "OTA health GET failed"
  # Device-like POST, with synthetic non-secret IDs: expect no firmware update.
  json="$(curl --noproxy '*' -fsS --max-time 10 -X POST \
    -H 'Content-Type: application/json' \
    -H 'Device-Id: 02:00:00:00:00:01' \
    -H 'Client-Id: 11111111-2222-4333-8444-555555555555' \
    -H 'User-Agent: test-board/2.6.0' \
    --data-binary '{"application":{"version":"2.6.0"},"board":{"type":"a03-synthetic-board"}}' \
    http://127.0.0.1:18003/xiaozhi/ota/)" || die "OTA POST failed"
  python3 -c '
import json,sys
v=json.load(sys.stdin)
assert v.get("firmware",{}).get("url","BAD")=="", "unexpected firmware download"
assert v.get("firmware",{}).get("version")=="2.6.0", "incorrect firmware version"
assert "mqtt" not in v, "unexpected MQTT gateway"
assert v.get("websocket",{}).get("url")=="ws://127.0.0.1:18000/xiaozhi/v1/", "unexpected WS address"
assert v.get("websocket",{}).get("token",""), "auth token not returned"
' <<< "$json" || die "OTA contract failed"
  test ! -e "$ROOT/data/bin/" || test -z "$(find "$ROOT/data/bin" -maxdepth 1 -type f -name '*.bin' -print -quit)" || die "unexpected firmware binaries"
  ok "OTA GET/POST smoke PASS; MQTT absent; firmware.url empty; WebSocket config loopback-only"
  ok "real device + paid API calls NOT tested (A04 / A05 / A07)"
}

install() {
  test "$(id -u)" = 0 || die "run install as root to protect credentials"
  preflight
  previous="$(known_containers)"
  # Use the published v0.9.8 digest directly; fail closed on a missing/changed blob.
  # Never resolve a mutable registry tag at installation time.
  docker pull "$IMAGE_PIN" >/dev/null
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$IMAGE_PIN" |
    grep -Fx "$IMAGE_PIN" | head -n 1 || true)"
  test "$digest" = "$IMAGE_PIN" || die "upstream pinned image digest validation failed"
  test ! -e "$ROOT" || die "$ROOT changed during preflight"
  mkdir -p "$ROOT/data" "$BACKUP"
  chmod 700 "$ROOT" "$ROOT/data" "$BACKUP"
  cp "$SOURCE/deploy/ai/a03/docker-compose.yml" "$ROOT/docker-compose.yml"
  printf 'XIAOZHI_IMAGE=%s\n' "$digest" > "$ROOT/.env"
  chmod 600 "$ROOT/.env"
  secret="$(openssl rand -hex 32)"
  cat > "$ROOT/data/.config.yaml" <<YAML
# A03 staging: loopback-only. Real API keys and public WSS are A04/A05 tasks.
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  websocket: ws://127.0.0.1:18000/xiaozhi/v1/
  vision_explain: http://127.0.0.1:18003/mcp/vision/explain
  mqtt_gateway: null
  auth_key: "$secret"
  auth:
    enabled: true
    allowed_devices: []
selected_module:
  VAD: SileroVAD
  ASR: OpenaiASR
  LLM: DeepSeekLLM
  TTS: EdgeTTS
  Memory: nomem
  Intent: nointent
ASR:
  OpenaiASR:
    api_key: PENDING_A05_NOT_A_REAL_KEY
LLM:
  DeepSeekLLM:
    api_key: PENDING_A05_NOT_A_REAL_KEY
enable_greeting: false
YAML
  chmod 600 "$ROOT/data/.config.yaml"
  # No firmware files. Upstream OTA would advertise matching binaries, so keep this empty.
  mkdir -p "$ROOT/data/bin"
  chmod 700 "$ROOT/data/bin"
  (cd "$ROOT" && docker compose -p "$PROJECT" config -q) || die "Compose static validation failed"
  stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
  # Back up only the new project's files; do not read or modify other projects.
  tar -C "$ROOT" -czf "$BACKUP/a03-initial-$stamp.tgz" .env docker-compose.yml data/.config.yaml
  chmod 600 "$BACKUP/a03-initial-$stamp.tgz"
  (cd "$ROOT" && docker compose -p "$PROJECT" up -d --no-build --no-deps server) || die "AI-only container startup failed; rollback only this project"
  succeeded=0
  for attempt in $(seq 1 60); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then
      succeeded=1
      break
    fi
    sleep 2
  done
  test "$succeeded" = 1 || die "AI server OTA did not become healthy; inspect only its own logs; rollback available"
  check_local
  current="$(known_containers)"
  if test "$previous" != "$current"; then die "existing running-container set changed during AI deployment; investigate"; fi
  ok "installed official server_0.9.8 pinned digest, with 1024 MiB and 1 CPU cap; private backup created"
  ok "no firewall changes, no Cloudflare Tunnel, no original Docker services touched"
}

status() {
  if test ! -f "$ROOT/.env"; then die "A03 not installed"; fi
  check_local
  docker compose -p "$PROJECT" -f "$ROOT/docker-compose.yml" --env-file "$ROOT/.env" ps --format table
}
rollback() {
  test "$(id -u)" = 0 || die "run rollback as root"
  test -f "$ROOT/.env" || die "not installed; will not affect other services"
  docker compose -p "$PROJECT" -f "$ROOT/docker-compose.yml" --env-file "$ROOT/.env" stop server
  ok "stopped only s3-voice-ai server; private data/backup retained, other projects untouched"
}

case "$ACTION" in
  preflight) preflight ;;
  install) install ;;
  status) status ;;
  rollback) rollback ;;
  *) printf 'Usage: bash tools/ai/a03-server.sh preflight|install|status|rollback\n'; exit 2 ;;
esac
