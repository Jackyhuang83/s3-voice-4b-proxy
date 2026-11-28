#!/usr/bin/env python3
"""Guarded, reversible *UI-only* publisher for S3-Voice WebUI v3.

Downloads 3 immutable reviewed GitHub blobs, verifies Git blob OIDs, backs up
the live customizations, atomically replaces only those 3 assets and checks
the running Gateway/Auth responses. No Docker restarts, Caddy changes,
credentials, audio module changes, or real model API calls.
"""
import argparse
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

REPO = "Jackyhuang83/s3-voice-4b-proxy"
# Review-pinned UI v3 source; NOT a branch reference.
SOURCE_COMMIT = "35a3cf5464b495d5d941c8bf53a6d2e4188b34b4"
EXPECTED_GIT_BLOBS = {
    "index.html": "d275e1192f59a65c15605f5c1cb266b2287f2158",
    "app.css": "54fe60556917a5f87f729dfe0270a39bf510e803",
    "app.js": "e2907dae0492cbfd6fa53346cb35c2aa2393163d",
}
BASE = Path("/opt/s3-voice-webui")
SOURCE = BASE / "src"
WEBUI = SOURCE / "webui"
PRIVATE = BASE / "private"
GATEWAY = "s3-voice-webui-gateway"
AUTH = "s3-voice-webui-auth"
IMMUTABLE_CONTAINERS = (GATEWAY, AUTH, "s3-voice-ai-server", "s3-voice-ai-gateway")
CODE_GUARDS = (
    "tools/ai/webui_auth.py", "tools/ai/webui_text.py",
    "webui/audio-ui.mjs", "webui/audio-opus.mjs",
    "webui/audio-worklet.js", "deploy/ai/webui/Caddyfile.isolated",
)
REQUIRED_DOM_IDS = (
    "connectionStatus", "logoutBtn", "loginView", "loginForm",
    "ownerPassword", "loginBtn", "loginError", "chatView",
    "modelSelect", "newChatBtn", "messages", "welcome",
    "chatForm", "messageInput", "voiceButton", "sendBtn",
    "voiceStatus", "appNotice",
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    prefix = b"blob " + str(len(data)).encode("ascii") + b"\x00"
    return hashlib.sha1(prefix + data).hexdigest()


def run(argv, *, input_data=None, timeout=30):
    proc = subprocess.run(
        argv, input=input_data, capture_output=True, timeout=timeout
    )
    if proc.returncode:
        raise RuntimeError(
            "COMMAND_FAILED " + " ".join(argv[:3]) + " rc=" + str(proc.returncode)
        )
    return proc.stdout


def inspect(name):
    result = json.loads(run(["docker", "inspect", name]).decode())[0]
    if not result["State"]["Running"]:
        raise RuntimeError("CONTAINER_NOT_RUNNING_" + name)
    return result


def identity(name):
    item = inspect(name)
    return item["Id"], item["State"]["StartedAt"]


def assert_safe_files():
    if os.geteuid() != 0:
        raise RuntimeError("ROOT_REQUIRED")
    for directory in (BASE, SOURCE, WEBUI, PRIVATE):
        if not directory.is_dir() or directory.is_symlink():
            raise RuntimeError("UNEXPECTED_DIRECTORY_" + directory.name)
    for name in EXPECTED_GIT_BLOBS:
        p = WEBUI / name
        if not p.is_file() or p.is_symlink():
            raise RuntimeError("UNEXPECTED_STATIC_FILE_" + name)
    for rel in CODE_GUARDS:
        p = SOURCE / rel
        if not p.is_file() or p.is_symlink():
            raise RuntimeError("UNEXPECTED_GUARDED_FILE_" + rel)


def runtime_identities():
    objects = {name: inspect(name) for name in IMMUTABLE_CONTAINERS}
    auth = objects[AUTH]
    if not any(
        m.get("Source") == str(SOURCE) and
        m.get("Destination") == "/project" and not m.get("RW", True)
        for m in auth["Mounts"]
    ):
        raise RuntimeError("AUTH_READ_ONLY_SOURCE_MOUNT_NOT_VERIFIED")
    if auth["HostConfig"].get("PortBindings") or objects[GATEWAY]["HostConfig"].get("PortBindings"):
        raise RuntimeError("WEBUI_PORT_EXPOSURE_MISMATCH")
    return {name: (item["Id"], item["State"]["StartedAt"]) for name, item in objects.items()}


def protected_hashes():
    return {rel: sha((SOURCE / rel).read_bytes()) for rel in CODE_GUARDS}


class IdParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = {}
        self.csp = []

    def handle_starttag(self, tag, attrs):
        opts = dict(attrs)
        if "id" in opts:
            self.ids[opts["id"]] = self.ids.get(opts["id"], 0) + 1
        if tag == "meta" and opts.get("http-equiv") == "Content-Security-Policy":
            self.csp.append(opts.get("content", ""))


def validate_source(source):
    if sorted(source) != sorted(EXPECTED_GIT_BLOBS):
        raise RuntimeError("UNEXPECTED_SOURCE_ASSET_LIST")
    for name, data in source.items():
        if git_blob(data) != EXPECTED_GIT_BLOBS[name]:
            raise RuntimeError("DOWNLOADED_GIT_BLOB_MISMATCH_" + name)
        if len(data) > 100000 or not data:
            raise RuntimeError("UNEXPECTED_SOURCE_SIZE_" + name)
    p = IdParser()
    p.feed(source["index.html"].decode("utf-8"))
    if any(p.ids.get(x) != 1 for x in REQUIRED_DOM_IDS):
        raise RuntimeError("MISSING_OR_DUPLICATE_UI_DOM_ID")
    if len(p.csp) != 1 or "default-src 'none'" not in p.csp[0] or "'unsafe-inline'" in p.csp[0]:
        raise RuntimeError("HTML_CSP_INVARIANT_FAILED")
    js = source["app.js"].decode("utf-8")
    for marker in ('const originAPI = "/webui/api/"', 'originAPI + "chat"', 'const welcomeNode = el("welcome")'):
        if marker not in js:
            raise RuntimeError("TEXT_CHAT_CONTRACT_MISSING")
    for marker in ("prefers-color-scheme: light", "safe-area-inset-bottom", ".composer"):
        if marker not in source["app.css"].decode("utf-8"):
            raise RuntimeError("UI_CSS_CONTRACT_MISSING")


def fetch_reviewed_source():
    result = {}
    for name in EXPECTED_GIT_BLOBS:
        url = "https://raw.githubusercontent.com/" + REPO + "/" + SOURCE_COMMIT + "/webui/" + name
        req = urllib.request.Request(url, headers={"User-Agent": "S3Voice-UIv3-PinnedPublisher/1"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            if resp.status != 200:
                raise RuntimeError("GITHUB_FETCH_STATUS_" + name)
            result[name] = resp.read(100001)
    validate_source(result)
    print("REVIEWED_SOURCE_PINNED_PASS", flush=True)
    return result


def probe():
    # Run from the EXISTING read-only Auth container across the current
    # Docker private network. No host ports, secrets or new containers needed.
    code = r'''
import hashlib, http.client, json
paths=("/", "/webui/", "/webui/?callback=synthetic",
       "/webui/app.css", "/webui/app.js",
       "/webui/api/session", "/webui/api/models",
       "/internal/ws-auth", "/webui/ws")
rows={}
for path in paths:
    c=http.client.HTTPConnection("s3-voice-webui-gateway",8080,timeout=4)
    try:
        c.request("GET",path)
        r=c.getresponse()
        raw=r.read(180000)
        rows[path]=[r.status, r.getheader("Location","-"),
                    hashlib.sha256(raw).hexdigest(),
                    b'id="loginView"' in raw]
    finally:
        c.close()
print(json.dumps(rows,sort_keys=True))
'''
    output = run(["docker", "exec", "-i", AUTH, "python3", "-B", "-"],
                 input_data=code.encode(), timeout=40)
    return json.loads(output.decode())


def assert_routes(rows, expected):
    statuses = {
        "/": 302,
        "/webui/": 200,
        "/webui/?callback=synthetic": 200,
        "/webui/app.css": 200,
        "/webui/app.js": 200,
        "/webui/api/session": 200,
        "/webui/api/models": 401,
        "/internal/ws-auth": 403,
        "/webui/ws": 403,
    }
    for url, status in statuses.items():
        if rows.get(url, [None])[0] != status:
            raise RuntimeError("RUNTIME_ROUTE_MISMATCH_" + url)
    if rows["/"][1] != "/webui/":
        raise RuntimeError("HOTFIX_ROOT_REDIRECT_REGRESSION")
    if not rows["/webui/"][3] or not rows["/webui/?callback=synthetic"][3]:
        raise RuntimeError("CLOUDFLARE_LANDING_REGRESSION")
    for name, url in (("index.html", "/webui/"),
                      ("app.css", "/webui/app.css"), ("app.js", "/webui/app.js")):
        if rows[url][2] != sha(expected[name]):
            raise RuntimeError("SERVING_WRONG_CONTENT_" + name)


def verify(expected, wait_seconds=12):
    deadline = time.monotonic() + wait_seconds
    last = ""
    while True:
        try:
            assert_routes(probe(), expected)
            return
        except Exception as exc:
            last = str(exc)
            if time.monotonic() >= deadline:
                raise RuntimeError("HTTP_ACCEPTANCE_FAILED_" + last) from exc
            time.sleep(0.4)


def atomic_publish(name, content):
    target = WEBUI / name
    original = target.stat()
    # Unlike single-file Caddy mount, /project is a read-only DIRECTORY bind.
    # Replace entry atomically so requests never read half a JS/CSS/HTML file.
    fd, tmpname = tempfile.mkstemp(prefix=".webui-v3-", dir=str(WEBUI))
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chown(tmpname, original.st_uid, original.st_gid)
        os.chmod(tmpname, stat.S_IMODE(original.st_mode))
        os.replace(tmpname, target)
        os.chmod(target, stat.S_IMODE(original.st_mode))
        if target.read_bytes() != content:
            raise RuntimeError("FILE_WRITE_MISMATCH_" + name)
    finally:
        if os.path.exists(tmpname):
            os.unlink(tmpname)


def safe_backup(before, after):
    parent = PRIVATE / "backups"
    parent.mkdir(mode=0o700, exist_ok=True)
    if parent.is_symlink():
        raise RuntimeError("BACKUP_PARENT_SYMLINK")
    directory = parent / ("webui-v3-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    directory.mkdir(mode=0o700)
    for name, content in before.items():
        out = directory / name
        with out.open("xb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        out.chmod(0o600)
    manifest = {
        "publisher": "S3-Voice UI v3 guarded one-shot",
        "reviewed_commit": SOURCE_COMMIT,
        "original_sha256": {key: sha(val) for key,val in before.items()},
        "published_sha256": {key: sha(val) for key,val in after.items()},
    }
    out = directory / "manifest.json"
    with out.open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    out.chmod(0o600)
    return directory


def rollback(before, original_protected, original_containers):
    # Always restore the exact original 3 bytes, including local customizations.
    for name in ("app.css", "app.js", "index.html"):
        atomic_publish(name, before[name])
    verify(before)
    if protected_hashes() != original_protected:
        raise RuntimeError("ROLLBACK_PROTECTED_FILES_CHANGED")
    if {n: identity(n) for n in IMMUTABLE_CONTAINERS} != original_containers:
        raise RuntimeError("ROLLBACK_CONTAINER_IDENTITY_CHANGED")
    print("UI_V3_ROLLBACK_VERIFIED_PASS", flush=True)


def main():
    assert_safe_files()
    lock_file = PRIVATE / "webui-v3-publisher.lock"
    if lock_file.is_symlink():
        raise RuntimeError("LOCK_SYMLINK")
    with lock_file.open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        containers = runtime_identities()
        original_protected = protected_hashes()
        before = {name: (WEBUI / name).read_bytes() for name in EXPECTED_GIT_BLOBS}
        verify(before, wait_seconds=5)
        print("PRODUCTION_STABLE_BASELINE_PASS", flush=True)
        reviewed = fetch_reviewed_source()
        if before == reviewed:
            print("UI_V3_ALREADY_DEPLOYED_PASS", flush=True)
            return
        # Do not update if anything changed during the read-only preflight.
        if {n: identity(n) for n in IMMUTABLE_CONTAINERS} != containers:
            raise RuntimeError("CONTAINER_CHANGED_DURING_PREFLIGHT")
        if {name: (WEBUI / name).read_bytes() for name in EXPECTED_GIT_BLOBS} != before:
            raise RuntimeError("SOURCE_CHANGED_DURING_PREFLIGHT")
        backup = safe_backup(before, reviewed)
        print("UI_V3_BACKUP_PASS", flush=True)
        print("ROLLBACK_BACKUP_DIRECTORY=" + str(backup), flush=True)
        updated = False
        try:
            updated = True
            # HTML last: new DOM is only advertised after CSS/JS are present.
            for name in ("app.css", "app.js", "index.html"):
                atomic_publish(name, reviewed[name])
            verify(reviewed)
            if {n: identity(n) for n in IMMUTABLE_CONTAINERS} != containers:
                raise RuntimeError("PROTECTED_CONTAINER_RESTART_DETECTED")
            if protected_hashes() != original_protected:
                raise RuntimeError("PROTECTED_MODULE_CHANGED")
            print("UI_V3_LIVE_HTTP_PASS", flush=True)
            print("AUTH_CADDY_A03_A04_UNCHANGED_PASS", flush=True)
            print("NO_CONTAINER_RESTART_PASS", flush=True)
            print("PUBLIC_SAFARI_VISUAL_CHECK_REMAINS", flush=True)
        except Exception as problem:
            print("UI_V3_DEPLOY_FAILED=" + type(problem).__name__ + ":" + str(problem), flush=True)
            if updated:
                try:
                    rollback(before, original_protected, containers)
                except Exception as rb:
                    print("ROLLBACK_REQUIRES_MANUAL_REVIEW=" + str(rb), flush=True)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish exactly three reviewed UI v3 files on the existing VPS")
    parser.add_argument("--source-info", action="store_true", help="Print immutable source reference and exit")
    args = parser.parse_args()
    if args.source_info:
        print("SOURCE_COMMIT=" + SOURCE_COMMIT)
        print("ASSETS=" + ",".join(EXPECTED_GIT_BLOBS))
        sys.exit(0)
    try:
        main()
    except Exception as e:
        print("UI_V3_BLOCKED=" + type(e).__name__ + ":" + str(e), flush=True)
        sys.exit(1)
