#!/usr/bin/env python3
"""A09-Lite: owner-approved XiaoZhi six-digit OTA compatibility proxy.

Uses stdlib only; does NOT implement or fork speech, WebSocket or authentication.
Runs on loopback only. Upstream OTA provides the original server HMAC token.
"""

import argparse
from contextlib import contextmanager
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, parse, request

MAC = re.compile(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\Z")
CODE = re.compile(r"[0-9]{6}\Z")
MAX_BODY = 16384
TTL_SECONDS = 600
DEFAULT_DB = "/var/lib/s3-voice-a09-lite/activation.sqlite3"
DEFAULT_UPSTREAM = "http://127.0.0.1:18003/xiaozhi/ota/"
DOCKER_UPSTREAM = "http://s3-voice-ai-server:8003/xiaozhi/ota/"
DEFAULT_WSS = "wss://a09-lite-not-ready.invalid/xiaozhi/v1/"


def docker_internal():
    """Enable the Docker-only listener only inside a container, never on the host."""
    return os.environ.get("A09_LITE_DOCKER_INTERNAL") == "1" and Path("/.dockerenv").is_file()


def validate_origin(origin):
    if origin == DEFAULT_UPSTREAM:
        return origin
    if docker_internal() and origin == DOCKER_UPSTREAM:
        return origin
    raise ValueError("OTA origin must be the known A03 host-loopback or Docker service endpoint")


def validate_wss(url):
    parsed = parse.urlsplit(url)
    if parsed.scheme != "wss" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.path.startswith("/xiaozhi/v1/"):
        raise ValueError("a separate HTTPS-protected iOS WSS URL is required")
    return url


class ActivationStore:
    def __init__(self, path, now=None):
        self.path = str(path)
        self.now = now or (lambda: int(time.time()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        folder = Path(self.path).parent
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Reject a symlink, accidental existing permissive database, or public directory.
        if folder.is_symlink() or (folder.stat().st_mode & 0o077):
            raise PermissionError("activation directory must be owner-only (0700)")
        if Path(self.path).is_symlink():
            raise PermissionError("refuse SQLite symlink")
        old_umask = os.umask(0o077)
        try:
            with self.connect() as db:
                db.execute("""CREATE TABLE IF NOT EXISTS devices (
                    device_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    code TEXT UNIQUE,
                    expires_at INTEGER,
                    bound_at INTEGER
                )""")
        finally:
            os.umask(old_umask)
        os.chmod(self.path, 0o600)
        if os.stat(self.path).st_mode & 0o077:
            raise PermissionError("activation database must be owner-only (0600)")

    def issue(self, device_id, client_id):
        now = self.now()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM devices WHERE device_id=?", (device_id,)).fetchone()
            if row and not hmac.compare_digest(row["client_id"], client_id):
                raise PermissionError("device identity already registered to a different client")
            if row and row["bound_at"] is not None:
                return None
            if row and row["expires_at"] and row["expires_at"] > now:
                return row["code"]
            # Delete expired unbound rows so codes cannot accumulate indefinitely.
            db.execute("DELETE FROM devices WHERE bound_at IS NULL AND expires_at <= ?", (now,))
            for _ in range(16):
                code = f"{secrets.randbelow(1_000_000):06d}"
                if not db.execute("SELECT 1 FROM devices WHERE code=?", (code,)).fetchone():
                    db.execute("INSERT OR REPLACE INTO devices(device_id, client_id, code, expires_at, bound_at) VALUES(?,?,?,?,NULL)",
                               (device_id, client_id, code, now + TTL_SECONDS))
                    return code
            raise RuntimeError("activation code collision budget exhausted")

    def approved(self, device_id, client_id):
        with self.connect() as db:
            row = db.execute("SELECT client_id, bound_at FROM devices WHERE device_id=?", (device_id.lower(),)).fetchone()
            return bool(row and row["bound_at"] is not None and hmac.compare_digest(row["client_id"], client_id))

    def approve(self, code):
        if not CODE.fullmatch(code):
            raise ValueError("six digits required")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT device_id, expires_at FROM devices WHERE code=? AND bound_at IS NULL", (code,)).fetchone()
            if row is None or row["expires_at"] <= self.now():
                raise ValueError("missing or expired pending code")
            db.execute("UPDATE devices SET bound_at=?, code=NULL, expires_at=NULL WHERE device_id=? AND code=?",
                       (self.now(), row["device_id"], code))
            return row["device_id"]

    def revoke(self, device_id):
        if not MAC.fullmatch(device_id):
            raise ValueError("invalid device ID")
        with self.connect() as db:
            return db.execute("DELETE FROM devices WHERE device_id=?", (device_id.lower(),)).rowcount


def create_handler(store, upstream, wss_url):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            # No request URI, headers, device identities, tokens or activation codes in logs.
            pass

        def respond(self, status, obj=None):
            body = b"" if obj is None else json.dumps(obj, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def identity(self):
            device_id = self.headers.get("Device-Id", "").strip()
            client_id = self.headers.get("Client-Id", "").strip()
            if not MAC.fullmatch(device_id) or not client_id or len(client_id) > 128 or any(ord(c) < 33 or ord(c) > 126 for c in client_id):
                raise ValueError("invalid device identity")
            return device_id, client_id

        def do_GET(self):
            if self.path == "/health":
                self.respond(200, {"status": "ready"})
            elif self.path == "/internal/authorize-ws":
                try:
                    device_id, client_id = self.identity()
                    self.respond(200 if store.approved(device_id, client_id) else 403)
                except (ValueError, sqlite3.Error):
                    self.respond(403)
            else:
                self.respond(404)

        def do_POST(self):
            if self.path == "/xiaozhi/ota/activate":
                try:
                    device_id, client_id = self.identity()
                    self.respond(200 if store.approved(device_id, client_id) else 202)
                except (ValueError, sqlite3.Error):
                    self.respond(202)
                return
            if self.path != "/xiaozhi/ota/":
                self.respond(404)
                return
            try:
                device_id, client_id = self.identity()
                size = int(self.headers.get("Content-Length", "-1"))
                if size <= 0 or size > MAX_BODY:
                    raise ValueError("invalid body size")
                payload = self.rfile.read(size)
                if not isinstance(json.loads(payload), dict):
                    raise ValueError("invalid OTA payload")
                req = request.Request(upstream, data=payload, method="POST", headers={
                    "Device-Id": device_id, "Client-Id": client_id, "Content-Type": "application/json"})
                opener = request.build_opener(request.ProxyHandler({}))
                with opener.open(req, timeout=5) as resp:
                    if resp.status != 200:
                        raise ValueError("upstream OTA failed")
                    result = json.loads(resp.read(65536))
                if not isinstance(result, dict):
                    raise ValueError("invalid upstream OTA response")
                ws = result.get("websocket") or {}
                if not isinstance(ws.get("url"), str) or not isinstance(ws.get("token"), str) or not ws["token"]:
                    raise ValueError("upstream missing required WebSocket token")
                code = store.issue(device_id.lower(), client_id)
                result["websocket"]["url"] = wss_url
                if code is not None:
                    result["activation"] = {
                        "code": code,
                        "message": "Enter this code in your private S3-Voice owner console: " + code,
                        "challenge": device_id,
                    }
                else:
                    result.pop("activation", None)
                # No firmware update from the iOS compatibility endpoint.
                result["firmware"] = {"version": (result.get("firmware") or {}).get("version", "0.0.0"), "url": ""}
                self.respond(200, result)
            except (ValueError, KeyError, json.JSONDecodeError):
                self.respond(400, {"error": "invalid OTA request"})
            except PermissionError:
                self.respond(403, {"error": "identity conflict"})
            except (error.URLError, TimeoutError, OSError, sqlite3.Error):
                self.respond(503, {"error": "activation temporarily unavailable"})

    return Handler


def main(argv=None):
    cli = argparse.ArgumentParser(description="Owner-approved XiaoZhi activation bridge, not a voice server")
    cli.add_argument("--db", default=os.environ.get("A09_LITE_DB_PATH", DEFAULT_DB))
    sub = cli.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("serve")
    sub.add_parser("approve").add_argument("code")
    sub.add_parser("revoke").add_argument("device_id")
    args = cli.parse_args(argv)
    store = ActivationStore(args.db)
    try:
        if args.command == "init":
            store.initialize()
            print("A09_LITE_INIT_PASS")
        elif args.command == "approve":
            code = sys.stdin.readline().strip() if args.code == "-" else args.code
            device_id = store.approve(code)
            print("A09_LITE_APPROVED: device ending", device_id[-5:])
        elif args.command == "revoke":
            print("A09_LITE_REVOKED: records", store.revoke(args.device_id))
        elif args.command == "serve":
            upstream = validate_origin(os.environ.get("A09_LITE_UPSTREAM", DEFAULT_UPSTREAM))
            wss_url = validate_wss(os.environ.get("A09_LITE_WSS_URL", DEFAULT_WSS))
            if os.environ.get("A09_LITE_DOCKER_INTERNAL") == "1" and not docker_internal():
                raise ValueError("Docker-only mode requires a real container")
            if docker_internal() and (upstream != DOCKER_UPSTREAM or wss_url == DEFAULT_WSS):
                raise ValueError("Docker mode requires fixed A03 service and separate iOS WSS")
            bind_ip = "0.0.0.0" if docker_internal() else "127.0.0.1"
            server = ThreadingHTTPServer((bind_ip, int(os.environ.get("A09_LITE_PORT", "19009"))),
                                         create_handler(store, upstream, wss_url))
            print("A09_LITE_LISTEN: local-only", flush=True)
            server.serve_forever()
    except (ValueError, PermissionError, sqlite3.Error, OSError) as exc:
        print("A09_LITE_BLOCKED:", type(exc).__name__, str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())