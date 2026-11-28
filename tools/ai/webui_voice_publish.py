#!/usr/bin/env python3
"""P2 WebUI browser-voice *single-file* publisher; never touches the 4B stack.

Works only on an already-running, read-only-mounted WebUI v3 installation.
No container restart, no Caddy/Cloudflare change, no model API calls.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import urllib.request

REPO = "Jackyhuang83/s3-voice-4b-proxy"
SOURCE_COMMIT = "9daabddb90f817c3ad4f418089f07f85dd1e5588"
FILE_NAME = "audio-ui.mjs"
BEFORE_BLOB = "65d2dfc95000f84c67d6b121955cf9801dc1400a"
AFTER_BLOB = "f8bf11ca3a852b1474dd827c250d2b654ade53a5"
BASE = Path("/opt/s3-voice-webui")
SRC = BASE / "src"
VOICE = SRC / "webui" / FILE_NAME
PRIVATE = BASE / "private"
BACKUPS = PRIVATE / "backups"
LOCK = PRIVATE / "webui-voice-release.lock"
CONTAINERS = (
    "s3-voice-ai-server", "s3-voice-ai-gateway",
    "s3-voice-webui-auth", "s3-voice-webui-gateway",
)
GUARDS = (
    "webui/index.html", "webui/app.js", "webui/app.css",
    "webui/audio-opus.mjs", "webui/audio-worklet.js",
    "webui/vendor/libopus/dist/index.js",
    "webui/vendor/libopus/dist/generated/libopus.generated.mjs",
    "tools/ai/webui_auth.py", "tools/ai/webui_text.py",
    "deploy/ai/webui/Caddyfile.isolated",
)


class Blocked(Exception):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def execute(argv, payload=None, timeout=30):
    proc = subprocess.run(argv, input=payload, capture_output=True, timeout=timeout)
    if proc.returncode:
        raise Blocked("RUNTIME_COMMAND_FAILED")
    return proc.stdout


def safe_paths():
    if os.geteuid() != 0:
        raise Blocked("ROOT_REQUIRED")
    for path in (BASE, SRC, SRC / "webui", PRIVATE):
        if not path.is_dir() or path.is_symlink():
            raise Blocked("UNEXPECTED_DIRECTORY")
    if not VOICE.is_file() or VOICE.is_symlink() or LOCK.is_symlink():
        raise Blocked("UNEXPECTED_VOICE_FILE")
    for relative in GUARDS:
        path = SRC / relative
        if not path.is_file() or path.is_symlink():
            raise Blocked("PROTECTED_SOURCE_MISSING")
    html = (SRC / "webui/index.html").read_text()
    if 'id="voiceButton"' not in html or '/webui/audio-ui.mjs' not in html:
        raise Blocked("VOICE_UI_BASELINE_MISSING")
    if BACKUPS.exists() and (not BACKUPS.is_dir() or BACKUPS.is_symlink()):
        raise Blocked("BACKUPS_UNSAFE")


def container_states():
    found = {}
    for name in CONTAINERS:
        raw = execute(["docker", "inspect", name], timeout=15)
        item = json.loads(raw)[0]
        if not item["State"]["Running"]:
            raise Blocked("CONTAINER_STOPPED")
        found[name] = (item["Id"], item["State"]["StartedAt"])
        if name == "s3-voice-webui-auth":
            if not any(m["Source"] == str(SRC) and m["Destination"] == "/project"
                       and m["RW"] is False for m in item.get("Mounts", [])):
                raise Blocked("AUTH_READONLY_BIND_MISSING")
        if name.startswith("s3-voice-webui-") and item["HostConfig"].get("PortBindings"):
            raise Blocked("WEBUI_EXPOSED_HOST_PORT")
    return found


def guarded_hashes():
    return {relative: digest((SRC / relative).read_bytes()) for relative in GUARDS}


def routes():
    # Reuse the already deployed Python Auth container to query only the local
    # isolated WebUI gateway. Never use the device A04 gateway or public DNS.
    code = r'''
import hashlib, http.client, json
paths=("/webui/", "/webui/app.js", "/webui/audio-ui.mjs",
       "/webui/api/session", "/webui/api/models", "/webui/ws")
out={}
for path in paths:
    c=http.client.HTTPConnection("s3-voice-webui-gateway",8080,timeout=5)
    try:
        c.request("GET",path)
        r=c.getresponse()
        data=r.read(120000)
        out[path]=[r.status,hashlib.sha256(data).hexdigest(),
                   r.getheader("Content-Type","")]
    finally:
        c.close()
print(json.dumps(out,sort_keys=True))
'''
    out = execute(["docker", "exec", "-i", "s3-voice-webui-auth",
                   "python3", "-B", "-"], code.encode(), timeout=42)
    return json.loads(out)


def verify_routes(expected_voice_sha):
    paths = routes()
    expected = {
        "/webui/": 200, "/webui/app.js": 200,
        "/webui/audio-ui.mjs": 200, "/webui/api/session": 200,
        "/webui/api/models": 401, "/webui/ws": 403,
    }
    if any(paths.get(name, [None])[0] != code for name, code in expected.items()):
        raise Blocked("WEBUI_ROUTE_CONTRACT_FAILED")
    if paths["/webui/audio-ui.mjs"][1] != expected_voice_sha:
        raise Blocked("VOICE_STATIC_CONTENT_MISMATCH")
    if "javascript" not in paths["/webui/audio-ui.mjs"][2].lower():
        raise Blocked("VOICE_MIME_MISMATCH")
    if paths["/webui/"][1] != digest((SRC / "webui/index.html").read_bytes()):
        raise Blocked("EXISTING_UI_V3_NOT_SERVED")
    if paths["/webui/app.js"][1] != digest((SRC / "webui/app.js").read_bytes()):
        raise Blocked("EXISTING_TEXT_UI_NOT_SERVED")


def pinned_voice():
    url = "https://raw.githubusercontent.com/" + REPO + "/" + SOURCE_COMMIT + "/webui/" + FILE_NAME
    req = urllib.request.Request(url, headers={"User-Agent": "S3-Voice-WebUI-Voice-Pinned/1"})
    with urllib.request.urlopen(req, timeout=25) as result:
        if result.status != 200:
            raise Blocked("PINNED_SOURCE_UNAVAILABLE")
        data = result.read(100001)
    if not (0 < len(data) < 100001) or blob(data) != AFTER_BLOB:
        raise Blocked("PINNED_VOICE_BLOB_MISMATCH")
    script = data.decode("utf-8")
    for expected in ("resumeAfterAudioTail", "node.onended", "ttsStopped",
                     "getUserMedia", "/webui/ws", "clearTimeout"):
        if expected not in script:
            raise Blocked("VOICE_SOURCE_CONTRACT_FAILED")
    return data


def atomic_replace(data):
    old = VOICE.stat()
    fd, temp = tempfile.mkstemp(prefix=".webui-voice-", dir=str(VOICE.parent))
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        os.chown(temp, old.st_uid, old.st_gid)
        os.chmod(temp, stat.S_IMODE(old.st_mode))
        os.replace(temp, VOICE)
        if VOICE.read_bytes() != data:
            raise Blocked("VOICE_WRITE_MISMATCH")
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def backup(original, candidate):
    BACKUPS.mkdir(mode=0o700, exist_ok=True)
    if BACKUPS.is_symlink():
        raise Blocked("BACKUP_DIR_SYMLINK")
    target = BACKUPS / ("webui-voice-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    target.mkdir(mode=0o700)
    old = target / "before.mjs"
    with old.open("xb") as output:
        output.write(original)
        output.flush()
        os.fsync(output.fileno())
    old.chmod(0o600)
    manifest = {"kind": "webui-voice-single-file", "source_commit": SOURCE_COMMIT,
                "original_sha256": digest(original), "published_sha256": digest(candidate)}
    meta = target / "manifest.json"
    with meta.open("x") as output:
        json.dump(manifest, output)
        output.flush()
        os.fsync(output.fileno())
    meta.chmod(0o600)
    return target


def recover():
    if not BACKUPS.is_dir() or BACKUPS.is_symlink():
        raise Blocked("NO_VOICE_BACKUP")
    available = sorted(BACKUPS.glob("webui-voice-*/manifest.json"), reverse=True)
    for path in available:
        if path.is_symlink() or path.parent.is_symlink():
            continue
        manifest = json.loads(path.read_text())
        if manifest.get("kind") != "webui-voice-single-file":
            continue
        if (path.parent / "rolled-back").exists():
            continue
        if digest(VOICE.read_bytes()) != manifest["published_sha256"]:
            raise Blocked("CURRENT_VOICE_DIFFERS_FROM_BACKUP")
        original = (path.parent / "before.mjs").read_bytes()
        if digest(original) != manifest["original_sha256"]:
            raise Blocked("BACKUP_HASH_MISMATCH")
        return path.parent, original
    raise Blocked("NO_ACTIVE_VOICE_RELEASE")


def release(mode):
    safe_paths()
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before_containers = container_states()
        before_guards = guarded_hashes()
        original = VOICE.read_bytes()
        verify_routes(digest(original))
        print("WEBUI_VOICE_PRECHECK_PASS", flush=True)
        if mode == "status":
            print("WEBUI_VOICE_STATE=" +
                  ("UPDATED" if blob(original) == AFTER_BLOB else
                   "STABLE" if blob(original) == BEFORE_BLOB else "CUSTOM"),
                  flush=True)
            return
        if mode == "rollback":
            _, candidate = recover()
            if blob(original) != AFTER_BLOB:
                raise Blocked("ROLLED_BACK_SOURCE_UNEXPECTED")
            backup_data = candidate
        else:
            backup_data = None
            candidate = pinned_voice()
            print("WEBUI_VOICE_PINNED_HASH_PASS", flush=True)
            if original == candidate:
                print("WEBUI_VOICE_ALREADY_ACTIVE_PASS", flush=True)
                return
            if blob(original) != BEFORE_BLOB:
                raise Blocked("LIVE_VOICE_CUSTOMIZED_NO_OVERWRITE")
        if container_states() != before_containers or guarded_hashes() != before_guards:
            raise Blocked("BASELINE_CHANGED_BEFORE_WRITE")
        snapshot = None
        if mode != "rollback":
            snapshot = backup(original, candidate)
            print("WEBUI_VOICE_PRIVATE_BACKUP_PASS", flush=True)
        changed = False
        try:
            changed = True
            atomic_replace(candidate)
            verify_routes(digest(candidate))
            if container_states() != before_containers or guarded_hashes() != before_guards:
                raise Blocked("PROTECTED_BASELINE_CHANGED")
            if mode == "rollback":
                # Mark the snapshot used so another rollback cannot overwrite a new release.
                folder, _ = recover()
                (folder / "rolled-back").touch(mode=0o600, exist_ok=False)
                print("WEBUI_VOICE_MANUAL_ROLLBACK_PASS", flush=True)
            else:
                print("WEBUI_VOICE_AUDIO_ONLY_ACTIVE_PASS", flush=True)
                print("WEBUI_VOICE_NO_CONTAINER_RESTART_PASS", flush=True)
                print("WEBUI_VOICE_SAFARI_AUDIO_PENDING", flush=True)
        except Exception:
            if changed:
                try:
                    atomic_replace(original)
                    verify_routes(digest(original))
                    print("WEBUI_VOICE_FAILED_APPLY_ROLLBACK_PASS", flush=True)
                except Exception:
                    print("WEBUI_VOICE_ROLLBACK_UNVERIFIED", flush=True)
            raise
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("status", "apply", "rollback"), nargs="?", default="apply")
    args = parser.parse_args()
    try:
        release(args.action)
    except Exception as exc:
        # No error details: helper runs near private API and login configuration.
        print("WEBUI_VOICE_BLOCKED_" + type(exc).__name__, flush=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
