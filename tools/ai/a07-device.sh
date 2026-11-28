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
gateway_ready() {
  local code=""
  for n in $(seq 1 30); do
    code="$(curl --noproxy '*' -sS --max-time 2 -o /dev/null -w '%{http_code}' http://127.0.0.1:18080/ 2>/dev/null || true)"
    if test "$code" = 403; then return 0; fi
    sleep 1
  done
  printf 'A07_BLOCKED: Caddy did not return HTTP 403 after restart\n' >&2
  return 1
}
gateway_restart() {
  # Docker "Started" happens BEFORE Caddy has finished binding HTTP.
  edge --profile tunnel up -d --no-deps --force-recreate gateway >/dev/null || return 1
  gateway_ready || return 1
}
server_restart() {
  (cd "$A03" && docker compose -p s3-voice-ai restart server >/dev/null)
  ready=0
  for n in $(seq 1 60); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  if test "$ready" != 1; then
    printf 'A07_BLOCKED: original A03 OTA health did not recover; invoking scoped recovery\n' >&2
    return 1
  fi
}
smoke() {
  # The new Caddy process can briefly reset already-open connections.
  # Retry the unchanged official A04 200/101/403 smoke, not the config edits.
  local n
  for n in 1 2 3 4 5; do
    if python3 "$SMOKE" --identity "$IDENTITY" --origin http://127.0.0.1:18080 >/dev/null 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  printf 'A07_BLOCKED: A04 full 200/101/403 admission smoke failed after readiness checks\n' >&2
  return 1
}
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
  # Error recovery is deliberately verified; never claim rollback success if
  # Caddy and XiaoZhi are still unreachable. Do not restart an unchanged server.
  trap - ERR
  local failed=0 changed_caddy=0 changed_config=0
  if test ! -f "$A07/pre-a07.Caddyfile" ||
     test ! -f "$A07/pre-a07.identity.json" ||
     test ! -f "$A07/pre-a07.config.yaml"; then
    printf 'A07_RECOVERY_UNVERIFIED: original private snapshots missing\n' >&2
    return 1
  fi
  if ! cmp -s "$A07/pre-a07.Caddyfile" "$CADDY"; then
    cp "$A07/pre-a07.Caddyfile" "$CADDY" && chmod 444 "$CADDY" || failed=1
    changed_caddy=1
  fi
  cp -p "$A07/pre-a07.identity.json" "$IDENTITY" || failed=1
  if test "$changed_caddy" = 1 && test "$failed" = 0; then
    gateway_restart || failed=1
  fi
  if ! cmp -s "$A07/pre-a07.config.yaml" "$CONFIG"; then
    cp -p "$A07/pre-a07.config.yaml" "$CONFIG" && chmod 600 "$CONFIG" || failed=1
    changed_config=1
  fi
  if test "$changed_config" = 1 && test "$failed" = 0; then
    server_restart || failed=1
  fi
  if test "$failed" = 0 && gateway_ready && smoke; then
    ok "verified: original A04 identity and A05/A06 configuration restored; OTA/WSS 200/101/403 PASS"
    return 0
  fi
  printf 'A07_RECOVERY_UNVERIFIED: inspect A03/A04 status; private snapshots retained\n' >&2
  return 1
}
on_error() {
  code=$?
  trap - ERR
  if restore_original >&2; then
    printf 'A07_BLOCKED: stage/bind error; scoped A03/A04 restore VERIFIED; A07 working directory kept\n' >&2
  else
    printf 'A07_RECOVERY_UNVERIFIED: scoped restore could not be confirmed; do not retry stage\n' >&2
  fi
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
recover() {
  root
  test -f "$STATE" && test -f "$A07/pre-a07.Caddyfile" &&
    test -f "$A07/pre-a07.identity.json" && test -f "$A07/pre-a07.config.yaml" ||
    die "no interrupted A07 state to recover"
  python3 - "$STATE" <<'PY'
import json,sys
a=json.load(open(sys.argv[1]))
assert a.get("mode")=="staged", "A07_RECOVERY_BLOCKED: already bound; use rollback"
PY
  restore_original || die "original A03/A04 not healthy; keeping all snapshots"
  local archived="$A03/a07-aborted-$(date -u '+%Y%m%dT%H%M%SZ')"
  test ! -e "$archived" || die "recovery archive name collision"
  mv "$A07" "$archived" || die "cannot archive previous A07 state; do not overwrite"
  chmod 700 "$archived"
  ok "interrupted stage archived under private /opt/s3-voice-ai; new stage can start from verified original baseline"
}
rollback() {
  root
  test -f "$STATE" && test -f "$A07/pre-a07.Caddyfile" || die "no A07 backup"
  restore_original
  # restore_original itself already runs the complete A04 admission smoke.
  rm -rf "$A07"
  ok "A07 pairing removed after verified restoration"
}
case "$ACTION" in
  status) status ;; preflight) preflight ;; stage) stage ;; recover) recover ;;
  show-url) show_url ;; capture) capture ;; bind) bind ;;
  public) public_probe ;; rollback) rollback ;;
  *) printf 'Usage: a07-device.sh preflight|stage|show-url|capture|bind|public|status|recover|rollback\n' >&2; exit 2 ;;
esac
