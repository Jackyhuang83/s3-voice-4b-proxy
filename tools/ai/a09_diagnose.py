#!/usr/bin/env python3
"""One-shot privacy-preserving A09-Lite OTA ingress diagnostic.

The existing A04/4B gate, Cloudflare tunnel and voice core are never restarted.
Only the new A09 adapter is restarted. A04's new A09 OTA matcher is temporarily
forwarded directly to the A09 adapter so missing headers can be counted while
their requests still fail closed. All touched bytes are backed up and reversible.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path("/opt/s3-voice-a09-lite")
A04 = Path("/opt/s3-voice-ai-edge/Caddyfile")
APP = ROOT / "a09_lite.py"
ENV = ROOT / ".env"
ACTIVE = ROOT / ".same-host-active"
OLD_APP = ROOT / ".diag-before-adapter.py"
OLD_A04 = ROOT / ".diag-before-a04.Caddyfile"
MARK = ROOT / ".diag-active"
BASE = ROOT / ".diag-baseline.json"
REVIEWED = Path(__file__).with_name("a09_lite.py")
KNOWN_OLD_BLOB = "3c2c6649a842472a7fe2ca8465de0bf8a74184d9"
ORIGINAL = ("s3-voice-ai-server", "s3-voice-ai-gateway", "s3-voice-ai-tunnel")
ADAPTER = "s3-voice-a09-lite-adapter"
GATEWAY = "s3-voice-a09-lite-gateway"


class Blocked(Exception):
    pass


def ensure(condition, reason):
    if not condition:
        raise Blocked(reason)


def announce(tag, text):
    print("A09_DIAG_%s: %s" % (tag, text), flush=True)


def run(*args, stdin=None, timeout=30):
    p = subprocess.run(args, input=stdin, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        # Never print stdout/stderr: Caddy or Compose may contain private URLs.
        raise Blocked("command failed: %s (exit %d)" % (args[0], p.returncode))
    return p.stdout.decode("utf-8", "replace").strip()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def check_files():
    ensure(os.geteuid() == 0, "requires root")
    for p in (ROOT, APP, A04, ENV, ACTIVE):
        ensure(p.exists() and not p.is_symlink(), "required installed file missing/unsafe")
    ensure((ROOT.stat().st_mode & 0o077) == 0, "A09 owner directory is not private")
    ensure(REVIEWED.is_file(), "reviewed diagnostic adapter source missing")
    env = {}
    for line in ENV.read_text().splitlines():
        k, sep, v = line.partition("=")
        ensure(sep == "=" and k not in env, "invalid A09 environment")
        env[k] = v
    secret = env.get("IOS_SECRET", "")
    ensure(re.fullmatch(r"[a-f0-9]{64}", secret) is not None, "invalid A09 secret")
    ensure(env.get("IOS_HOSTNAME") == "voice.cncloudx.com",
           "existing voice hostname not activated")
    return secret


def ids():
    return {n: run("docker", "inspect", "-f", "{{.Id}}", n) for n in ORIGINAL}


def healthy():
    for n in ORIGINAL + (ADAPTER, GATEWAY):
        ensure(run("docker", "inspect", "-f", "{{.State.Running}}", n) == "true",
               "expected container not running")
    ensure(code("http://127.0.0.1:18003/xiaozhi/ota/") == 200,
           "original A03 OTA is unhealthy")
    ensure(code("http://127.0.0.1:18080/") == 403,
           "original A04 default deny is unhealthy")


def code(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {},
                                 method="POST" if data is not None else "GET")
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=6) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (OSError, TimeoutError, urllib.error.URLError):
        return -1


def memory():
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, sep, v = line.partition(":")
        if k in ("MemAvailable", "SwapTotal", "SwapFree"):
            values[k] = int(v.strip().split()[0])
    return values


def guard_resources(before):
    after = memory()
    ensure(after["MemAvailable"] >= 1_100_000, "less than 1.05 GiB free after change")
    before_swap = before["SwapTotal"] - before["SwapFree"]
    after_swap = after["SwapTotal"] - after["SwapFree"]
    ensure(after_swap - before_swap <= 65536, "swap increased by >64MiB")


def compose_ready():
    for _ in range(35):
        if run("docker", "inspect", "-f", "{{.State.Health.Status}}", ADAPTER) == "healthy":
            return
        time.sleep(1)
    raise Blocked("new A09 adapter failed health check")


def same_inode_write(path, content):
    ensure(path.is_file() and not path.is_symlink(), "unsafe source file")
    before = path.stat().st_ino
    with path.open("r+b", buffering=0) as f:
        f.seek(0)
        f.truncate()
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    ensure(path.stat().st_ino == before, "Docker bind-mounted source inode changed")


def caddy_adapt(content):
    run("docker", "exec", "-i", "s3-voice-ai-gateway", "caddy", "adapt",
        "--config", "-", "--adapter", "caddyfile", stdin=content, timeout=15)


def caddy_reload():
    run("docker", "exec", "s3-voice-ai-gateway", "caddy", "reload",
        "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile", timeout=15)


def diagnostics():
    # Read private adapter loopback through docker exec. No public diagnostic route.
    source = """import json,urllib.request
