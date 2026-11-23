#!/usr/bin/env python3
"""A07 reversible official XiaoZhi audio pacing trial for in-sentence dropouts.

Uses native v0.9.8 tts_audio_send_delay=60, not an upstream code fork.
Only A03's private YAML changes; restarts A03 only; existing real-4B A04
admission gate is regression-tested. No device flash, no API requests.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

ROOT = Path("/opt/s3-voice-ai")
CFG = ROOT / "data/.config.yaml"
TRIAL = ROOT / "a07-pacing"
STATE = TRIAL / "state.json"
BACKUP = TRIAL / "before.yaml"
IDENTITY = Path("/opt/s3-voice-ai-edge/identity.json")
DELAY_RE = re.compile(r"(?m)^(tts_audio_send_delay:[ \t]*)([0-9]+)([ \t]*(?:#.*)?)$")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def render(original):
    """Preserve all original YAML bytes except the one official top-level setting."""
    if not original.endswith("\n"):
        raise ValueError("config must end in newline")
    matches = list(DELAY_RE.finditer(original))
    if len(matches) > 1:
        raise ValueError("duplicate pacing keys")
    if matches:
        if matches[0].group(2) != "0":
            raise ValueError("existing send delay is not default zero")
        return DELAY_RE.sub(lambda m: m.group(1) + "60" + m.group(3), original, count=1)
    return original + "tts_audio_send_delay: 60\n"


def ensure_baseline():
    if os.geteuid() != 0:
        raise ValueError("requires root Shell")
    if not CFG.is_file() or not IDENTITY.is_file():
        raise ValueError("A03/A04 private baseline missing")
    cfg = CFG.read_text()
    for expected in ("  ASR: VoskASR\n", "  LLM: GenericGPTLLM\n", "  TTS: EdgeTTS\n"):
        if cfg.count(expected) != 1:
            raise ValueError("A05/A06 baseline changed")
    ident = json.loads(IDENTITY.read_text())
    if ident.get("mode") != "hardware":
        raise ValueError("real Waveshare A07 admission not active")
    return cfg


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


def replace_cfg(text):
    temp = CFG.with_name(".config.yaml.a07-pacing-tmp")
    private_write(temp, text)
    os.replace(temp, CFG)
    os.chmod(CFG, 0o600)


def check_live():
    # Device OTA and real-identity OTA+WSS 200/101/403 regressions.
    for attempt in range(50):
        try:
            with urlopen("http://127.0.0.1:18003/xiaozhi/ota/", timeout=2) as f:
                if f.status == 200:
                    break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    else:
        raise ValueError("A03 OTA not healthy after restart")
    test = Path(__file__).resolve().parents[2] / "tests/ai/a04_gateway_smoke.py"
    for _ in range(3):
        r = subprocess.run(["python3", str(test), "--identity", str(IDENTITY),
                            "--origin", "http://127.0.0.1:18080"],
                           capture_output=True, timeout=30)
        if r.returncode == 0:
            return
        time.sleep(1)
    raise ValueError("A04 OTA/WSS admission regression failed")


def restart():
    result = subprocess.run(["docker", "compose", "-p", "s3-voice-ai",
                             "-f", str(ROOT / "docker-compose.yml"),
                             "--env-file", str(ROOT / ".env"),
                             "restart", "server"],
                            capture_output=True, timeout=55)
    if result.returncode:
        raise ValueError("A03-only restart failed")


def apply():
    orig = ensure_baseline()
    if TRIAL.exists():
        raise ValueError("pacing snapshot already exists: use status or rollback")
    candidate = render(orig)
    check_live()
    TRIAL.mkdir(mode=0o700)
    private_write(BACKUP, orig)
    private_write(STATE, json.dumps({"baseline_sha256": sha(orig),
                                     "trial_sha256": sha(candidate), "delay_ms": 60}) + "\n")
    try:
        replace_cfg(candidate)
        restart()
        check_live()
    except Exception:
        # Never mark success if rollback health validation fails.
        replace_cfg(orig)
        restart()
        try:
            check_live()
            print("A07_PACING_ROLLBACK_PASS: trial failed; original config and OTA/WSS verified")
        except Exception:
            print("A07_PACING_RECOVERY_UNVERIFIED: original configuration restored but health failed")
        raise
    print("A07_PACING_OK: official 60ms first-to-last Opus pacing active; A05/A06 and A04 OTA/WSS preserved")
    print("A07_PACING_OK: private original configuration backed up; rollback command available")


def rollback():
    ensure_baseline()
    if not BACKUP.is_file() or not STATE.is_file():
        raise ValueError("no active A07 pacing snapshot")
    state = json.loads(STATE.read_text())
    original = BACKUP.read_text()
    running = CFG.read_text()
    if sha(original) != state.get("baseline_sha256"):
        raise ValueError("baseline snapshot corrupted")
    if sha(running) != state.get("trial_sha256"):
        raise ValueError("running config differs from trial; refuse to overwrite")
    replace_cfg(original)
    restart()
    check_live()
    # Preserve evidence. Never delete private backup of configuration/keys.
    done = TRIAL.with_name("a07-pacing-rolled-back")
    if done.exists():
        raise ValueError("recovery archive exists: original config restored, retain snapshot")
    TRIAL.rename(done)
    print("A07_PACING_ROLLBACK_PASS: default send delay restored and A03/A04 OTA/WSS verified")


def status():
    cfg = ensure_baseline()
    if not TRIAL.is_dir():
        print("A07_PACING_STATUS: no active trial")
        return
    state = json.loads(STATE.read_text())
    if sha(cfg) == state.get("trial_sha256"):
        print("A07_PACING_STATUS: active send_delay=60ms, original backup present")
    elif sha(cfg) == state.get("baseline_sha256"):
        print("A07_PACING_STATUS: baseline restored; snapshot retained")
    else:
        print("A07_PACING_STATUS: configuration drift; do not overwrite until reviewed")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "apply", "rollback"])
    args = ap.parse_args()
    try:
        if args.action == "apply":
            apply()
        elif args.action == "rollback":
            rollback()
        else:
            status()
    except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.TimeoutExpired):
        # Secrets may be in configuration, Docker or HTTP errors. Do not echo them.
        raise SystemExit("A07_PACING_BLOCKED: preflight/apply/rollback failed; private snapshots preserved") from None


if __name__ == "__main__":
    main()
