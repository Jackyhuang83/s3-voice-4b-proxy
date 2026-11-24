#!/usr/bin/env bash
# A09 Manager-Only pilot: stock web/manager-api + MySQL + Redis; no duplicate Python voice server.
# Modes: preflight | install | status | bridge | bridge-rollback | stop
set -Eeuo pipefail
set +x
umask 077
export LC_ALL=C
ROOT=/opt/s3-voice-manager
PROJECT=s3-voice-manager
PRODUCTION=/opt/s3-voice-ai
EDGE=/opt/s3-voice-ai-edge
SOURCE="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$SOURCE/deploy/ai/a09/docker-compose.yml"
COMPOSE="$ROOT/docker-compose.yml"
ENVFILE="$ROOT/.env"
IMAGE_PREFIX=ghcr.io/xinnan-tech/xiaozhi-esp32-server
UNBRIDGED_WSS=wss://manager-only-not-ready.invalid/xiaozhi/v1/

msg() { printf 'A09_%s: %s\n' "$1" "$2"; }
die() { msg BLOCKED "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing $1"; }
comp() { docker compose -p "$PROJECT" -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
mem_available() { awk '/^MemAvailable:/ {print $2;exit}' /proc/meminfo; }
swap_used() { awk '/^SwapTotal:/ {total=$2} /^SwapFree:/ {free=$2} END {print total-free}' /proc/meminfo; }
baseline() {
  local i
  for i in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do
    test "$(docker inspect -f '{{.State.Running}}' "$i" 2>/dev/null)" = true || die "existing $i not running"
  done
  test -r "$PRODUCTION/data/.config.yaml" || die 'existing voice config inaccessible'
  test -r "$EDGE/identity.json" || die 'existing gateway identity inaccessible'
}
baseline_ids() {
  docker inspect -f '{{.Id}}' s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel
}
memory_guard() {
  local avail
  avail="$(mem_available)"
  test "$avail" -ge 650000 || { msg BLOCKED 'less than ~635MiB MemAvailable after pilot startup; pilot must stop' >&2; return 1; }
  if test -r "$ROOT/.baseline-swap"; then
    local now was
    now="$(swap_used)"
    was="$(cat "$ROOT/.baseline-swap")"
    test "$((now-was))" -le 131072 || { msg BLOCKED 'swap use increased by >128MiB; pilot must stop' >&2; return 1; }
  fi
}
preflight() {
  test "$(id -u)" -eq 0 || die 'run as root'
  for x in docker curl awk ss df openssl python3 uname grep; do need "$x"; done
  test -r "$TEMPLATE" || die 'reviewed Manager-Only Compose missing'
  docker info >/dev/null 2>&1 || die 'Docker daemon inaccessible'
  docker compose version >/dev/null 2>&1 || die 'Docker Compose unavailable'
  test "$(uname -m)" = x86_64 || die 'official manager v0.9.8 image requires x86_64'
  local major total avail disk
  major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
  case "$major" in ''|*[!0-9]*) die 'unknown Docker Engine version';; esac
  test "$major" -ge 28 || die 'Docker 28+ required for localhost port publishing'
  baseline
  curl --noproxy '*' -fsS --max-time 4 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null || die 'existing 4B OTA unhealthy'
  test ! -e "$ROOT" || die 'Manager-Only pilot already exists; use status, never overwrite'
  if ss -H -lnt | awk '{print $4}' | grep -Eq ':19002$'; then die 'private manager port 19002 occupied'; fi
  total="$(awk '/^MemTotal:/ {print $2;exit}' /proc/meminfo)"
  avail="$(mem_available)"
  test "$total" -ge 3400000 || die 'physical RAM too small for shared Manager-Only pilot'
  test "$avail" -ge 1400000 || die 'less than ~1.34GiB MemAvailable; do not cohost manager'
  disk="$(df -Pk /opt | awk 'NR==2 {print $4}')"
  test "$disk" -ge 5242880 || die 'less than 5GiB disk available'
  msg PREFLIGHT_PASS 'read-only; no image pull, file change, or service restart'
}
image_digest() {
  local image="$1" repo="${1%%:*}" digest
  docker pull "$image" >&2 || die 'official version image pull failed'
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" | grep -F "${repo}@sha256:" | head -n 1 || true)"
  [[ "$digest" == "${repo}@sha256:"* ]] || die 'image digest not pinned'
  printf '%s' "$digest"
}
manager_secret() {
  printf "%s\n" "SELECT param_value FROM sys_params WHERE param_code='server.secret' LIMIT 1;" |
    comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --batch --skip-column-names -uroot xiaozhi_esp32_server' 2>/dev/null
}
sql_exec() {
  comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot xiaozhi_esp32_server' >/dev/null
}
invalidate_manager_params() {
  # Stock SysParamsRedis uses the hash sys:params. Do not flush the whole Redis DB.
  comp exec -T redis redis-cli HDEL sys:params server.secret server.websocket server.ota server.auth.enabled >/dev/null
}
wait_manager() {
  local code
  for _ in $(seq 1 90); do
    memory_guard || return 1
    code="$(curl --noproxy '*' -sS -L -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:19002/ 2>/dev/null || true)"
    [[ "$code" == 200 ]] && return 0
    sleep 2
  done
  return 1
}
stop_pilot_on_error() {
  local exit_code="$1"
  if [[ "$exit_code" -ne 0 && -f "$ENVFILE" ]]; then
    comp stop manager redis mysql >/dev/null 2>&1 || true
    msg PILOT_STOPPED 'Manager-Only containers stopped; original 4B untouched'
  fi
}
local_activation_probe() {
  python3 - <<'PYOTA'
import json, secrets, uuid, urllib.request, urllib.error
mac='02:'+':'.join(secrets.token_hex(1) for _ in range(5))
headers={'Device-Id':mac,'Client-Id':str(uuid.uuid4()),'Content-Type':'application/json'}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
req=urllib.request.Request('http://127.0.0.1:19002/xiaozhi/ota/',
    data=b'{"application":{"version":"2.6.0"}}',headers=headers,method='POST')
with opener.open(req,timeout=15) as resp:
    assert resp.status==200
    data=json.load(resp)
assert len(str((data.get('activation') or {}).get('code','')))==6
assert str(data['activation']['code']).isdigit()
assert bool((data.get('websocket') or {}).get('token'))
assert (data.get('websocket') or {}).get('url')=='wss://manager-only-not-ready.invalid/xiaozhi/v1/'
req=urllib.request.Request('http://127.0.0.1:19002/xiaozhi/ota/activate',
    headers=headers,method='POST',data=b'')
try:
    with opener.open(req,timeout=15) as resp:
        status=resp.status
except urllib.error.HTTPError as e:
    status=e.code
assert status==202,(status,'unbound activation should be 202')
print('A09_ACTIVATION_CONTRACT_PASS: OTA=200 CODE=6 TOKEN=True UNBOUND=202 (local only)')
PYOTA
}
install() {
  preflight
  local ids manager_image mysql_image redis_image secret
  ids="$(baseline_ids)"
  # Resource gate is deliberately before image pulls and filesystem changes.
  manager_image="$(image_digest "$IMAGE_PREFIX:web_0.9.8")"
  mysql_image="$(image_digest 'mysql:8.4')"
  redis_image="$(image_digest 'redis:8.0')"
  test ! -e "$ROOT" || die 'pilot directory appeared during image pull'
  mkdir -m 700 -p "$ROOT" "$ROOT/mysql" "$ROOT/redis" "$ROOT/uploadfile"
  trap 'stop_pilot_on_error "$?"' EXIT
  chmod 700 "$ROOT" "$ROOT/mysql" "$ROOT/redis" "$ROOT/uploadfile"
  printf '%s\n' "$(swap_used)" > "$ROOT/.baseline-swap"
  chmod 600 "$ROOT/.baseline-swap"
  cp "$TEMPLATE" "$COMPOSE"
  chmod 600 "$COMPOSE"
  {
    printf 'MANAGER_IMAGE=%s\nMYSQL_IMAGE=%s\nREDIS_IMAGE=%s\n' "$manager_image" "$mysql_image" "$redis_image"
    printf 'DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
  } > "$ENVFILE"
  chmod 600 "$ENVFILE"
  comp config --quiet || die 'Manager-Only compose validation failed'
  comp up -d --no-build mysql redis >/dev/null || die 'database containers failed'
  memory_guard
  comp up -d --no-build manager >/dev/null || die 'manager startup failed'
  wait_manager || die 'manager did not become healthy or memory guard failed'
  secret="$(manager_secret)" || die 'manager secret query failed'
  [[ "$secret" =~ ^[[:alnum:]_-]{16,128}$ ]] || die 'official manager secret missing'
  unset secret
  # Only the independent management database is written. No production file/API touched.
  printf '%s\n' \
    "UPDATE sys_params SET param_value='$UNBRIDGED_WSS' WHERE param_code='server.websocket';" \
    "UPDATE sys_params SET param_value='http://127.0.0.1:19002/xiaozhi/ota/' WHERE param_code='server.ota';" \
    "UPDATE sys_params SET param_value='true' WHERE param_code='server.auth.enabled';" | sql_exec
  invalidate_manager_params
  comp restart manager >/dev/null
  wait_manager || die 'manager unhealthy after isolated configuration'
  local_activation_probe || die 'stock six-digit OTA contract did not pass'
  memory_guard
  test "$(baseline_ids)" = "$ids" || die 'original 4B/gateway/tunnel container IDs unexpectedly changed'
  baseline
  trap - EXIT
  msg INSTALL_PASS 'Manager+MySQL+Redis only; six-digit local OTA passed; original voice not linked'
}
bridge_verify() {
  # Verify exact production HMAC parity, without printing bearer URL or secret.
  python3 - "$PRODUCTION/data/.config.yaml" "$EDGE/identity.json" <<'PYBRIDGE'
import base64,hashlib,hmac,json,re,secrets,sys,urllib.parse,urllib.request,uuid
from pathlib import Path
cfg=Path(sys.argv[1]).read_text()
ident=json.loads(Path(sys.argv[2]).read_text())
match=re.search(r'(?m)^  auth_key:\s*["\']?([a-zA-Z0-9_-]{16,128})["\']?\s*$',cfg)
assert match, 'production auth_key not a supported scalar; refuse bridge'
key=match.group(1)
assert re.search(r'(?m)^    enabled:\s*true\s*$',cfg), 'production WS auth disabled'
u=re.search(r'(?m)^  websocket:\s*["\']?(wss://[^\s"\']+)["\']?\s*$',cfg)
assert u, 'production WS URL missing'
url=u.group(1)
assert url=='wss://'+ident['hostname']+'/xiaozhi/v1/'+ident['pair_secret'], 'gateway secret mismatch'
headers={'Device-Id':'02:'+':'.join(secrets.token_hex(1) for _ in range(5)),
         'Client-Id':str(uuid.uuid4()),'Content-Type':'application/json'}
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
req=urllib.request.Request('http://127.0.0.1:19002/xiaozhi/ota/',
    data=b'{"application":{"version":"2.6.0"}}',headers=headers,method='POST')
with opener.open(req,timeout=15) as resp:
    data=json.load(resp)
ws=data.get('websocket') or {}
assert ws.get('url')==url, 'manager WS URL differs from production'
sig,ts=ws['token'].split('.')
expected=base64.urlsafe_b64encode(hmac.new(key.encode(),(headers['Client-Id']+'|'+headers['Device-Id']+'|'+ts).encode(),hashlib.sha256).digest()).decode().rstrip('=')
assert hmac.compare_digest(sig,expected), 'manager token rejected by production HMAC verification'
print('A09_BRIDGE_PROTOCOL_PASS: real voice URL matches; HMAC token cryptographically compatible')
PYBRIDGE
}
bridge_rollback() {
  test -f "$ENVFILE" || die 'Manager-Only not installed'
  test -r "$ROOT/.pre-bridge-secret" || die 'no Manager-Only bridge backup exists'
  local old_secret
  old_secret="$(cat "$ROOT/.pre-bridge-secret")"
  [[ "$old_secret" =~ ^[[:alnum:]_-]{16,128}$ ]] || die 'corrupt bridge backup'
  printf '%s\n' \
    "UPDATE sys_params SET param_value='$old_secret' WHERE param_code='server.secret';" \
    "UPDATE sys_params SET param_value='$UNBRIDGED_WSS' WHERE param_code='server.websocket';" | sql_exec
  invalidate_manager_params
  unset old_secret
  comp restart manager >/dev/null
  wait_manager || die 'pilot manager unhealthy after bridge rollback'
  rm -f "$ROOT/.bridged"
  msg BRIDGE_ROLLBACK_PASS 'only new manager DB reverted; original 4B unchanged'
}
bridge() {
  test "$(id -u)" -eq 0 || die 'run as root'
  test -f "$ENVFILE" || die 'run isolated install first'
  test ! -e "$ROOT/.bridged" || die 'bridge already applied'
  baseline
  curl --noproxy '*' -fsS --max-time 4 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null || die 'original OTA unhealthy'
  test ! -e "$ROOT/.pre-bridge-secret" || die 'bridge backup already exists; use bridge-rollback'
  local original
  original="$(manager_secret)" || die 'manager-generated secret absent'
  [[ "$original" =~ ^[[:alnum:]_-]{16,128}$ ]] || die 'manager secret malformed'
  printf '%s\n' "$original" > "$ROOT/.pre-bridge-secret"
  chmod 600 "$ROOT/.pre-bridge-secret"
  unset original
  # Read root-only production secrets; write *only* isolated management DB values.
  # Refuse unexpected YAML or mismatched gateway bearer; never print secret or URL.
  python3 - "$PRODUCTION/data/.config.yaml" "$EDGE/identity.json" <<'PYSQL' | sql_exec
import json,re,sys
from pathlib import Path
cfg=Path(sys.argv[1]).read_text()
ident=json.loads(Path(sys.argv[2]).read_text())
key=re.search(r'(?m)^  auth_key:\s*["\']?([A-Za-z0-9_-]{16,128})["\']?\s*$',cfg)
url=re.search(r'(?m)^  websocket:\s*["\']?(wss://[^\s"\']+)["\']?\s*$',cfg)
assert key and url and re.search(r'(?m)^    enabled:\s*true\s*$',cfg), 'production auth baseline mismatch'
assert url.group(1)=='wss://'+ident['hostname']+'/xiaozhi/v1/'+ident['pair_secret'], 'private WSS route mismatch'
assert re.fullmatch(r'wss://[A-Za-z0-9_.-]+/xiaozhi/v1/[a-f0-9]{64}',url.group(1)), 'unexpected URL shape'
print("UPDATE sys_params SET param_value='"+key.group(1)+"' WHERE param_code='server.secret';")
print("UPDATE sys_params SET param_value='"+url.group(1)+"' WHERE param_code='server.websocket';")
PYSQL
  invalidate_manager_params
  # Never restart or reconfigure production server/gateway/tunnel.
  if ! comp restart manager >/dev/null || ! wait_manager || ! bridge_verify; then
    bridge_rollback
    die 'bridge failed and reverted on isolated manager; original voice unchanged'
  fi
  touch "$ROOT/.bridged"
  chmod 600 "$ROOT/.bridged"
  baseline
  msg BRIDGE_PASS 'manager HMAC matches existing voice; no public route or iPhone binding yet'
}
status() {
  test -f "$ENVFILE" || die 'Manager-Only not installed'
  baseline
  comp ps
  msg RESOURCE "MemAvailable_KiB=$(mem_available); pilot-only status"
  if test -e "$ROOT/.bridged"; then msg BRIDGE 'local HMAC parity verified; iPhone still pending'; fi
}
stop() {
  test "$(id -u)" -eq 0 || die 'run as root'
  test -f "$ENVFILE" || die 'Manager-Only not installed'
  comp stop manager redis mysql >/dev/null
  baseline
  msg STOP_PASS 'stopped only three Manager-Only containers; no data deletion or production changes'
}
case "${1:-}" in
  preflight) preflight ;;
  install) install ;;
  bridge) bridge ;;
  bridge-rollback) bridge_rollback ;;
  status) status ;;
  stop) stop ;;
  *) printf 'Usage: sudo bash tools/ai/a09-fullmodule.sh preflight|install|bridge|bridge-rollback|status|stop\n' >&2; exit 2 ;;
esac
