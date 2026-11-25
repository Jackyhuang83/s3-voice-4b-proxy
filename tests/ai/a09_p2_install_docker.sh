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
  sudo rm -rf -- "$STAGE"
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
# Fake preexisting A04 default-deny gateway, using the real pinned Caddy image.
printf ':8080 {\n  respond "Forbidden" 403\n}\n' > "$TMP/Caddyfile"
chmod 0644 "$TMP/Caddyfile"
docker run -d --name s3-voice-ai-gateway --network s3-voice-ai-edge_front \
  -p 127.0.0.1:18080:8080 -v "$TMP/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.11.7-alpine >/dev/null
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
echo 'A09_P2_REAL_INSTALL_SIM_PASS: original Docker identities preserved; new pilot healthy; no host ports'
sudo bash "$ROOT/tools/ai/a09-lite-deploy.sh" stop > "$TMP/stop.log" 2>&1
grep -q '^A09_P2_STOP_PASS:' "$TMP/stop.log"
for n in s3-voice-a09-lite-adapter s3-voice-a09-lite-gateway; do
  test "$(docker inspect -f '{{.State.Running}}' "$n")" = false
done
test "$before" = "$(for n in s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel; do docker inspect -f '{{.Id}}' "$n"; done)"
echo 'A09_P2_REAL_STOP_SIM_PASS: two new containers stopped; original services never restarted'
