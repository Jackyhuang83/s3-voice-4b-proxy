#!/usr/bin/env bash
# A09-Lite P2: independently deploy two tiny containers; existing 4B never changed.
# sudo bash tools/ai/a09-lite-deploy.sh preflight|install|status|pending|approve|revoke|stop
set -Eeuo pipefail
set +x
umask 077
export LC_ALL=C
ROOT=/opt/s3-voice-a09-lite
SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE="$ROOT/docker-compose.yml"
ENVFILE="$ROOT/.env"
PROJECT=s3-voice-a09-lite
PYTHON_TAG=python:3.13.9-slim-bookworm
IOS_HOSTNAME=ios-voice.cncloudx.com
BASELINE_CONTAINERS=(s3-voice-ai-server s3-voice-ai-gateway s3-voice-ai-tunnel)
comp() { docker compose -p "$PROJECT" -f "$COMPOSE" --env-file "$ENVFILE" "$@"; }
msg() { printf 'A09_P2_%s: %s\n' "$1" "$2"; }
die() { msg BLOCKED "$*" >&2; exit 1; }
require_root() { test "$(id -u)" = 0 || die 'root required'; }
need() { command -v "$1" >/dev/null 2>&1 || die "missing $1"; }
mem_available() { awk '/^MemAvailable:/ {print $2;exit}' /proc/meminfo; }
swap_used() { awk '/^SwapTotal:/ {t=$2} /^SwapFree:/ {f=$2} END {print t-f}' /proc/meminfo; }
baseline_ids() { local n; for n in "${BASELINE_CONTAINERS[@]}"; do docker inspect -f '{{.Id}}' "$n"; done; }
original_healthy() {
  local n code
  for n in "${BASELINE_CONTAINERS[@]}"; do
    test "$(docker inspect -f '{{.State.Running}}' "$n" 2>/dev/null)" = true || die "original $n not running"
  done
  code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18003/xiaozhi/ota/ 2>/dev/null || true)"
  test "$code" = 200 || die "original A03 OTA GET status $code"
  code="$(curl --noproxy '*' -sS -o /dev/null -w '%{http_code}' --max-time 4 http://127.0.0.1:18080/ 2>/dev/null || true)"
  test "$code" = 403 || die "original A04 default-deny changed; HTTP $code"
}
resources_pre() {
  local total avail disk
  total="$(awk '/^MemTotal:/ {print $2;exit}' /proc/meminfo)"
  avail="$(mem_available)"
  disk="$(df -Pk /opt | awk 'NR==2 {print $4}')"
  test "$total" -ge 3400000 || die 'physical RAM below protected 3.4M KiB guard'
  test "$avail" -ge 1400000 || die 'less than ~1.34GiB available; do not deploy'
  test "$disk" -ge 5242880 || die 'less than 5 GiB available disk'
}
resource_guard() {
  local now was
  test "$(mem_available)" -ge 1100000 || die 'MemAvailable below ~1.05GiB after pilot; STOP'
  now="$(swap_used)"; was="$(cat "$ROOT/.baseline-swap")"
  test "$((now-was))" -le 65536 || die 'Swap rose >64 MiB during pilot; STOP'
}
preflight() {
  require_root
  for cmd in docker curl awk df python3 openssl grep; do need "$cmd"; done
  test -r "$SOURCE/deploy/ai/a09-lite/docker-compose.yml" || die 'reviewed source missing'
  test -r "$SOURCE/deploy/ai/a09-lite/Caddyfile.in" || die 'reviewed Caddy template missing'
  test -r "$SOURCE/tools/ai/a09_lite.py" || die 'reviewed stdlib adapter missing'
  docker info >/dev/null 2>&1 || die 'Docker daemon not available'
  docker compose version >/dev/null 2>&1 || die 'Docker Compose not available'
  test "$(uname -m)" = x86_64 || die 'pinned images expected x86_64'
  local major
  major="$(docker version --format '{{.Server.Version}}' | cut -d. -f1)"
  [[ "$major" =~ ^[0-9]+$ ]] && test "$major" -ge 28 || die 'Docker Engine 28+ required'
  docker network inspect s3-voice-ai_default >/dev/null || die 'original A03 network missing'
  docker network inspect s3-voice-ai-edge_front >/dev/null || die 'original A04 front network missing'
  original_healthy
  resources_pre
  test ! -e "$ROOT" && test ! -L "$ROOT" || die 'A09-Lite already staged; status/stop only; do not overwrite'
  local n
  for n in s3-voice-a09-lite-adapter s3-voice-a09-lite-gateway; do
    ! docker inspect "$n" >/dev/null 2>&1 || die "container name already exists: $n"
  done
  msg PREFLIGHT_PASS 'read-only; original 4B/A03/A04 running and isolated networks present; no images or files changed'
}
image_digest() {
  local img="$1" repo="${1%%:*}" digest
  # Image may already be on disk after an interrupted iPhone/SSH pilot.
  # Only trust locally cached images when Docker reports an immutable repo digest.
  digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$img" 2>/dev/null | grep -F "${repo}@sha256:" | head -n 1 || true)"
  if [[ "$digest" == "${repo}@sha256:"* ]]; then
    msg IMAGE_CACHED 'verified local Python image digest; skipping network pull' >&2
  else
    msg IMAGE_PULL 'no verified local digest; pulling Python image (progress visible)' >&2
    docker pull "$img" >&2 || die 'official Python image pull failed'
    digest="$(docker image inspect --format '{{range .RepoDigests}}{{println .}}{{end}}' "$img" | grep -F "${repo}@sha256:" | head -n 1 || true)"
    [[ "$digest" == "${repo}@sha256:"* ]] || die 'immutable Python digest unavailable'
  fi
  printf '%s' "$digest"
}
stop_new_on_error() {
  local rc="$1"
  if test "$rc" -ne 0 && test -r "$ENVFILE"; then
    comp stop gateway adapter >/dev/null 2>&1 || true
    msg PILOT_STOPPED 'only two new A09-Lite containers stopped; private files kept'
  fi
}
# Checks a real Caddy default deny and activation/WS pre-bind gate over Docker DNS.
local_probe() {
  # Compose reports Started before Caddy's socket is ready; do not false-trip.
  local attempt
  for attempt in $(seq 1 40); do
    if docker exec s3-voice-a09-lite-adapter python -I -c '
import urllib.request,urllib.error
url="http://gateway:8080/"
try:
    urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=3)
    raise SystemExit("A09_P2_GATE_FAIL: default route exposed")
