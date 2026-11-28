#!/usr/bin/env bash
# GitHub-hosted disposable runner ONLY: executes the actual production P2
# install/status/stop, with synthetic A03/A04/Tunnel in isolated Docker.
# This is NOT a voice-device or Cloudflare account acceptance test.
set -Eeuo pipefail
set +x
export LC_ALL=C
if [[ "${GITHUB_ACTIONS:-}" != "true" || "${RUNNER_ENVIRONMENT:-}" != "github-hosted" ]]; then
  printf 'A09_P2_INSTALL_CI_BLOCKED: GitHub-hosted runner only\n' >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STAGE=/opt/s3-voice-a09-lite
[[ ! -e "$STAGE" && ! -L "$STAGE" ]] || { echo "A09_P2_INSTALL_CI_BLOCKED: stage already exists"; exit 2; }
TMP="$(mktemp -d)"
cleanup() {
  set +e
  if test -r "$STAGE/.env"; then
    sudo docker compose -p s3-voice-a09-lite -f "$STAGE/docker-compose.yml" \
      --env-file "$STAGE/.env" down --remove-orphans >/dev/null 2>&1
  fi
  docker rm -f s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel >/dev/null 2>&1
  docker network rm s3-voice-ai_default s3-voice-ai-edge_front >/dev/null 2>&1
  sudo rm -rf -- "$STAGE" /opt/s3-voice-ai-edge
  rm -rf -- "$TMP"
}
trap cleanup EXIT
docker network create s3-voice-ai_default >/dev/null
docker network create s3-voice-ai-edge_front >/dev/null
docker pull python:3.13.9-slim-bookworm >/dev/null
docker pull caddy:2.11.7-alpine >/dev/null
# Fake preexisting A03: same 8003 OTA and 8000 WS ports and Docker DNS name.
docker run -d --name s3-voice-ai-server \
  --network s3-voice-ai_default -p 127.0.0.1:18003:8003 \
  -v "$ROOT/tests/ai/a09_p2_fake_voice.py:/tmp/fake.py:ro" \
  python:3.13.9-slim-bookworm python -I /tmp/fake.py >/dev/null
# Real production A04 Caddy template, with a synthetic original 4B identity.
# This is crucial: the same-host test must preserve an actual legacy OTA/WS
# matcher rather than a fake 403-only gateway.
sudo mkdir -p /opt/s3-voice-ai-edge
sudo python3 - "$ROOT/deploy/ai/a04/Caddyfile.in" /opt/s3-voice-ai-edge/Caddyfile <<'PY'
from pathlib import Path
import sys
text=Path(sys.argv[1]).read_text()
for k,v in [
    ('__PAIR_SECRET__', 'a'*64),
    ('__DEVICE_ID__', '02:01:02:03:04:05'),
    ('__CLIENT_ID__', 'same-host-original-client-id'),
]:
    assert k in text
    text=text.replace(k,v)
Path(sys.argv[2]).write_text(text)
PY
sudo chmod 0444 /opt/s3-voice-ai-edge/Caddyfile
docker run -d --name s3-voice-ai-gateway --network s3-voice-ai-edge_front \
  -p 127.0.0.1:18080:8080 -v /opt/s3-voice-ai-edge/Caddyfile:/etc/caddy/Caddyfile:ro \
  caddy:2.11.7-alpine >/dev/null
docker network connect s3-voice-ai_default s3-voice-ai-gateway
# Synthetic original Tunnel: no Cloudflare token, no outbound tunnel traffic.
docker run -d --name s3-voice-ai-tunnel --network s3-voice-ai-edge_front \
  python:3.13.9-slim-bookworm python -c 'import time; time.sleep(600)' >/dev/null
ready=0
for i in $(seq 1 45); do
  ota="$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ || true)"
  deny="$(curl --noproxy '*' -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:18080/ || true)"
  if [[ "$ota" == 200 && "$deny" == 403 ]]; then ready=1; break; fi
  sleep 1
