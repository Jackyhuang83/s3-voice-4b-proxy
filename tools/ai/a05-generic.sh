#!/usr/bin/env bash
# A05: one generic OpenAI-compatible LLM, reuse official XiaoZhi v0.9.8 adapter.
# No credentials? Use 'preflight' or 'status'. No paid request until explicit consent.
set -Eeuo pipefail
umask 077
set +x
ACTION=preflight
if test "$#" -gt 0; then ACTION="$1"; fi
SRC="$(cd "$(dirname "$0")/../.." && pwd)"
ROOT=/opt/s3-voice-ai
EDGE=/opt/s3-voice-ai-edge
CONFIG="$ROOT/data/.config.yaml"
BACKUP_ROOT=/var/backups/s3-voice-ai
STATE="$ROOT/a05-backup.path"
CRED="$ROOT/data/.a05-credential.tmp.json"
PROVIDER="$ROOT/data/.a05-provider-smoke.tmp.py"
LOCAL_BACKUP=""

die() { printf 'A05_BLOCKED: %s\n' "$*" >&2; exit 1; }
ok() { printf 'A05_OK: %s\n' "$*"; }
require_root() { test "$(id -u)" = 0 || die "root Shell required"; }
cleanup() { rm -f "$CRED" "$PROVIDER"; }
wait_ota() {
  local ready=0
  for n in $(seq 1 45); do
    if curl --noproxy '*' -fsS --max-time 2 http://127.0.0.1:18003/xiaozhi/ota/ >/dev/null 2>&1; then ready=1; break; fi
    sleep 1
  done
  test "$ready" = 1 || die "A03 did not become healthy after local restart"
}
restart_a03() {
  (cd "$ROOT" && docker compose -p s3-voice-ai restart server >/dev/null)
  wait_ota
}
preflight() {
  require_root
  command -v python3 >/dev/null || die "missing python3"
  command -v docker >/dev/null || die "missing Docker"
  test -f "$CONFIG" && test -f "$ROOT/.env" || die "A03 install missing"
  test -f "$EDGE/identity.json" && test -f "$EDGE/.env" || die "A04 gateway not installed"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-server || die "A03 container not running"
  docker ps --format '{{.Names}}' | grep -Fxq s3-voice-ai-gateway || die "A04 gateway not running"
  test ! -e "$STATE" || die "A05 already configured; use status or rollback"
  python3 "$SRC/tools/ai/a05-config.py" audit --config "$CONFIG"
  bash "$SRC/tools/ai/a04-edge.sh" local >/dev/null
  ok "A03 + A04 local OTA/WSS checks PASS; no API credentials needed for preflight"
}

rollback_on_error() {
  code=$?
  trap - ERR
  if test -n "$LOCAL_BACKUP" && test -f "$LOCAL_BACKUP"; then
    cp -p "$LOCAL_BACKUP" "$CONFIG" || true
    restart_a03 || true
    printf 'A05_BLOCKED: original A03/A04 LLM config restored after failed activation\n' >&2
  fi
  exit "$code"
}

activate() {
  preflight
  test ! -e "$CRED" && test ! -e "$PROVIDER" || die "unexpected provider temp file; investigate before retry"
  printf 'OpenAI-compatible HTTPS base URL (e.g. https://provider.example/v1): '
  IFS= read -r base_url
  printf 'Provider model ID: '
  IFS= read -r model_name
  printf 'Provider API key (input hidden): ' >&2
  IFS= read -r -s key
  printf '\n' >&2
  trap cleanup EXIT
  printf '%s' "$key" | python3 "$SRC/tools/ai/a05-config.py" credentials \
    --output "$CRED" --base-url "$base_url" --model "$model_name" || die "invalid provider parameters"
  unset key
  printf 'One short LIVE API call may incur provider charges. Type YES to verify: '
  IFS= read -r consent
  test "$consent" = YES || die "not authorized to make a paid API request; no server changes made"
  cp "$SRC/tests/ai/a05_provider_contract.py" "$PROVIDER"
  chmod 600 "$PROVIDER"
  docker exec -w /opt/xiaozhi-esp32-server s3-voice-ai-server \
    python3 data/.a05-provider-smoke.tmp.py live \
    --credentials data/.a05-credential.tmp.json || die "real upstream streaming call failed; original config left untouched"

  mkdir -p "$BACKUP_ROOT"
  chmod 700 "$BACKUP_ROOT"
  LOCAL_BACKUP="$BACKUP_ROOT/a05-before-$(date -u '+%Y%m%dT%H%M%SZ').yaml"
  test ! -e "$LOCAL_BACKUP" || die "backup filename collision"
  cp -p "$CONFIG" "$LOCAL_BACKUP"
  chmod 600 "$LOCAL_BACKUP"
  trap rollback_on_error ERR
  python3 "$SRC/tools/ai/a05-config.py" apply --config "$CONFIG" --credentials "$CRED"
  restart_a03
  bash "$SRC/tools/ai/a04-edge.sh" local >/dev/null
  printf '%s\n' "$LOCAL_BACKUP" > "$STATE"
  chmod 600 "$STATE"
  LOCAL_BACKUP=""
  trap - ERR
  ok "generic OpenAI-compatible LLM activated; upstream provider live stream and A04 local ingress PASS"
  ok "original A03/A04 config backed up; use rollback to return to previous model"
}

status() {
  require_root
  test -f "$CONFIG" || die "A03 missing"
  python3 "$SRC/tools/ai/a05-config.py" audit --config "$CONFIG"
  if test -f "$STATE"; then ok "backup available for scoped A05 rollback"; fi
}
rollback() {
  require_root
  test -f "$STATE" || die "A05 was not activated; nothing to roll back"
  old="$(cat "$STATE")"
  case "$old" in /var/backups/s3-voice-ai/a05-before-*.yaml) ;; *) die "unexpected backup path";; esac
  test -f "$old" || die "A05 original config backup missing"
  cp -p "$old" "$CONFIG"
  chmod 600 "$CONFIG"
  restart_a03
  bash "$SRC/tools/ai/a04-edge.sh" local >/dev/null || die "restored A04 route failed local smoke"
  rm -f "$STATE"
  ok "original A03/A04 config restored; A05 model disconnected; other services untouched"
}

case "$ACTION" in
  preflight) preflight ;;
  activate) activate ;;
  status) status ;;
  rollback) rollback ;;
  *) printf 'Usage: a05-generic.sh preflight|activate|status|rollback\n'; exit 2 ;;
esac