except urllib.error.HTTPError as e:
    assert e.code==403,e.code
' >/dev/null 2>&1; then
      msg GATE_PASS 'separate Caddy default deny 403'
      return 0
    fi
    sleep 1
  done
  return 1
}
install_pilot() {
  preflight
  local original_ids python_image caddy_image secret
  original_ids="$(baseline_ids)"
  # No new Caddy image: use the running official A04 gateway exact image ID.
  caddy_image="$(docker inspect -f '{{.Image}}' s3-voice-ai-gateway)"
  docker image inspect "$caddy_image" >/dev/null || die 'original Caddy image missing locally'
  python_image="$(image_digest "$PYTHON_TAG")"
  msg INSTALL_STAGE 'Python image ready; checking original container identity' >&2
  resources_pre
  test "$(baseline_ids)" = "$original_ids" || die 'original container changed during image resolution'
  test ! -e "$ROOT" && test ! -L "$ROOT" || die 'A09-Lite directory unexpectedly appeared'
  # Use the external coreutils executable explicitly; do not recurse into the installer.
  command install -d -m 0700 "$ROOT" "$ROOT/data"
  chown 10001:10001 "$ROOT/data"
  printf '%s\n' "$(swap_used)" > "$ROOT/.baseline-swap"
  cp "$SOURCE/deploy/ai/a09-lite/docker-compose.yml" "$COMPOSE"
  cp "$SOURCE/tools/ai/a09_lite.py" "$ROOT/a09_lite.py"
  chmod 0600 "$COMPOSE"; chmod 0644 "$ROOT/a09_lite.py"
  secret="$(openssl rand -hex 32)"
  python3 - "$SOURCE/deploy/ai/a09-lite/Caddyfile.in" "$ROOT/Caddyfile" "$secret" <<'PY'
from pathlib import Path
import sys
src = Path(sys.argv[1]).read_text()
assert src.count('__IOS_SECRET__')==3
Path(sys.argv[2]).write_text(src.replace('__IOS_SECRET__',sys.argv[3]))
PY
  chmod 0444 "$ROOT/Caddyfile"
  {
    printf 'PYTHON_IMAGE=%s\nCADDY_IMAGE=%s\n' "$python_image" "$caddy_image"
    printf 'IOS_HOSTNAME=%s\nIOS_SECRET=%s\n' "$IOS_HOSTNAME" "$secret"
  } > "$ENVFILE"
  chmod 0600 "$ENVFILE"
  unset secret
  trap 'stop_new_on_error "$?"' EXIT
  comp config --quiet || die 'Compose rejected isolated configuration'
  # One-time DB initialization as uid 10001; writes ONLY new ./data bind mount.
  comp run --rm --no-deps adapter python -I /app/a09_lite.py --db /var/lib/s3-voice-a09-lite/activation.sqlite3 init >/dev/null || die 'SQLite init failed'
  resource_guard
  comp up -d --no-build adapter gateway >/dev/null || die 'isolated gateway startup failed'
  local_probe || die 'Caddy default-deny failed'
  resource_guard
  test "$(baseline_ids)" = "$original_ids" || die 'original 4B container IDs changed'
  original_healthy
  trap - EXIT
  msg PILOT_PASS 'A09-Lite adapter+gateway isolated; no original service restart or new host port'
  msg PUBLIC_NOT_READY 'Cloudflare hostname NOT configured by this script; only owner can add separate published route'
}
status() {
  require_root
  test -r "$ENVFILE" || die 'A09-Lite not installed'
  comp ps
  original_healthy
  pending
  msg STATUS 'original 4B OTA and default deny pass; real iPhone not tested'
}
# Read-only SQLite summary for owner: no codes, MACs, Client-Ids or secrets.
# The active count is authoritative for codes generated by THIS A09-Lite.
pending() {
  require_root
  test -r "$ENVFILE" || die 'A09-Lite not installed'
  test "$(docker inspect -f '{{.State.Running}}' s3-voice-a09-lite-adapter 2>/dev/null)" = true || die 'A09-Lite adapter not running'
  docker exec -u 10001 s3-voice-a09-lite-adapter python -I -c '
import sqlite3, time
p="file:/var/lib/s3-voice-a09-lite/activation.sqlite3?mode=ro"
with sqlite3.connect(p, uri=True, timeout=5) as db:
    now=int(time.time())
    active=db.execute("SELECT count(*) FROM devices WHERE bound_at IS NULL AND expires_at > ?",(now,)).fetchone()[0]
    expired=db.execute("SELECT count(*) FROM devices WHERE bound_at IS NULL AND expires_at <= ?",(now,)).fetchone()[0]
    approved=db.execute("SELECT count(*) FROM devices WHERE bound_at IS NOT NULL").fetchone()[0]
    print("A09_P2_PENDING_STATUS: active=%d expired=%d approved=%d"%(active,expired,approved))
'
}