done
test "$ready" = 1 || { echo A09_P2_INSTALL_CI_FAKE_ORIGINAL_UNHEALTHY >&2; exit 1; }
before="$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
# CRITICAL: execute the real installer code, not a parallel test-only Compose.
sudo bash "$ROOT/tools/ai/a09-lite-deploy.sh" install > "$TMP/install.log" 2>&1 || {
  tail -n 90 "$TMP/install.log" | sed -E 's#(IOS_SECRET|Bearer|Authorization)=[^[:space:]]+#\1=REDACTED#g' >&2
  echo A09_P2_INSTALL_CI_FAILED >&2
  exit 1
}
grep -q '^A09_P2_PREFLIGHT_PASS:' "$TMP/install.log"
grep -q '^A09_P2_GATE_PASS:' "$TMP/install.log"
grep -q '^A09_P2_PILOT_PASS:' "$TMP/install.log"

# Reproduce the user's ALREADY-installed A09 adapter, not a fresh new build.
BASELINE_A09=c0bb348deac4edf4be079e540ccc5aafffa39d00
git -C "$ROOT" fetch -q --depth 1 origin "$BASELINE_A09"
git -C "$ROOT" show "$BASELINE_A09:tools/ai/a09_lite.py" | sudo tee "$STAGE/a09_lite.py" >/dev/null
docker restart s3-voice-a09-lite-adapter >/dev/null

grep -q '^A09_P2_PUBLIC_NOT_READY:' "$TMP/install.log"
for n in s3-voice-a09-lite-adapter s3-voice-a09-lite-gateway; do
  test "$(docker inspect -f '{{.State.Running}}' "$n")" = true
  docker inspect -f '{{json .NetworkSettings.Ports}}' "$n" | python3 -c \
    'import json,sys; ports=json.load(sys.stdin); assert not any(v for v in ports.values()), ports'
done
after="$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
test "$before" = "$after" || { echo A09_P2_INSTALL_CI_ORIGINAL_RECREATED >&2; exit 1; }
sudo bash "$ROOT/tools/ai/a09-lite-deploy.sh" status > "$TMP/status.log" 2>&1
grep -q '^A09_P2_STATUS:' "$TMP/status.log"
grep -q '^A09_P2_PENDING_STATUS: active=0 expired=0 approved=0' "$TMP/status.log"
echo 'A09_P2_REAL_INSTALL_SIM_PASS: original Docker identities preserved; new pilot healthy; no host ports'
before_a04="$(sudo sha256sum /opt/s3-voice-ai-edge/Caddyfile | cut -d' ' -f1)"
# Run the actual new one-domain code. GitHub-hosted simulator skips ONLY the
# impossible public Cloudflare verification; local Caddy routing is exercised.
sudo env GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=github-hosted \
  A09_SAME_HOST_SIMULATOR=1 python3 "$ROOT/tools/ai/a09_same_host.py" apply \
  > "$TMP/same-host.log" 2>&1 || {
  cat "$TMP/same-host.log" >&2
  echo A09_P2_SAME_HOST_CI_FAILED >&2
  exit 1
}
grep -q '^A09_P2_SAME_HOST_PILOT_PASS:' "$TMP/same-host.log"
sudo python3 - "$STAGE/.env" <<'PY'
from pathlib import Path
import sys
env=Path(sys.argv[1]).read_text()
assert 'IOS_HOSTNAME=voice.cncloudx.com' in env
PY
# Correct route forwards the *existing* A04 host to A09 without changing 4B
# identity and exact private routes. The probe never logs the private new URL.
sudo python3 - "$STAGE/.env" <<'PY'
import base64, http.client, json, os, subprocess, sys, urllib.request, urllib.error
env=dict(line.split('=',1) for line in open(sys.argv[1]).read().splitlines())
def ws(path, device, client, token):
    headers={'Device-Id':device,'Client-Id':client,'Authorization':'Bearer '+token,
             'Upgrade':'websocket','Connection':'Upgrade',
             'Sec-WebSocket-Key':base64.b64encode(os.urandom(16)).decode(),
             'Sec-WebSocket-Version':'13'}
    conn=http.client.HTTPConnection('127.0.0.1',18080,timeout=7)
    try:
        conn.request('GET',path,headers=headers)
        response=conn.getresponse()
        return response.status
    finally:
        conn.close()
