#!/usr/bin/env python3
"""A07 one-shot, fail-closed, native 60ms Opus pacing on the existing A03.

Never changes LLM credentials, Access, Caddy, WebUI or device firmware.
Downloads hash-pinned helpers and uses their exact-byte backup/rollback.
"""
import argparse
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

SOURCE_COMMIT = "2ed2cd2c7f543140e60b182f41080899b4a9bc6e"
REPO = "Jackyhuang83/s3-voice-4b-proxy"
BLOBS = {
    "tools/ai/a07-audio-pacing.py": "8c8f8238ed4db20d7e0a6024a406deb1561c5fa5",
    "tests/ai/a04_gateway_smoke.py": "d550a142605a663a61659cab6d37ecc77f5fde26",
}
PROTECTED = (
    "s3-voice-ai-gateway", "s3-voice-ai-tunnel",
    "s3-voice-webui-gateway", "s3-voice-webui-auth",
)
ROOT = Path("/opt/s3-voice-ai")
LOCK = ROOT / ".a07-voice-once.lock"


class SafeStop(Exception):
    """Sanitized guard error; must never include private values."""


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def fetch_pinned():
    result = {}
    for path, expected in BLOBS.items():
        url = f"https://raw.githubusercontent.com/{REPO}/{SOURCE_COMMIT}/{path}"
        req = urllib.request.Request(url, headers={"User-Agent": "S3-Voice-A07-Pinned-Release/1"})
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status != 200:
                raise SafeStop("PINNED_SOURCE_DOWNLOAD_FAILED")
            data = response.read(120001)
        if not (0 < len(data) <= 120000) or git_blob(data) != expected:
            raise SafeStop("PINNED_SOURCE_HASH_MISMATCH")
        result[path] = data
    return result


def protected_fingerprint():
    result = {}
    for name in PROTECTED:
        proc = subprocess.run(
            ["docker", "inspect", "--format",
             "{{.Id}}|{{.State.StartedAt}}|{{.State.Running}}", name],
            capture_output=True, timeout=15, check=False,
        )
        if proc.returncode:
            raise SafeStop("PROTECTED_CONTAINER_UNAVAILABLE")
        parts = proc.stdout.strip().split(b"|")
        if len(parts) != 3 or parts[2] != b"true" or not all(parts[:2]):
            raise SafeStop("PROTECTED_CONTAINER_NOT_RUNNING")
        result[name] = tuple(parts[:2])
    return result


def helper_call(root, action):
    helper = root / "tools/ai/a07-audio-pacing.py"
    proc = subprocess.run([sys.executable, str(helper), action],
                          capture_output=True, timeout=230, check=False)
    if proc.returncode:
        # Never emit stderr/stdout from commands running near private API keys.
        raise SafeStop("PACING_HELPER_" + action.upper() + "_BLOCKED")
    return proc.stdout.decode("utf-8", "replace")


def status_kind(stdout):
    if "A07_PACING_ENGINE_PASS:" not in stdout:
        raise SafeStop("RUNTIME_OPUS_ENGINE_NOT_VERIFIED")
    statuses = {
        "no active trial": "baseline",
        "active send_delay=60ms, original backup present": "active",
        "baseline restored; snapshot retained": "restored",
        "configuration drift; do not overwrite until reviewed": "drift",
    }
    hits = [key for phrase, key in statuses.items() if ("A07_PACING_STATUS: " + phrase) in stdout]
    if len(hits) != 1:
        raise SafeStop("PACING_STATE_UNKNOWN")
    return hits[0]


def release(mode="apply"):
    if os.geteuid() != 0 or not ROOT.is_dir() or ROOT.is_symlink():
        raise SafeStop("ROOT_OR_BASELINE_MISSING")
    if LOCK.is_symlink():
        raise SafeStop("LOCK_SYMLINK_BLOCKED")
    lock_fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        source = fetch_pinned()
        print("A07_VOICE_PINNED_SOURCE_PASS", flush=True)
        with tempfile.TemporaryDirectory(prefix="s3-voice-a07-", dir="/tmp") as folder:
            root = Path(folder)
            for path, data in source.items():
                dest = root / path
                dest.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
            before = protected_fingerprint()
            initial = status_kind(helper_call(root, "status"))
            print("A07_VOICE_RUNTIME_PREFLIGHT_PASS", flush=True)
            if mode == "rollback":
                if initial != "active":
                    raise SafeStop("ROLLBACK_REQUIRES_ACTIVE_TRIAL")
                helper_call(root, "rollback")
                after = status_kind(helper_call(root, "status"))
                if after != "baseline":
                    raise SafeStop("ROLLBACK_STATE_UNEXPECTED")
                if protected_fingerprint() != before:
                    raise SafeStop("PROTECTED_CONTAINERS_CHANGED")
                print("A07_VOICE_ROLLBACK_AND_OTA_WSS_PASS", flush=True)
                return
            if initial == "active":
                print("A07_VOICE_PACING_ALREADY_ACTIVE_PASS", flush=True)
                print("A07_VOICE_REAL_4B_PLAYBACK_UNVERIFIED", flush=True)
                return
            if initial != "baseline":
                raise SafeStop("PREVIOUS_TRIAL_REQUIRES_REVIEW")
            print("A07_VOICE_PRODUCTION_BASELINE_PASS", flush=True)
            applied = False
            try:
                helper_call(root, "apply")
                applied = True
                final = status_kind(helper_call(root, "status"))
                if final != "active":
                    raise SafeStop("PACING_NOT_ACTIVE_AFTER_APPLY")
                if protected_fingerprint() != before:
                    raise SafeStop("PROTECTED_CONTAINERS_CHANGED")
            except (SafeStop, OSError, subprocess.TimeoutExpired):
                # The A07 helper already restores on an apply failure. If it
                # returned success but a *post*-check fails, roll back once.
                if applied:
                    try:
                        helper_call(root, "rollback")
                        print("A07_VOICE_POSTCHECK_ROLLBACK_PASS", flush=True)
                    except (SafeStop, OSError, subprocess.TimeoutExpired):
                        print("A07_VOICE_RECOVERY_UNVERIFIED", flush=True)
                raise
            print("A07_VOICE_PACING_60MS_ACTIVE_PASS", flush=True)
            print("A07_VOICE_A04_OTA_WSS_AND_WEBUI_UNCHANGED_PASS", flush=True)
            print("A07_VOICE_REAL_4B_PLAYBACK_UNVERIFIED", flush=True)
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description="Safe A07 one-shot 4B server audio pacing")
    parser.add_argument("action", nargs="?", choices=("apply", "rollback"), default="apply")
    args = parser.parse_args()
    try:
        release(args.action)
    except (SafeStop, OSError, ValueError, subprocess.TimeoutExpired, BlockingIOError):
        print("A07_VOICE_BLOCKED: configuration not accepted; check private A07 backup, do not repeat blindly", flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