approve() {
  require_root
  test -r "$ENVFILE" || die 'not installed'
  test "$(docker inspect -f '{{.State.Running}}' s3-voice-a09-lite-adapter 2>/dev/null)" = true || die 'adapter not running'
  local code
  # The phone terminal may paste the command chain before user interaction.
  # Read from its controlling TTY; show digits so owner can verify input.
  test -r /dev/tty || die 'interactive SSH terminal unavailable; no action taken'
  printf 'Hi Xiaozhi six-digit code (visible): type 6 digits, then press Return: ' >&2
  if ! IFS= read -r code </dev/tty; then
    die 'terminal input ended; run approve as a standalone command'
  fi
  [[ "$code" =~ ^[0-9]{6}$ ]] || die 'terminal did not receive exactly six digits; no action taken'
  # Pass via stdin rather than command args/environment or shell history.
  printf '%s\n' "$code" | docker exec -i -u 10001 s3-voice-a09-lite-adapter python -I /app/a09_lite.py --db /var/lib/s3-voice-a09-lite/activation.sqlite3 approve -
  unset code
}
revoke() {
  require_root
  test -r "$ENVFILE" || die 'not installed'
  test "$#" = 1 || die 'revoke requires an exact MAC device identity'
  [[ "$1" =~ ^([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}$ ]] || die 'invalid device identity'
  docker exec -u 10001 s3-voice-a09-lite-adapter python -I /app/a09_lite.py --db /var/lib/s3-voice-a09-lite/activation.sqlite3 revoke "$1"
}
stop() {
  require_root
  test -r "$ENVFILE" || die 'A09-Lite not installed'
  comp stop gateway adapter >/dev/null
  original_healthy
  msg STOP_PASS 'stopped only A09-Lite; isolated database retained; original 4B unchanged'
}
case "${1:-}" in
  preflight) preflight ;;
  install) install_pilot ;;
  status) status ;;
  pending) pending ;;
  approve) approve ;;
  revoke) test "$#" -eq 2 || die 'revoke <MAC>'; revoke "$2" ;;
  stop) stop ;;
  *) printf 'Usage: sudo bash tools/ai/a09-lite-deploy.sh preflight|install|status|approve|revoke <MAC>|stop\n' >&2; exit 2 ;;
esac