url='http://127.0.0.1:18080/xiaozhi/ota/'+env['IOS_SECRET']
headers={'Device-Id':'02:ab:cd:ef:45:67','Client-Id':'a09-same-host-test','Content-Type':'application/json'}
request=urllib.request.Request(url,data=b'{"application":{"version":"2.6.0"}}',headers=headers)
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=8) as resp:
    body=json.load(resp)
assert body['websocket']['url'].startswith('wss://voice.cncloudx.com/xiaozhi/v1/')
assert len(body['activation']['code'])==6
# Verify a pending code exists on THIS adapter without disclosing its value.
summary=subprocess.check_output(['bash',os.path.join(os.getcwd(),'tools/ai/a09-lite-deploy.sh'),'pending'],text=True)
assert 'active=1' in summary,(summary,)
secret_ota='http://127.0.0.1:18080/xiaozhi/ota/'+env['IOS_SECRET']+'/activate'
def activation_code():
    req=urllib.request.Request(secret_ota,data=b'{}',headers=headers,method='POST')
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code
assert activation_code()==202

secret=env['IOS_SECRET']
device='02:ab:cd:ef:45:67'
client='a09-same-host-test'
token=body['websocket']['token']
assert ws('/xiaozhi/v1/'+secret,device,client,token)==403
p=subprocess.run(['docker','exec','-i','-u','10001','s3-voice-a09-lite-adapter',
                  'python','-I','/app/a09_lite.py','--db',
                  '/var/lib/s3-voice-a09-lite/activation.sqlite3',
                  'approve','-'],
                 input=body['activation']['code']+'\n',capture_output=True,text=True,timeout=10)
assert p.returncode==0,p.stderr
summary=subprocess.check_output(['bash',os.path.join(os.getcwd(),'tools/ai/a09-lite-deploy.sh'),'pending'],text=True)
assert 'active=0' in summary and 'approved=1' in summary,(summary,)
assert activation_code()==200
assert ws('/xiaozhi/v1/'+secret,device,client,token)==101
assert ws('/xiaozhi/v1/'+secret,device,client,'bad.fake')==403
assert ws('/xiaozhi/v1/'+secret,device,'other-device',token)==403
# Legacy original OTA identity must still reach fake A03 through old A04.
original='http://127.0.0.1:18080/xiaozhi/ota/'+'a'*64
headers={'Device-Id':'02:01:02:03:04:05','Client-Id':'same-host-original-client-id','Content-Type':'application/json'}
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
    urllib.request.Request(original,data=b'{}',headers=headers),timeout=8) as resp:
    assert resp.status==200
    legacy=json.load(resp)
assert ws('/xiaozhi/v1/'+'a'*64,headers['Device-Id'],
          headers['Client-Id'],legacy['websocket']['token'])==101
