#!/usr/bin/env bash
# A07: minimal Caddy-based one-time registration, no firmware flash or extra port.
set -Eeuo pipefail
set +x
umask 077
ACTION=status
if test "$#" -gt 0; then ACTION="$1"; fi
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
A03=/opt/s3-voice-ai
A04=/opt/s3-voice-ai-edge
A07=/opt/s3-voice-ai-a07
CONFIG="$A03/data/.config.yaml"
IDENTITY="$A04/identity.json"
CADDY="$A04/Caddyfile"
STATE="$A07/enroll.json"
COMPOSE="$A04/docker-compose.yml"
TEMPLATE="$SRC/deploy/ai/a04/Caddyfile.in"
SMOKE="$SRC/tests/ai/a04_gateway_smoke.py"

die() { printf 'A07_BLOCKED: %s\n' "$*" >&2; exit 1; }
ok() { printf 'A07_OK: %s\n' "$*"; }
root() { test "$(id -u)" = 0 || die "run in root Shell"; }
edge() { docker compose -p s3-voice-ai-edge -f "$COMPOSE" --env-file "$A04/.env" "$@"; }
gateway_restart() { edge --profile tunnel up -d --no-deps --force-recreate gateway >/dev/null; }
server_restart() {
  (cd "$A03" && docker compose -p s3-voice-ai restart server >/dev/null)
  ready=0
  for n in $(seq 1 60); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  test "$ready" = 1 || die "original A03 OTA health did not recover"
}
smoke() { python3 "$SMOKE" --identity "$IDENTITY" --origin http://127.0.0.1:18080 >/dev/null; }
status() {
  root
  if test ! -f "$STATE"; then
    ok "no A07 pairing staged; original A04 synthetic-only gate unchanged"
    return
  fi
  python3 - "$STATE" <<'PY'
import json,sys
a=json.load(open(sys.argv[1]))
assert a["mode"] in ("staged","active")
print("A07_STATUS: " + ("waiting-for-hardware-OTA" if a["mode"]=="staged" else "real-device-bound"))
print("A07_STATUS: private path secret not displayed")
PY
}
preflight() {
  root
  for cmd in python3 docker curl openssl; do command -v "$cmd" >/dev/null || die "missing $cmd"; done
  test -f "$CONFIG" && test -f "$A03/a05-backup.path" && test -f "$A03/a06-backup.path" ||
    die "A03/A05/A06 accepted configuration missing"
  test -f "$IDENTITY" && test -f "$CADDY" && test -f "$TEMPLATE" || die "A04 baseline missing"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-gateway || die "A04 gateway stopped"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-server || die "A03 server stopped"
  test ! -e "$A07" || die "A07 already staged; use status/capture/bind/rollback"
  python3 - "$IDENTITY" "$CONFIG" "$CADDY" <<'PY'
import json,sys
from pathlib import Path
a=json.loads(Path(sys.argv[1]).read_text())
c=Path(sys.argv[2]).read_text()
f=Path(sys.argv[3]).read_text()
assert a["mode"]=="synthetic","A04 real-device pairing already active"
assert c.count("  ASR: VoskASR\n")==1 and c.count("  TTS: EdgeTTS\n")==1
assert c.count("  LLM: GenericGPTLLM\n")==1
assert c.count("wss://"+a["hostname"]+"/xiaozhi/v1/"+a["pair_secret"])==1
assert a["pair_secret"] in f and a["device_id"] in f and a["client_id"] in f
PY
  smoke
  ok "A04 synthetic ingress, A05 GPT and A06 voice baseline checked; no edits"
}
restore_original() {
  trap - ERR
  if test -f "$A07/pre-a07.Caddyfile"; then
    cp "$A07/pre-a07.Caddyfile" "$CADDY"
    chmod 444 "$CADDY"
    gateway_restart || true
  fi
  if test -f "$A07/pre-a07.identity.json"; then
    cp "$A07/pre-a07.identity.json" "$IDENTITY"
    chmod 600 "$IDENTITY"
  fi
  if test -f "$A07/pre-a07.config.yaml"; then
    cp "$A07/pre-a07.config.yaml" "$CONFIG"
    chmod 600 "$CONFIG"
    server_restart || true
  fi
  ok "original A04 synthetic gate and original A05/A06 config restored"
}
on_error() {
  code=$?
  trap - ERR
  restore_original >&2 || true
  printf 'A07_BLOCKED: stage/bind error; attempted scoped A03/A04 restore; no other services touched\n' >&2
  exit "$code"
}
stage() {
  preflight
  mkdir "$A07"
  chmod 700 "$A07"
  cp -p "$CADDY" "$A07/pre-a07.Caddyfile"
  cp -p "$IDENTITY" "$A07/pre-a07.identity.json"
  cp -p "$CONFIG" "$A07/pre-a07.config.yaml"
  chmod 600 "$A07"/pre-a07.*
  python3 - "$STATE" <<'PY'
import json,secrets,sys
from pathlib import Path
p=Path(sys.argv[1])
p.write_text(json.dumps({"mode":"staged","pair_secret":secrets.token_hex(32)})+"\n")
p.chmod(0o600)
PY
  trap on_error ERR
  python3 "$SRC/tools/ai/a07-pair.py" stage-render \
    --original "$A07/pre-a07.Caddyfile" --state "$STATE" \
    --output "$A07/Caddyfile.staged"
  cp "$A07/Caddyfile.staged" "$CADDY"
  chmod 444 "$CADDY"
  gateway_restart
  smoke
  trap - ERR
  ok "one-time OTA discovery staged; unknown device still receives 403; request paths never logged"
  ok "run 'show-url' privately on VPS and enter that URL on 4B Wi-Fi setup Advanced page"
}
show_url() {
  root
  test -f "$STATE" || die "run stage first"
  python3 - "$STATE" <<'PY'
import json,sys
a=json.load(open(sys.argv[1]))
if a["mode"]!="staged": raise SystemExit("A07_BLOCKED: already bound")
print("A07_PRIVATE_OTA_URL=https://voice.cncloudx.com/xiaozhi/ota/"+a["pair_secret"])
print("Copy privately to 4B setup; NEVER paste this full URL in chat/screenshots.")
PY
}
capture() {
  root
  test -f "$STATE" && test -f "$A07/Caddyfile.staged" || die "A07 not staged"
  test ! -f "$A07/candidate.json" || die "already captured; bind or rollback"
  docker exec s3-voice-ai-gateway cat /config/a07-pair.log > "$A07/capture.jsonl" ||
    die "no real OTA request yet; check firmware's advanced OTA setting"
  chmod 600 "$A07/capture.jsonl"
  python3 "$SRC/tools/ai/a07-pair.py" capture \
    --log "$A07/capture.jsonl" --state "$STATE" --output "$A07/candidate.json"
  rm -f "$A07/capture.jsonl"
  ok "candidate captured into private root-only file; verify it was your device before bind"
}
bind() {
  root
  test -f "$STATE" && test -f "$A07/candidate.json" || die "run stage/show-url/capture first"
  python3 - "$STATE" <<'PY'
import json,sys
if json.load(open(sys.argv[1]))["mode"]!="staged":
    raise SystemExit("A07_BLOCKED: not in staging mode")
PY
  printf 'Did you just configure YOUR Waveshare 4B and observe its OTA retry? Type BIND: '
  IFS= read -r approved
  test "$approved" = BIND || die "owner approval missing, no changes"
  trap on_error ERR
  python3 "$SRC/tools/ai/a07-pair.py" bind-render \
    --template "$TEMPLATE" --synthetic "$A07/pre-a07.identity.json" \
    --candidate "$A07/candidate.json" --state "$STATE" \
    --out-caddy "$A07/Caddyfile.bound" --out-identity "$A07/identity.bound.json" \
    --config "$A07/pre-a07.config.yaml" --out-config "$A07/config.bound.yaml"
  cp "$A07/Caddyfile.bound" "$CADDY"
  chmod 444 "$CADDY"
  cp "$A07/identity.bound.json" "$IDENTITY"
  chmod 600 "$IDENTITY"
  gateway_restart
  cp "$A07/config.bound.yaml" "$CONFIG"
  chmod 600 "$CONFIG"
  server_restart
  smoke
  python3 - "$STATE" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);a=json.loads(p.read_text())
a["mode"]="active"
t=p.with_suffix(".tmp");t.write_text(json.dumps(a)+"\n");t.chmod(0o600);t.replace(p)
PY
  trap - ERR
  ok "strict real 4B identity bound: OTA 200 / WS 101 / deny 403"
  ok "A05 GPT, A06 Vosk/EdgeTTS unchanged; normal 4B reboot can retry OTA"
}
public_probe() {
  root
  test -f "$STATE" || die "A07 not staged"
  python3 - "$STATE" <<'PY'
import json,sys
assert json.load(open(sys.argv[1]))["mode"]=="active","not bound yet"
PY
  python3 "$SMOKE" --identity "$IDENTITY" --origin https://voice.cncloudx.com
  ok "public OTA/WSS admission PASS; real microphone/speaker hardware test still required"
}
rollback() {
  root
  test -f "$STATE" && test -f "$A07/pre-a07.Caddyfile" || die "no A07 backup"
  restore_original
  smoke
  rm -rf "$A07"
  ok "A07 pairing removed; previous stable synthetic identity gate restored"
}
case "$ACTION" in
  status) status ;; preflight) preflight ;; stage) stage ;;
  show-url) show_url ;; capture) capture ;; bind) bind ;;
  public) public_probe ;; rollback) rollback ;;
  *) printf 'Usage: a07-device.sh preflight|stage|show-url|capture|bind|public|status|rollback\n' >&2; exit 2 ;;
esac
