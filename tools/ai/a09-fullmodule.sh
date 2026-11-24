#!/usr/bin/env bash
# Optional full XiaoZhi v0.9.8 pilot, independent of A03/A04/A07 and Waveshare 4B.
# Usage: sudo bash tools/ai/a09-fullmodule.sh preflight|install|status|stop
set -Eeuo pipefail
set +x
umask 077
export LC_ALL=C
ROOT=/opt/s3-voice-fullpilot
PROJECT=s3-voice-fullpilot
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$SOURCE/deploy/ai/a09/docker-compose.yml"
COMPOSE="$ROOT/docker-compose.yml"
ENVFILE="$ROOT/.env"
# Host placement is explicit for install; persisted so status/stop remain safe.
HOST_MODE=cohost
case "${1:-}" in
  preflight-remote|install-remote) HOST_MODE=remote ;;
  *)
    if test -r "$ROOT/.host-mode"; then HOST_MODE="$(cat "$ROOT/.host-mode")"; fi
    ;;
esac
case "$HOST_MODE" in cohost|remote) ;; *) echo 'A09_BLOCKED: invalid host mode' >&2; exit 1 ;; esac
IMAGE_PREFIX=ghcr.io/xinnan-tech/xiaozhi-esp32-server

msg() { printf 'A09_%s: %s\n' "$1" "$2"; }
die() { msg BLOCKED "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing $1"; }
comp() { docker compose -p "$PROJECT" -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
containers_in_scope() {
  local i
  # Remote mode is for a separate VPS, never one already running S3-Voice production.
  if [[ "$HOST_MODE" == remote ]]; then
    for i in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do
      if docker inspect "$i" >/dev/null 2>&1; then
        die "$i exists; refuse remote mode on a production S3-Voice host"
      fi
    done
    return 0
  fi
  # Cohost mode retains the original live-production health guard.
  for i in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do
    test "$(docker inspect -f '{{.State.Running}}' "$i" 2>/dev/null)" = true || die "$i is not running"
  done
}
preflight() {
  test "$(id -u)" -eq 0 || die 'run as root'
  for x in docker curl awk ss df openssl python3 uname; do need "$x"; done
  test -r "$TEMPLATE" || die 'reviewed Compose template missing'
  docker info >/dev/null 2>&1 || die 'Docker daemon inaccessible'
  docker compose version >/dev/null 2>&1 || die 'Docker Compose unavailable'
  test "$(uname -m)" = x86_64 || die 'official v0.9.8 full images require x86_64'
  major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
  case "$major" in ''|*[!0-9]*) die 'unknown Docker version';; esac
  test "$major" -ge 28 || die 'Docker Engine 28+ needed for loopback-only publishing safety'
  containers_in_scope
  test ! -e "$ROOT" || die 'pilot already exists; use status; never overwrite it'
  for port in 19000 19002 19003; do
    if ss -H -lnt | awk '{print $4}' | grep -Eq ":${port}$"; then
      die "pilot TCP port $port occupied"
    fi
  done
  mem_total="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo)"
  mem_available="$(awk '/^MemAvailable:/ {print $2; exit}' /proc/meminfo)"
  test "$mem_total" -ge 3800000 || die 'less than ~4GB physical RAM; do not cohost full module'
  test "$mem_available" -ge 2400000 || die 'less than 2.3GiB currently available; leave old services running'
  disk_free="$(df -Pk /opt | awk 'NR==2 {print $4}')"
  test "$disk_free" -ge 10485760 || die 'less than 10GiB available on /opt filesystem'
  msg PREFLIGHT_PASS 'hardware/resource/ports/baseline checked; no changes made'
}
image_digest() {
  local image="$1" repo="${1%%:*}" digest
  docker pull "$image" >&2 || die 'official/pinned-version image pull failed'
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" | grep -F "${repo}@sha256:" | head -n 1 || true)"
  [[ "$digest" == "${repo}@sha256:"* ]] || die 'image digest not resolved'
  printf '%s' "$digest"
}
wait_manager() {
  local code
  for _ in $(seq 1 100); do
    code="$(curl --noproxy '*' -sS -L -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:19002/ 2>/dev/null || true)"
    if [[ "$code" == 200 ]]; then return 0; fi
    sleep 2
  done
  die 'pilot manager did not become healthy; original A03 unaffected'
}
manager_secret() {
  printf '%s\n' "SELECT param_value FROM sys_params WHERE param_code='server.secret' LIMIT 1;" | \
    comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --batch --skip-column-names -uroot xiaozhi_esp32_server' 2>/dev/null
}
configure() {
  test -f "$ENVFILE" || die 'run install first'
  local secret
  secret="$(manager_secret)" || die 'manager DB secret query failed'
  [[ "$secret" =~ ^[[:alnum:]_-]{16,128}$ ]] || die 'manager secret absent or malformed'
  # Stock server will request the complete config and assigned agent config from manager.
  cat > "$ROOT/data/.config.yaml" <<YAML
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  vision_explain: http://127.0.0.1:19003/mcp/vision/explain
  auth_key: "$secret"
manager-api:
  url: http://manager:8002/xiaozhi
  secret: "$secret"
prompt_template: agent-base-prompt.txt
YAML
  chmod 600 "$ROOT/data/.config.yaml"
  # Only the new, isolated manager database is updated; original S3 voice is untouched.
  printf '%s\n' \
    "UPDATE sys_params SET param_value='ws://127.0.0.1:19000/xiaozhi/v1/' WHERE param_code='server.websocket';" \
    "UPDATE sys_params SET param_value='http://127.0.0.1:19002/xiaozhi/ota/' WHERE param_code='server.ota';" \
    "UPDATE sys_params SET param_value='true' WHERE param_code='server.auth.enabled';" | \
    comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot xiaozhi_esp32_server' >/dev/null
  comp restart manager >/dev/null
  wait_manager
  comp --profile voice up -d --no-deps server >/dev/null
  for _ in $(seq 1 60); do
    if curl --noproxy '*' -fsS --max-time 3 http://127.0.0.1:19003/xiaozhi/ota/ >/dev/null 2>&1; then
      msg SERVER_READY 'isolated full server started'
      return 0
    fi
    sleep 2
  done
  die 'manager installed but isolated full server did not start; old server unchanged'
}
a09_install_exit() {
  local result="$1"
  if [[ "$result" -ne 0 && -f "$ENVFILE" ]]; then
    comp --profile voice stop >/dev/null 2>&1 || true
    msg PILOT_STOPPED 'installation failed; pilot stopped, files preserved; baseline untouched'
  fi
}
install() {
  preflight
  local server_image manager_image mysql_image redis_image
  server_image="$(image_digest "$IMAGE_PREFIX:server_0.9.8")"
  manager_image="$(image_digest "$IMAGE_PREFIX:web_0.9.8")"
  mysql_image="$(image_digest 'mysql:8.4')"
  redis_image="$(image_digest 'redis:8.0')"
  test ! -e "$ROOT" || die 'pilot path unexpectedly appeared'
  mkdir -m 700 -p "$ROOT" "$ROOT/data" "$ROOT/mysql" "$ROOT/redis" "$ROOT/uploadfile"
  printf '%s\n' "$HOST_MODE" > "$ROOT/.host-mode"
  chmod 600 "$ROOT/.host-mode"
  trap 'a09_install_exit "$?"' EXIT
  chmod 700 "$ROOT" "$ROOT/data" "$ROOT/mysql" "$ROOT/redis" "$ROOT/uploadfile"
  cp "$TEMPLATE" "$COMPOSE"
  chmod 600 "$COMPOSE"
  {
    printf 'SERVER_IMAGE=%s\nMANAGER_IMAGE=%s\nMYSQL_IMAGE=%s\nREDIS_IMAGE=%s\n' "$server_image" "$manager_image" "$mysql_image" "$redis_image"
    printf 'DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  } > "$ENVFILE"
  chmod 600 "$ENVFILE"
  comp config --quiet || die 'pilot compose validation failed; old services untouched'
  comp up -d --no-build mysql redis manager >/dev/null || die 'pilot manager startup failed; old services untouched'
  wait_manager
  msg MANAGER_READY 'private 127.0.0.1:19002 only; no Cloudflare/4B modifications'
  configure
  # Stock manager OTA contract: six digits + signed token, no paid model invocation.
  python3 - <<'PYOTA'
import json, secrets, uuid, urllib.request, urllib.error
mac='02:'+':'.join(secrets.token_hex(1) for _ in range(5))
hdr={'Device-Id':mac,'Client-Id':str(uuid.uuid4()),'Content-Type':'application/json'}
req=urllib.request.Request('http://127.0.0.1:19002/xiaozhi/ota/',data=b'{"application":{"version":"2.6.0"}}',headers=hdr,method='POST')
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as resp:
    assert resp.status == 200
    result=json.load(resp)
assert len(str(result.get('activation',{}).get('code','')))==6
assert str(result['activation']['code']).isdigit()
assert result.get('websocket',{}).get('url')=='ws://127.0.0.1:19000/xiaozhi/v1/'
assert len(result.get('websocket',{}).get('token',''))>=24
req=urllib.request.Request('http://127.0.0.1:19002/xiaozhi/ota/activate',headers=hdr,method='POST',data=b'')
try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=15) as resp:
        status=resp.status
except urllib.error.HTTPError as e:
    status=e.code
assert status==202,(status,'unbound activation check should be 202')
print('A09_ACTIVATION_CONTRACT_PASS: OTA 200 / 6digits / token / unbound 202')
PYOTA
  containers_in_scope
  msg INSTALL_PASS 'full module pilot deployed locally (iPhone/public integration NOT accepted)'
  msg NEXT 'Use SSH port forward for administrator registration; public OTA and voice need P2 validation'
}
status() {
  test -f "$ENVFILE" || die 'pilot not installed'
  containers_in_scope
  comp --profile voice ps
}
stop() {
  test -f "$ENVFILE" || die 'pilot not installed'
  comp --profile voice stop >/dev/null
  containers_in_scope
  msg STOP_PASS 'stopped only pilot containers; no data deletion, 4B baseline untouched'
}
case "${1:-}" in
  preflight|preflight-remote) preflight ;;
  install|install-remote) install ;;
  status) status ;;
  stop) stop ;;
  *) echo 'Usage: sudo bash tools/ai/a09-fullmodule.sh preflight|install|preflight-remote|install-remote|status|stop' >&2; exit 2 ;;
esac