print('A09_P2_SAME_HOST_ROUTE_CI_PASS: old 4B OTA/WS101 and new iPhone OTA, owner approve, WS403/101')
PY
# Read-only audit of ACTUAL A04 bind mount and its local secret OTA route.
sudo python3 "$ROOT/tools/ai/a09_edge_audit.py" --local-only > "$TMP/edge-audit.log" 2>&1 || {
  cat "$TMP/edge-audit.log" >&2
  echo A09_EDGE_AUDIT_CI_FAILED >&2
  exit 1
}
grep -q '^A09_EDGE_CADDY_CONFIG: EXACT_A09_ROUTE_PRESENT;' "$TMP/edge-audit.log"
grep -qx 'A09_EDGE_LOCAL_HTTP: 400' "$TMP/edge-audit.log"
grep -qx 'A09_EDGE_LOCAL_VERDICT: PASS' "$TMP/edge-audit.log"
echo 'A09_EDGE_CI_PASS: synthetic invalid OTA reaches actual Caddy route; no activation or Cloudflare modification'
before_diag="$(sudo sha256sum /opt/s3-voice-ai-edge/Caddyfile | cut -d' ' -f1)"
sudo python3 "$ROOT/tools/ai/a09_diagnose.py" arm > "$TMP/diag-arm.log" 2>&1 || {
  tail -n 35 "$TMP/diag-arm.log" >&2
  echo A09_DIAG_CI_ARM_FAILED >&2
  exit 1
}
grep -q '^A09_DIAG_ARM_PASS:' "$TMP/diag-arm.log"
sudo python3 "$ROOT/tools/ai/a09_diagnose.py" report > "$TMP/diag-initial.log"
grep -q '^A09_DIAG_VERDICT: NO_A09_OTA_REACHED' "$TMP/diag-initial.log"
# Missing Client-Id must reach the NEW adapter, be counted, and fail HTTP 400.
sudo python3 - "$STAGE/.env" <<'PY'
import sys,urllib.request,urllib.error
env=dict(line.split('=',1) for line in open(sys.argv[1]).read().splitlines())
req=urllib.request.Request(
    'http://127.0.0.1:18080/xiaozhi/ota/'+env['IOS_SECRET'],
    data=b'{"application":{"version":"2.6.0"}}',
    headers={'Device-Id':'02:01:02:03:04:77','Content-Type':'application/json'},
    method='POST')
try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=8)
    raise SystemExit('A09_DIAG_CI_MISSING_ID_NOT_REJECTED')
except urllib.error.HTTPError as e:
    assert e.code==400,e.code
PY
sudo python3 "$ROOT/tools/ai/a09_diagnose.py" report > "$TMP/diag-final.log"
grep -q '^A09_DIAG_VERDICT: MISSING_REQUIRED_IDENTITY' "$TMP/diag-final.log"
grep -q 'missing_client_id=1' "$TMP/diag-final.log"
grep -q 'ota_seen=1' "$TMP/diag-final.log"
sudo python3 "$ROOT/tools/ai/a09_diagnose.py" rollback > "$TMP/diag-rollback.log"
grep -q '^A09_DIAG_ROLLBACK_PASS:' "$TMP/diag-rollback.log"
test "$before_diag" = "$(sudo sha256sum /opt/s3-voice-ai-edge/Caddyfile | cut -d' ' -f1)"
test "$before" = "$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
echo 'A09_DIAG_CI_PASS: old adapter upgraded temporarily; missing Client-Id counted/denied; exact Caddy and adapter restored'
sudo python3 "$ROOT/tools/ai/a09_same_host.py" rollback > "$TMP/rollback.log" 2>&1
grep -q '^A09_P2_SAME_HOST_ROLLBACK_PASS:' "$TMP/rollback.log"
test "$before_a04" = "$(sudo sha256sum /opt/s3-voice-ai-edge/Caddyfile | cut -d' ' -f1)"
test "$before" = "$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
echo 'A09_P2_SAME_HOST_ROLLBACK_CI_PASS: exact A04 Caddy bytes restored, original containers unchanged'
sudo bash "$ROOT/tools/ai/a09-lite-deploy.sh" stop > "$TMP/stop.log" 2>&1
grep -q '^A09_P2_STOP_PASS:' "$TMP/stop.log"
for n in s3-voice-a09-lite-adapter s3-voice-a09-lite-gateway; do
  test "$(docker inspect -f '{{.State.Running}}' "$n")" = false
done
test "$before" = "$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
echo 'A09_P2_REAL_STOP_SIM_PASS: two new containers stopped; original services never restarted'