p=urllib.request.build_opener(urllib.request.ProxyHandler({}))
with p.open('http://127.0.0.1:19009/internal/diagnostics',timeout=4) as r:
 print(r.read(8192).decode())"""
    return json.loads(run("docker", "exec", ADAPTER, "python", "-I", "-c", source))


def private_create(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def candidate(caddy, secret):
    original = (
        "  @a09_ota {\n"
        "    method POST\n"
        "    path /xiaozhi/ota/" + secret + "\n"
        "    header Device-Id *\n"
        "    header Client-Id *\n"
        "  }\n"
        "  handle @a09_ota {\n"
        "    reverse_proxy s3-voice-a09-lite-gateway:8080\n"
        "  }\n"
    )
    # Temporary diagnostic route: the adapter STILL requires both headers.
    # Only the separately secret A09 route changes, never original 4B rules.
    replacement = (
        "  @a09_ota {\n"
        "    method POST\n"
        "    path /xiaozhi/ota/" + secret + "\n"
        "  }\n"
        "  handle @a09_ota {\n"
        "    rewrite * /xiaozhi/ota/\n"
        "    reverse_proxy s3-voice-a09-lite-adapter:19009\n"
        "  }\n"
    )
    ensure(caddy.count(original) == 1, "unexpected A04 iOS matcher; refusing changes")
    return caddy.replace(original, replacement, 1)


def rollback(interrupted=False):
    check_files()
    ensure(OLD_A04.is_file() and OLD_APP.is_file(), "no private diagnostic backups")
    old_a04 = OLD_A04.read_bytes()
    old_app = OLD_APP.read_bytes()
    ensure(git_blob(old_app) == KNOWN_OLD_BLOB, "unknown adapter backup")
    secret = check_files()
    expected = candidate(old_a04.decode(), secret).encode()
    # Refuse to overwrite unrelated admin changes, except partial same-inode writes.
    current = A04.read_bytes()
    if not interrupted:
        ensure(current == expected, "unexpected Caddy edits after arm; refuse overwrite")
        ensure(APP.read_bytes() == REVIEWED.read_bytes(),
               "unexpected adapter edits after arm; refuse overwrite")
    original_ids = ids()
    caddy_adapt(old_a04)
    same_inode_write(A04, old_a04)
    caddy_reload()
    same_inode_write(APP, old_app)
    run("docker", "restart", ADAPTER, timeout=50)
    compose_ready()
    healthy()
    ensure(ids() == original_ids, "original 4B container identity changed")
    for path in (MARK, BASE, OLD_A04, OLD_APP):
        path.unlink(missing_ok=True)
    announce("ROLLBACK_PASS", "restored exact original A04 and A09 bytes; original 4B untouched")


def arm():
    secret = check_files()
    ensure(not any(p.exists() for p in (OLD_APP, OLD_A04, MARK, BASE)),
           "diagnostic already armed or partial backup exists; do not overwrite")
    ensure(git_blob(APP.read_bytes()) == KNOWN_OLD_BLOB,
           "installed adapter source differs from known P2 baseline; STOP")
    reviewed = REVIEWED.read_bytes()
    ensure(b"/internal/diagnostics" in reviewed and b"RequestDiagnostics" in reviewed,
           "reviewed diagnostics implementation absent")
    old_ids = ids()
    healthy()
    before = memory()
    ensure(before["MemAvailable"] >= 1_400_000, "less than 1.34 GiB free")
    original = A04.read_bytes()
    changed = candidate(original.decode(), secret).encode()
    caddy_adapt(changed)
    # Create backups BEFORE any production write.
    private_create(OLD_APP, APP.read_bytes())
    private_create(OLD_A04, original)
    try:
        same_inode_write(APP, reviewed)
        run("docker", "restart", ADAPTER, timeout=50)
        compose_ready()
        same_inode_write(A04, changed)
        caddy_reload()
        # A bad identity must reach the adapter and remain HTTP 400, NOT mint a code.
        url = "http://127.0.0.1:18080/xiaozhi/ota/" + secret
        probe_headers = {"Device-Id": "02:00:00:00:00:09", "Content-Type": "application/json"}
        ensure(code(url, data=b"{}", headers=probe_headers) == 400,
               "temporary private route failed to enforce missing Client-Id")
        snap = diagnostics()
        ensure(snap["counts"]["ota_seen"] >= 1 and
               snap["counts"]["missing_client_id"] >= 1,
               "privacy counters did not record missing Client-Id")
        ensure(code("http://127.0.0.1:18080/internal/diagnostics") == 403,
               "internal diagnostics unexpectedly public")
        healthy()
        guard_resources(before)
        ensure(ids() == old_ids, "original 4B container changed")
        private_create(BASE, json.dumps(snap, separators=(",", ":")).encode())
        private_create(MARK, b"enabled\n")
        announce("ARM_PASS", "private counters enabled; 4B route unchanged; ready for ONE phone connect")
    except BaseException:
        try:
            rollback(interrupted=True)
        except BaseException:
            announce("ROLLBACK_BLOCKED", "private backups preserved; do not restart 4B")
        raise


def report():
    check_files()
    ensure(MARK.is_file() and BASE.is_file(), "diagnostic has not been armed")
    before = json.loads(BASE.read_text())["counts"]
    now = diagnostics()
    since = now["since"]
    baseline = json.loads(BASE.read_text())["since"]
    ensure(since == baseline, "adapter restarted; counters lost; no reliable report")
    counts = {key: max(0, int(n) - int(before.get(key, 0)))
              for key, n in now["counts"].items()}
    # Values describe all new requests to private adapter since arm, not a
    # fingerprint of any particular phone. No user identity or code is stored.
    fmt = " ".join("%s=%d" % (k, v) for k, v in sorted(counts.items()))
    announce("COUNTS", fmt)
    if counts["ota_seen"] == 0:
        announce("VERDICT", "NO_A09_OTA_REACHED (client config/path/method/Cloudflare route not proven)")
    elif counts["missing_client_id"] or counts["missing_device_id"]:
        announce("VERDICT", "MISSING_REQUIRED_IDENTITY (do not auto-generate identifiers)")
    elif counts["bad_client_id"] or counts["bad_device_id"]:
        announce("VERDICT", "INVALID_IDENTITY_FORMAT")
    elif counts["upstream_error"]:
        announce("VERDICT", "A03_UPSTREAM_UNAVAILABLE")
    elif counts["bad_body"]:
        announce("VERDICT", "OTA_REQUEST_OR_RESPONSE_INCOMPATIBLE")
    elif counts["ota_code_in_response"]:
        announce("VERDICT", "A09_OTA_CODE_ISSUED (check current pending expiry, not app UI)")
    else:
        announce("VERDICT", "OTA_SEEN_NO_CODE (inspect redacted response stage)")
    healthy()
    announce("READ_ONLY_PASS", "no secret/device identities displayed or changed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("arm", "report", "rollback"))
    arg = parser.parse_args()
    try:
        {"arm": arm, "report": report, "rollback": rollback}[arg.command]()
    except (Blocked, OSError, subprocess.TimeoutExpired, ValueError, KeyError,
            UnicodeError, json.JSONDecodeError) as e:
        # Exception details never contain request URI or secret.
        announce("BLOCKED", str(e))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
