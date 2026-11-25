#!/usr/bin/env bash
# Disposable GitHub runner ONLY. Exercises real official Caddy 2.11.7 and
# Python 3.13 containers against a fake A03 HMAC server, never paid APIs.
set -Eeuo pipefail
set +x
umask 077
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
PROJECT=s3-voice-a09-lite
ENVFILE="$TMP/.env"
CONFFILE="$TMP/docker-compose.yml"
CID=a09-lite-ci-voice
comp() { docker compose -p "$PROJECT" -f "$CONFFILE" --env-file "$ENVFILE" "$@"; }
cleanup() {
  if test -r "$ENVFILE"; then comp down --remove-orphans >/dev/null 2>&1 || true; fi
  docker rm -f "$CID" >/dev/null 2>&1 || true
  docker network rm s3-voice-ai_default s3-voice-ai-edge_front >/dev/null 2>&1 || true
  sudo rm -rf -- "$TMP"
}
trap cleanup EXIT
# This test owns the two production-like names on the ephemeral runner only.
docker network create s3-voice-ai_default >/dev/null
docker network create s3-voice-ai-edge_front >/dev/null
docker pull python:3.13.9-slim-bookworm >/dev/null
docker pull caddy:2.11.7-alpine >/dev/null
mkdir -p "$TMP/data"
sudo chown 10001:10001 "$TMP/data"
sudo chmod 0700 "$TMP/data"
cp "$ROOT/tools/ai/a09_lite.py" "$TMP/a09_lite.py"
# Runner umask 077 must not block non-root UID10001 on the read-only file mount.
chmod 0644 "$TMP/a09_lite.py"
cp "$ROOT/deploy/ai/a09-lite/docker-compose.yml" "$CONFFILE"
secret="$(openssl rand -hex 32)"
python3 - "$ROOT/deploy/ai/a09-lite/Caddyfile.in" "$TMP/Caddyfile" "$secret" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1]).read_text()
Path(sys.argv[2]).write_text(p.replace('__IOS_SECRET__',sys.argv[3]))
PY
chmod 0444 "$TMP/Caddyfile"
{
  printf 'PYTHON_IMAGE=%s\n' python:3.13.9-slim-bookworm
  printf 'CADDY_IMAGE=%s\n' caddy:2.11.7-alpine
  printf 'IOS_HOSTNAME=%s\n' ios-voice.cncloudx.com
  printf 'IOS_SECRET=%s\n' "$secret"
} > "$ENVFILE"
chmod 0600 "$ENVFILE"
# A03 fake server has stable DNS alias matching the genuine A03 project.
docker run -d --name "$CID" --network s3-voice-ai_default --network-alias s3-voice-ai-server \
  -v "$ROOT/tests/ai/a09_p2_fake_voice.py:/tmp/fake.py:ro" \
  python:3.13.9-slim-bookworm python -I /tmp/fake.py >/dev/null
comp config --quiet
comp run --rm --no-deps adapter python -I /app/a09_lite.py --db /var/lib/s3-voice-a09-lite/activation.sqlite3 init >/dev/null
comp up -d --no-build adapter gateway >/dev/null
# Do not assume Docker Compose "Started" means the Caddy listener is ready.
for i in $(seq 1 40); do
  if docker exec s3-voice-a09-lite-adapter python -I -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:19009/health',timeout=2)" >/dev/null 2>&1; then break; fi
  sleep 1
done
# The CI client executes from adapter's isolated Docker namespace and reads
# its own WSS URL from env, so no secret or active 4B identifier is logged.
docker exec -i s3-voice-a09-lite-adapter python -I - <<'PY'
import base64, json, os, socket, subprocess, sys, urllib.error, urllib.parse, urllib.request
DEVICE = '02:ab:cd:ef:45:67'
CLIENT = '9dabdafe-3d8a-4e40-97d5-2e05c310c912'
WSS = os.environ['A09_LITE_WSS_URL']
SECRET = WSS.rsplit('/',1)[1]
BASE = 'http://gateway:8080'
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HEADERS = {'Device-Id': DEVICE, 'Client-Id': CLIENT, 'Content-Type': 'application/json'}

def http(path, method='POST', headers=None):
    payload = b'{"application":{"version":"2.6.0"}}' if method=='POST' else None
    req = urllib.request.Request(BASE+path, headers=headers or HEADERS, data=payload, method=method)
    try:
        with OPENER.open(req,timeout=6) as r:
            return r.status,r.read()
    except urllib.error.HTTPError as e:
        return e.code,e.read()

def ws(device=DEVICE, client=CLIENT, token='', route=None):
    headers = {'Device-Id':device, 'Client-Id':client,
               'Authorization':'Bearer '+token, 'Upgrade':'websocket',
               'Connection':'Upgrade', 'Sec-WebSocket-Key':base64.b64encode(os.urandom(16)).decode(),
               'Sec-WebSocket-Version':'13'}
    return http('/xiaozhi/v1/'+(route or SECRET), method='GET', headers=headers)[0]

assert http('/')[0]==403
assert http('/health',method='GET')[0]==403
assert http('/internal/authorize-ws',method='GET')[0]==403
assert http('/xiaozhi/ota/invalidsecret')[0]==403
status, body = http('/xiaozhi/ota/'+SECRET)
assert status==200,(status,body)
answer=json.loads(body)
assert len(answer['activation']['code'])==6
assert answer['websocket']['url']==WSS
assert answer['websocket']['token']
assert not answer['firmware']['url']
code=answer['activation']['code']
token=answer['websocket']['token']
print('A09_P2_CI_OTA_PASS: six digits, existing HMAC and distinct iOS WSS')
assert http('/xiaozhi/ota/activate')[0]==202
assert ws(token=token)==403
assert ws(device='02:ab:cd:ef:45:68',token=token)==403
# Owner approval is CLI only; no HTTP approval endpoint.
proc=subprocess.run([sys.executable,'-I','/app/a09_lite.py','--db','/var/lib/s3-voice-a09-lite/activation.sqlite3','approve','-'],input=code+'\n',text=True,capture_output=True,timeout=5)
assert proc.returncode==0,proc.stderr
assert http('/xiaozhi/ota/activate')[0]==200
assert ws(token=token)==101
assert ws(client='9dabdafe-3d8a-4e40-97d5-2e05c310c913',token=token)==403
assert ws(token='bogus.fake')==403
status, body=http('/xiaozhi/ota/'+SECRET)
assert status==200 and 'activation' not in json.loads(body)
print('A09_P2_CI_BIND_PASS: 202->200; WS 403 prebind, 101 after, HMAC invalid denied')
assert http('/xiaozhi/ota/'+SECRET,headers={'Device-Id':DEVICE,'Client-Id':'wrong'})[0]==403
assert http('/xiaozhi/ota/activate',headers={'Device-Id':DEVICE,'Client-Id':'wrong'})[0]==202
print('A09_P2_CI_ISOLATION_PASS: wrong identity and hidden internal endpoints denied')
PY
# No new host ports: adapter/gateway have empty port bindings.
for name in s3-voice-a09-lite-adapter s3-voice-a09-lite-gateway; do
  docker inspect -f '{{json .NetworkSettings.Ports}}' "$name" | python3 -c \
    'import json,sys; ports=json.load(sys.stdin); assert not any(v for v in ports.values()),ports'
done
printf '%s\n' 'A09_P2_CI_NETWORK_PASS: no host-published ports; real Caddy+Python Docker integration PASS'