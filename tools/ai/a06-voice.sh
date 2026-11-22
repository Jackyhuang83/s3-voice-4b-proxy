#!/usr/bin/env bash
# A06: reuse upstream VoskASR Chinese small model + existing EdgeTTS.
# Exactly one isolated A03 config switch; A04 tunnel and A05 GPT remain intact.
set -Eeuo pipefail
set +x
umask 077
export LC_ALL=C
ACTION=preflight
if test "$#" -gt 0; then ACTION="$1"; fi
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT=/opt/s3-voice-ai
EDGE=/opt/s3-voice-ai-edge
CONFIG="$ROOT/data/.config.yaml"
MODEL="$ROOT/data/models/vosk/vosk-model-small-cn-0.22"
MODEL_URL=https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
STATE="$ROOT/a06-backup.path"
BACKUP_DIR=/var/backups/s3-voice-ai
CONTRACT="$ROOT/data/.a06-voice-contract.tmp.py"
LOCAL_BACKUP=""

die() { printf 'A06_BLOCKED: %s\n' "$*" >&2; exit 1; }
ok() { printf 'A06_OK: %s\n' "$*"; }
root() { test "$(id -u)" = 0 || die "root shell required"; }
gateway_test() {
  python3 "$SRC/tests/ai/a04_gateway_smoke.py" --identity "$EDGE/identity.json" \
    --origin http://127.0.0.1:18080 >/dev/null || die "A04 OTA/WSS regression detected"
}
wait_ota() {
  local ready=0
  for n in $(seq 1 60); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  test "$ready" = 1 || die "A03 server OTA not healthy"
}
restart_server() {
  (cd "$ROOT" && docker compose -p s3-voice-ai restart server >/dev/null)
  wait_ota
}
preflight() {
  root
  for c in docker python3 curl df; do command -v "$c" >/dev/null || die "missing $c"; done
  test -f "$CONFIG" && test -f "$ROOT/.env" || die "A03 install missing"
  test -f "$ROOT/a05-backup.path" || die "A05 live generic API not accepted yet"
  test -f "$EDGE/identity.json" || die "A04 identity gate missing"
  test ! -f "$STATE" || die "A06 already activated; use status or rollback"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-server || die "A03 server not running"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-gateway || die "A04 gateway not running"
  python3 "$SRC/tools/ai/a06-config.py" status --config "$CONFIG"
  python3 - "$CONFIG" "$SRC/tools/ai/a06-config.py" <<'PY'
import importlib.util,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location("a06conf",sys.argv[2])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
try: m.transform(Path(sys.argv[1]).read_text())
except ValueError: sys.exit("A06_BLOCKED: unexpected current A05 baseline; no config modified")
PY
  wait_ota
  gateway_test
  ok "A03/A04/A05 live baseline checked; no service modified"
}
prepare() {
  preflight
  if test -f "$MODEL/am/final.mdl" && test -f "$MODEL/conf/model.conf"; then
    ok "official Vosk Chinese small model already present; no download needed"
    return
  fi
  test ! -e "$MODEL" || die "partial Vosk model directory exists; investigate before retry"
  free_kib="$(df -Pk "$ROOT" | awk 'NR==2{print $4}')"
  test "$free_kib" -gt 1048576 || die "less than 1 GiB disk available"
  mkdir -p "$ROOT/data/models/vosk"
  chmod 700 "$ROOT/data/models" "$ROOT/data/models/vosk"
  temp="$(mktemp -d "$ROOT/data/models/vosk/.a06-download-XXXXXX")"
  trap 'rm -rf "$temp"' EXIT
  curl -fsSL --retry 2 --connect-timeout 15 --max-time 180 \
    "$MODEL_URL" -o "$temp/model.zip" || die "official Vosk model download failed (no config changed)"
  python3 - "$temp/model.zip" "$temp" <<'PY'
import sys,zipfile
from pathlib import Path
z=zipfile.ZipFile(sys.argv[1])
entries=z.infolist()
root="vosk-model-small-cn-0.22/"
assert entries and sum(e.file_size for e in entries) < 220*1024*1024,"unexpected large model"
assert all(e.filename.startswith(root) and ".." not in Path(e.filename).parts for e in entries),"unexpected model archive structure"
z.extractall(sys.argv[2])
PY
  test -f "$temp/vosk-model-small-cn-0.22/am/final.mdl" || die "downloaded model lacks official acoustic weights"
  test -f "$temp/vosk-model-small-cn-0.22/conf/model.conf" || die "downloaded model lacks official config"
  mv "$temp/vosk-model-small-cn-0.22" "$MODEL"
  ok "official Apache-2.0 Vosk Chinese 0.22 small model installed in private A03 data mount"
}
test_voice() {
  root
  test -f "$MODEL/am/final.mdl" || die "run prepare first"
  test ! -f "$CONTRACT" || die "leftover A06 script; inspect before retry"
  cp "$SRC/tests/ai/a06_voice_contract.py" "$CONTRACT"
  chmod 600 "$CONTRACT"
  trap 'rm -f "$CONTRACT"' EXIT
  docker exec -e PYTHONPATH=/opt/xiaozhi-esp32-server -w /opt/xiaozhi-esp32-server \
    s3-voice-ai-server python3 data/.a06-voice-contract.tmp.py real ||
      die "ASR or live EdgeTTS integration failed; A05 configuration unchanged"
  rm -f "$CONTRACT"
  trap - EXIT
  ok "upstream Vosk speech recognition + EdgeTTS Chinese audio roundtrip PASS"
}
restore_on_error() {
  local code=$?
  trap - ERR
  if test -n "$LOCAL_BACKUP" && test -f "$LOCAL_BACKUP"; then
    cp -p "$LOCAL_BACKUP" "$CONFIG" || true
    restart_server || true
    printf 'A06_BLOCKED: restored prior A05 GPT/A04 gateway configuration\n' >&2
  fi
  exit "$code"
}
activate() {
  prepare
  test_voice
  mkdir -p "$BACKUP_DIR"
  chmod 700 "$BACKUP_DIR"
  LOCAL_BACKUP="$BACKUP_DIR/a06-before-$(date -u '+%Y%m%dT%H%M%SZ').yaml"
  test ! -e "$LOCAL_BACKUP" || die "backup timestamp collision"
  cp -p "$CONFIG" "$LOCAL_BACKUP"
  chmod 600 "$LOCAL_BACKUP"
  trap restore_on_error ERR
  python3 "$SRC/tools/ai/a06-config.py" apply --config "$CONFIG"
  # Official upstream config loader merges unchanged EdgeTTS default config.
  docker exec -e PYTHONPATH=/opt/xiaozhi-esp32-server -w /opt/xiaozhi-esp32-server \
    s3-voice-ai-server python3 -c "import yaml; x=yaml.safe_load(open('data/.config.yaml')); assert x['selected_module']['ASR']=='VoskASR' and x['selected_module']['TTS']=='EdgeTTS' and x['selected_module']['LLM']=='GenericGPTLLM' and x['ASR']['VoskASR']['model_path']=='data/models/vosk/vosk-model-small-cn-0.22'" >/dev/null
  restart_server
  gateway_test
  printf '%s\n' "$LOCAL_BACKUP" > "$STATE"
  chmod 600 "$STATE"
  LOCAL_BACKUP=""
  trap - ERR
  ok "official VoskASR + EdgeTTS active; A05 generic GPT preserved; A04 OTA/WSS PASS"
  ok "one-command rollback available; no other VPS services altered"
}
status() {
  root
  test -f "$CONFIG" || die "A03 missing"
  python3 "$SRC/tools/ai/a06-config.py" status --config "$CONFIG"
  test ! -f "$STATE" || ok "A06 private pre-change backup present"
}
rollback() {
  root
  test -f "$STATE" || die "A06 not activated; nothing to restore"
  previous="$(cat "$STATE")"
  case "$previous" in /var/backups/s3-voice-ai/a06-before-*.yaml) ;; *) die "unrecognized backup path";; esac
  test -f "$previous" || die "A06 backup missing"
  cp -p "$previous" "$CONFIG"
  chmod 600 "$CONFIG"
  restart_server
  gateway_test
  rm -f "$STATE"
  ok "restored A05 GenericGPTLLM and prior ASR, A04 WSS preserved; official downloaded model left on disk"
}
case "$ACTION" in
  preflight) preflight ;;
  prepare) prepare ;;
  test) test_voice ;;
  activate) activate ;;
  status) status ;;
  rollback) rollback ;;
  *) printf 'Usage: a06-voice.sh preflight|prepare|test|activate|status|rollback\n'; exit 2 ;;
esac
