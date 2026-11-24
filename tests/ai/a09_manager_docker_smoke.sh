#!/usr/bin/env bash
# CI only: boot three stock Manager-Only containers on a disposable GitHub runner.
# Never called by the production VPS A09 installer.
set -Eeuo pipefail
set +x
umask 077
export LC_ALL=C
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
NAME=s3-voice-manager
CONF="$TMP/docker-compose.yml"
ENVFILE="$TMP/.env"
comp() { docker compose -p "$NAME" -f "$CONF" --env-file "$ENVFILE" "$@"; }
cleanup() {
  if test -f "$ENVFILE"; then comp down -v --remove-orphans >/dev/null 2>&1 || true; fi
  rm -rf "$TMP"
}
trap cleanup EXIT

get_digest() {
  local image="$1" repo="${1%%:*}" digest
  docker pull "$image" >/dev/null
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$image" | grep -F "${repo}@sha256:" | head -n 1 || true)"
  [[ "$digest" == "${repo}@sha256:"* ]] || { echo "CI_IMAGE_DIGEST_FAIL" >&2; exit 1; }
  printf '%s' "$digest"
}
cp "$ROOT/deploy/ai/a09/docker-compose.yml" "$CONF"
manager_image="$(get_digest 'ghcr.io/xinnan-tech/xiaozhi-esp32-server:web_0.9.8')"
mysql_image="$(get_digest 'mysql:8.4')"
redis_image="$(get_digest 'redis:8.0')"
{
  printf 'MANAGER_IMAGE=%s\nMYSQL_IMAGE=%s\nREDIS_IMAGE=%s\n' "$manager_image" "$mysql_image" "$redis_image"
  printf 'DB_PASSWORD=%s\n' "$(openssl rand -hex 24)"
} > "$ENVFILE"
chmod 600 "$ENVFILE"
comp config --quiet
comp up -d --no-build mysql redis manager
ready=0
for _ in $(seq 1 150); do
  code="$(curl --noproxy '*' -sS -L -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:19002/ 2>/dev/null || true)"
  if test "$code" = 200; then ready=1; break; fi
  sleep 2
done
if test "$ready" != 1; then
  echo 'A09_CI_MANAGER_NOT_READY' >&2
  comp ps
  comp logs --no-color --tail 35 manager | sed -E 's/([Pp]assword|[Ss]ecret|[Tt]oken)[=:][^ ]+/\1=[REDACTED]/g' || true
  exit 1
fi
secret="$(printf "%s\n" "SELECT param_value FROM sys_params WHERE param_code='server.secret' LIMIT 1;" | comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql --batch --skip-column-names -uroot xiaozhi_esp32_server')"
[[ "$secret" =~ ^[[:alnum:]_-]{16,128}$ ]] || { echo 'A09_CI_SECRET_MISSING' >&2; exit 1; }
unset secret
printf '%s\n' \
  "UPDATE sys_params SET param_value='wss://manager-only-not-ready.invalid/xiaozhi/v1/' WHERE param_code='server.websocket';" \
  "UPDATE sys_params SET param_value='http://127.0.0.1:19002/xiaozhi/ota/' WHERE param_code='server.ota';" \
  "UPDATE sys_params SET param_value='true' WHERE param_code='server.auth.enabled';" | \
  comp exec -T mysql sh -ec 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot xiaozhi_esp32_server' >/dev/null
comp exec -T redis redis-cli HDEL sys:params server.secret server.websocket server.ota server.auth.enabled >/dev/null
comp restart manager >/dev/null
ready=0
for _ in $(seq 1 90); do
  code="$(curl --noproxy '*' -sS -L -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:19002/ 2>/dev/null || true)"
  if test "$code" = 200; then ready=1; break; fi
  sleep 2
done
test "$ready" = 1 || { echo 'A09_CI_MANAGER_RESTART_FAIL' >&2; exit 1; }

python3 - <<'PYOTA'
import json, secrets, uuid, urllib.error, urllib.request
mac = '02:' + ':'.join(secrets.token_hex(1) for _ in range(5))
headers = {'Device-Id': mac, 'Client-Id': str(uuid.uuid4()), 'Content-Type': 'application/json'}
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
req = urllib.request.Request(
    'http://127.0.0.1:19002/xiaozhi/ota/',
    data=b'{"application":{"version":"2.6.0"}}', headers=headers, method='POST')
with opener.open(req, timeout=12) as response:
    assert response.status == 200
    data = json.load(response)
code = str((data.get('activation') or {}).get('code', ''))
assert len(code) == 6 and code.isdigit()
ws = data.get('websocket') or {}
assert ws.get('url') == 'wss://manager-only-not-ready.invalid/xiaozhi/v1/'
assert len(ws.get('token', '')) >= 24
req = urllib.request.Request(
    'http://127.0.0.1:19002/xiaozhi/ota/activate',
    headers=headers, data=b'', method='POST')
try:
    with opener.open(req, timeout=12) as response:
        status = response.status
except urllib.error.HTTPError as e:
    status = e.code
assert status == 202, f'unbound activate status = {status}'
print('A09_CI_DOCKER_INTEGRATION_PASS: 3 containers; OTA=200; six digits; token; unbound 202')
PYOTA

# Verify actual Docker host publish is loopback-only.
docker inspect -f '{{json .NetworkSettings.Ports}}' "$(comp ps -q manager)" | \
  python3 -c 'import json,sys; p=json.load(sys.stdin); x=p.get("8002/tcp") or []; assert len(x)>=1 and all(v["HostIp"]=="127.0.0.1" for v in x), p'
