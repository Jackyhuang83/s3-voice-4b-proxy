#!/usr/bin/env bash
# S3-Voice-AI A04 — isolate a strict Caddy OTA/WS gate and optional Cloudflare connector.
# sudo bash tools/ai/a04-edge.sh stage|local|connect|public|status|rollback
set -Eeuo pipefail
umask 077
export LC_ALL=C
ACTION=help
if test "$#" -gt 0; then ACTION="$1"; fi
A03=/opt/s3-voice-ai
EDGE=/opt/s3-voice-ai-edge
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
AI_COMPOSE="$A03/docker-compose.yml"
EDGE_COMPOSE="$EDGE/docker-compose.yml"
CADDY_TAG=caddy:2.11.7-alpine
TUNNEL_TAG=cloudflare/cloudflared:2026.11.0
NAME=s3-voice-ai-edge

die() { printf 'A04_BLOCKED: %s\n' "$*" >&2; exit 1; }
ok() { printf 'A04_OK: %s\n' "$*"; }
require_root() { test "$(id -u)" = 0 || die "use root Shell"; }
known() { docker ps --format '{{.Names}}' | grep -E '^(homesphere($|-)|miniprobe($|-)|media-bridge$|qms-postgres$)' | sort || true; }
ai_restart() { docker compose -p s3-voice-ai -f "$AI_COMPOSE" --env-file "$A03/.env" restart server >/dev/null; }
edge_compose() { docker compose -p "$NAME" -f "$EDGE_COMPOSE" --env-file "$EDGE/.env" "$@"; }
check_safe() {
  require_root
  for cmd in docker curl python3 openssl awk ss grep sed; do command -v "$cmd" >/dev/null || die "missing $cmd"; done
  test -f "$A03/data/.config.yaml" || die "A03 server config missing"
  test -f "$A03/.env" || die "A03 image lock missing"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-server || die "A03 server not running"
  docker network inspect s3-voice-ai_default >/dev/null 2>&1 || die "A03 backend network missing"
  curl --noproxy '*' -fsS --max-time 5 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null || die "A03 OTA health failed"
  test ! -d "$A03/data/bin" || test -z "$(find "$A03/data/bin" -maxdepth 1 -type f -name '*.bin' -print -quit)" || die "unexpected OTA firmware binaries"
  grep -q 'PENDING_A05_NOT_A_REAL_KEY' "$A03/data/.config.yaml" || die "paid key may be configured; refuse opening A04 before provider budget/security review"
  grep -q '^    enabled: true$' "$A03/data/.config.yaml" || die "upstream WS auth must be enabled"
}
image_digest() {
  local tag="$1" match="$2" digest=""
  docker pull "$tag" >/dev/null
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$tag" | grep -E "$match" | head -n 1 || true)"
  test -n "$digest" || die "cannot resolve immutable registry digest for official image"
  printf '%s\n' "$digest"
}
restore_stage() {
  # Only when partially installing A04; never tear down other Docker projects.
  trap - ERR
  if test -f "$EDGE/.env"; then
    edge_compose --profile tunnel stop tunnel gateway >/dev/null 2>&1 || true
  fi
  if test -f "$EDGE/pre-a04.config.yaml"; then
    cp "$EDGE/pre-a04.config.yaml" "$A03/data/.config.yaml"
    chmod 600 "$A03/data/.config.yaml"
    ai_restart || true
  fi
  printf 'A04_BLOCKED: staged changes rolled back; existing services preserved\n' >&2
}
stage() {
  check_safe
  test ! -e "$EDGE" || die "A04 already staged; use local/status/rollback (no overwrite)"
  listeners="$(ss -H -lnt | awk '{print $4}')"
  if printf '%s\n' "$listeners" | grep -Eq ':18080$'; then die "reserved TCP 18080 is already occupied"; fi
  grep -Fqx '  websocket: ws://127.0.0.1:18000/xiaozhi/v1/' "$A03/data/.config.yaml" || die "A03 URL baseline changed; no automatic rewrite"
  old_containers="$(known)"
  # Pull only the pinned official Caddy release, then resolve and lock its digest.
  caddy_digest="$(image_digest "$CADDY_TAG" '(^|/)caddy@sha256:[0-9a-f]{64}$')"
  mkdir -p "$EDGE"
  chmod 700 "$EDGE"
  trap restore_stage ERR
  cp "$A03/data/.config.yaml" "$EDGE/pre-a04.config.yaml"
  chmod 600 "$EDGE/pre-a04.config.yaml"
  python3 - "$EDGE/identity.json" <<'PY'
import json,secrets,sys
from pathlib import Path
# Temporary synthetic enrollment for staging; real 4B pairing happens at P3.
v={"device_id":"02:00:00:00:00:01","client_id":"11111111-2222-4333-8444-555555555555",
   "pair_secret":secrets.token_hex(32),"hostname":"voice.cncloudx.com","mode":"synthetic"}
p=Path(sys.argv[1])
p.write_text(json.dumps(v)+"\n")
p.chmod(0o600)
PY
  python3 - "$SRC/deploy/ai/a04/Caddyfile.in" "$EDGE/identity.json" "$EDGE/Caddyfile" <<'PY'
import json,sys
from pathlib import Path
template=Path(sys.argv[1]).read_text()
ident=json.loads(Path(sys.argv[2]).read_text())
for key,value in (("__PAIR_SECRET__",ident["pair_secret"]),("__DEVICE_ID__",ident["device_id"]),("__CLIENT_ID__",ident["client_id"])):
    assert template.count(key)>0,key
    template=template.replace(key,value)
p=Path(sys.argv[3]);p.write_text(template);p.chmod(0o444)
PY
  cp "$SRC/deploy/ai/a04/docker-compose.yml" "$EDGE/docker-compose.yml"
  chmod 600 "$EDGE/docker-compose.yml"
  printf 'CADDY_IMAGE=%s\n' "$caddy_digest" > "$EDGE/.env"
  chmod 600 "$EDGE/.env"
  edge_compose config -q
  edge_compose up -d --no-deps gateway >/dev/null
  # Docker reports "Started" before Caddy has bound its listening socket.
  # Probe the default-deny route first; do not change A03 until gate is healthy.
  gate_ready=0
  for n in $(seq 1 45); do
    http_code="$(curl --noproxy '*' -s --max-time 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/ || true)"
    if test "$http_code" = 403; then gate_ready=1; break; fi
    sleep 1
  done
  test "$gate_ready" = 1 || die "Caddy gateway did not become ready; CI logs / local private logs are needed"
  python3 - "$A03/data/.config.yaml" "$EDGE/identity.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);data=p.read_text();v=json.loads(Path(sys.argv[2]).read_text())
old="  websocket: ws://127.0.0.1:18000/xiaozhi/v1/"
assert data.count(old)==1,"A03 websocket baseline mismatch"
new="  websocket: wss://"+v["hostname"]+"/xiaozhi/v1/"+v["pair_secret"]
tmp=p.with_name(".config.yaml.a04tmp")
tmp.write_text(data.replace(old,new));tmp.chmod(0o600);tmp.replace(p)
PY
  ai_restart
  online=0
  for n in $(seq 1 50); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then online=1;break;fi
    sleep 2
  done
  test "$online" = 1
  python3 "$SRC/tests/ai/a04_gateway_smoke.py" --identity "$EDGE/identity.json" --origin http://127.0.0.1:18080
  test "$(known)" = "$old_containers" || die "known HomeSphere/MiniProbe running-container set changed"
  trap - ERR
  ok "local gateway staged; known and unknown synthetic device tests PASS; existing containers preserved"
  ok "OTA/WSS use a private 256-bit path secret; no public Tunnel or paid API enabled"
}
local_probe() {
  check_safe
  test -f "$EDGE/identity.json" || die "A04 stage missing"
  python3 "$SRC/tests/ai/a04_gateway_smoke.py" --identity "$EDGE/identity.json" --origin http://127.0.0.1:18080
}
connect() {
  check_safe
  local_probe
  test ! -e "$EDGE/tunnel-token" || die "Tunnel already configured; do not overwrite secret"
  printf 'Paste the dedicated S3-Voice Cloudflare Tunnel token (input hidden): ' >&2
  IFS= read -r -s token
  printf '\n' >&2
  size="$(printf '%s' "$token" | wc -c | tr -d ' ')"
  test "$size" -ge 80 || die "invalid/short token; no changes made"
  # Official cloudflared >= 2026.10 supports --token-file; lock manifest digest.
  digest="$(image_digest "$TUNNEL_TAG" '(^|/)cloudflared@sha256:[0-9a-f]{64}$')"
  # Host edge directory is 0700; world-readable mount file is inaccessible
  # to non-root host users but readable by container uid 65532.
  printf '%s' "$token" > "$EDGE/tunnel-token"
  unset token
  chmod 444 "$EDGE/tunnel-token"
  printf 'CLOUDFLARED_IMAGE=%s\n' "$digest" >> "$EDGE/.env"
  edge_compose --profile tunnel up -d --no-deps tunnel >/dev/null
  ok "dedicated Tunnel connector launched (outbound only, no host-network, no public inbound ports)"
  ok "Cloudflare dashboard must route voice.cncloudx.com -> http://gateway:8080"
  ok "run the public probe after configuring the published hostname"
}
public_probe() {
  check_safe
  test -f "$EDGE/identity.json" || die "A04 stage missing"
  python3 "$SRC/tests/ai/a04_gateway_smoke.py" --identity "$EDGE/identity.json" --origin https://voice.cncloudx.com
}
status() {
  local_probe
  edge_compose ps --format table
  ok "local A04 gate healthy; public route not claimed tested until public probe succeeds"
}
rollback() {
  require_root
  test -f "$EDGE/pre-a04.config.yaml" || die "no A04 backup found; refusing rollback"
  if test -f "$EDGE/.env"; then edge_compose --profile tunnel stop tunnel gateway >/dev/null; fi
  cp "$EDGE/pre-a04.config.yaml" "$A03/data/.config.yaml"
  chmod 600 "$A03/data/.config.yaml"
  ai_restart
  # Docker "Started" means the process launched, not that Python OTA bound 8003.
  restored=0
  for n in $(seq 1 45); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then
      restored=1
      break
    fi
    sleep 1
  done
  test "$restored" = 1 || die "A03 OTA health failed after rollback readiness window"
  ok "restored A03 pre-A04 configuration and stopped only dedicated A04 containers"
  ok "private A04 files retained; original HomeSphere/MiniProbe untouched"
}
case "$ACTION" in
  stage) stage ;;
  local) local_probe ;;
  connect) connect ;;
  public) public_probe ;;
  status) status ;;
  rollback) rollback ;;
  *) printf 'Usage: a04-edge.sh stage|local|connect|public|status|rollback\n'; exit 2 ;;
esac
