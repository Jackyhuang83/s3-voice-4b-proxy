#!/usr/bin/env python3
"""P1-1 only: owner session and browser-to-A03 WS handshake credentials.

This is NOT a WebSocket proxy, device OTA endpoint, speech engine or production
installer. Place behind isolated Caddy on a private Docker network. No host
ports should be published by the auth container; Caddy strips all untrusted
identity headers before its forward_auth copy_headers step.
"""

import argparse
import hmac
import http.cookies
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import importlib.util
from pathlib import Path

# Load sibling text-only helper by its exact trusted path, so tests importing
# this script with importlib behave exactly like the live stdlib container.
_text_spec = importlib.util.spec_from_file_location("s3_webui_text", Path(__file__).with_name("webui_text.py"))
webui_text = importlib.util.module_from_spec(_text_spec)
_text_spec.loader.exec_module(webui_text)

COOKIE_NAME = "__Host-s3voice"
MAX_BODY = 4096
SESSION_TTL_SECONDS = 1800
MAX_SESSIONS = 8
MAX_FAILURES = 8
FAILURE_WINDOW_SECONDS = 60


class Config:
    def __init__(self, env):
        self.origin = env.get("S3_WEBUI_ORIGIN", "")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.path or
                parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise ValueError("S3_WEBUI_ORIGIN must be one https://origin without path")
        self.owner_secret = env.get("S3_WEBUI_OWNER_SECRET", "")
        self.gateway_secret = env.get("S3_WEBUI_GATE_SECRET", "")
        for label, value in (("owner", self.owner_secret), ("gateway", self.gateway_secret)):
            if len(value) < 32 or any(ch in value for ch in "\r\n"):
                raise ValueError(label + " secret must be at least 32 characters")
        self.device_id = env.get("S3_WEBUI_DEVICE_ID", "")
        self.client_id = env.get("S3_WEBUI_CLIENT_ID", "")
        # Distinct identity provisioned for the web browser; never share 4B MAC/UUID.
        import re
        if not re.fullmatch(r"[0-9a-f]{2}(?::[0-9a-f]{2}){5}", self.device_id):
            raise ValueError("missing dedicated lowercase webui device id")
        if not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", self.client_id):
            raise ValueError("missing dedicated webui client id")
        self.ota = env.get("S3_WEBUI_UPSTREAM_OTA", "")
        u = urlsplit(self.ota)
        if (u.scheme != "http" or u.path != "/xiaozhi/ota/" or u.query or u.fragment or
                u.username or u.password or u.netloc not in ("127.0.0.1:18003", "s3-voice-ai-server:8003", "upstream:8003")):
            raise ValueError("OTA must be an explicitly allowed private A03 endpoint")
        self.bind = env.get("S3_WEBUI_BIND", "127.0.0.1")
        if self.bind not in ("127.0.0.1", "0.0.0.0"):
            raise ValueError("invalid bind interface")
        self.port = int(env.get("S3_WEBUI_PORT", "19011"))
        if not 1 <= self.port <= 65535:
            raise ValueError("invalid port")
        self.models = webui_text.read_catalog(env)


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}
        self.failures = deque()

    def active(self, cookie):
        # Compare secrets even for nonexistent cookies; don't log cookie values.
        if not cookie:
            return False
        with self.lock:
            now = time.monotonic()
            for token, deadline in list(self.sessions.items()):
                if deadline <= now:
                    del self.sessions[token]
            return any(hmac.compare_digest(cookie, token) for token in self.sessions)

    def too_many(self):
        with self.lock:
            now = time.monotonic()
            while self.failures and self.failures[0] + FAILURE_WINDOW_SECONDS < now:
                self.failures.popleft()
            return len(self.failures) >= MAX_FAILURES

    def fail(self):
        with self.lock:
            self.failures.append(time.monotonic())

    def issue(self):
        token = secrets.token_urlsafe(32)
        with self.lock:
            now = time.monotonic()
            self.sessions = {k: v for k, v in self.sessions.items() if v > now}
            if len(self.sessions) >= MAX_SESSIONS:
                # Fail closed: don't evict active users merely because a new login arrived.
                return None
            self.sessions[token] = now + SESSION_TTL_SECONDS
        return token

    def revoke(self, token):
        with self.lock:
            for stored in list(self.sessions):
                if hmac.compare_digest(token, stored):
                    del self.sessions[stored]


class AuthHandler(BaseHTTPRequestHandler):
    server_version = "S3VoiceWebui/0.2"
    sys_version = ""

    def log_message(self, *_):
        # Never log paths, identities, cookies, passwords or A03 bearer tokens.
        pass

    def respond(self, status, payload=None, headers=()):
        raw = json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def origin_ok(self):
        return self.headers.get("Origin", "") == self.server.cfg.origin

    def cookie(self):
        try:
            jar = http.cookies.SimpleCookie()
            jar.load(self.headers.get("Cookie", ""))
            morsel = jar.get(COOKIE_NAME)
            return morsel.value if morsel else ""
        except http.cookies.CookieError:
            return ""

    def deny(self, status=403):
        self.respond(status, {"error": "access denied"})

    def do_GET(self):
        if self.path == "/webui/api/session":
            self.respond(200, {"authenticated": self.server.state.active(self.cookie())})
        elif self.path == "/internal/ws-auth":
            self.ws_auth()
        elif self.path == "/webui/api/models":
            webui_text.visible_models(self)
        elif webui_text.static_target(self.path) is not None:
            webui_text.serve_static(self)
        else:
            self.deny(404)

    def do_POST(self):
        if not self.origin_ok():
            return self.deny()
        if self.path == "/webui/api/login":
            if self.server.state.too_many():
                return self.deny(429)
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                return self.deny(415)
            try:
                size = int(self.headers.get("Content-Length", "-1"))
                if not (0 < size <= MAX_BODY):
                    return self.deny(413)
                obj = json.loads(self.rfile.read(size))
                credential = obj.get("secret", "") if isinstance(obj, dict) else ""
                if not isinstance(credential, str):
                    return self.deny()
            except (ValueError, UnicodeDecodeError):
                return self.deny(400)
            if not hmac.compare_digest(credential, self.server.cfg.owner_secret):
                self.server.state.fail()
                return self.deny(401)
            cookie = self.server.state.issue()
            if cookie is None:
                return self.deny(429)
            self.respond(200, {"authenticated": True}, [("Set-Cookie", f"{COOKIE_NAME}={cookie}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age={SESSION_TTL_SECONDS}")])
        elif self.path == "/webui/api/logout":
            self.server.state.revoke(self.cookie())
            self.respond(200, {"authenticated": False}, [("Set-Cookie", f"{COOKIE_NAME}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0")])
        elif self.path == "/webui/api/chat":
            webui_text.forward_text(self)
        else:
            self.deny(404)

    def ws_auth(self):
        cfg = self.server.cfg
        if not hmac.compare_digest(self.headers.get("X-S3-Gateway-Secret", ""), cfg.gateway_secret):
            return self.deny()
        if not self.origin_ok() or not self.server.state.active(self.cookie()):
            return self.deny()
        if self.headers.get("X-Forwarded-Method") != "GET" or self.headers.get("X-Forwarded-Uri") != "/webui/ws":
            return self.deny()
        # Only auth service may request A03 OTA. No browser-facing OTA or token API.
        payload = json.dumps({
            "application": {"name": "s3-webui", "version": "1.0.0"},
            "board": {"type": "web", "name": "s3-voice-webui", "mac": cfg.device_id},
            "mac_address": cfg.device_id,
        }).encode()
        request = urllib.request.Request(cfg.ota, data=payload, method="POST", headers={
            "Content-Type": "application/json", "Device-Id": cfg.device_id,
            "Client-Id": cfg.client_id,
        })
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as result:
                if result.status != 200:
                    raise ValueError("upstream rejected")
                response_bytes = result.read(32769)
                if len(response_bytes) > 32768:
                    raise ValueError("too much upstream data")
            answer = json.loads(response_bytes)
            token = answer["websocket"]["token"]
            if not (isinstance(token, str) and 8 <= len(token) <= 2048 and
                    all(c not in token for c in "\r\n\x00")):
                raise ValueError("invalid upstream token")
        except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError):
            # Fail closed, no exception content / secrets in output.
            return self.deny(503)
        bearer = token if token.startswith("Bearer ") else "Bearer " + token
        self.respond(200, {}, [
            ("X-S3-WS-Authorization", bearer),
            ("X-S3-WS-Device", cfg.device_id),
            ("X-S3-WS-Client", cfg.client_id),
        ])


class AuthServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, cfg):
        super().__init__(address, AuthHandler)
        self.cfg = cfg
        self.state = State()


def main():
    parser = argparse.ArgumentParser(description="Isolated owner auth for S3 Voice WebUI")
    parser.add_argument("mode", choices=["check", "serve"])
    mode = parser.parse_args().mode
    cfg = Config(os.environ)
    if mode == "check":
        print("WEBUI_P1_AUTH_CONFIG_PASS: origin, private OTA, distinct identity, secrets present")
        return
    with AuthServer((cfg.bind, cfg.port), cfg) as server:
        server.serve_forever(poll_interval=0.25)


if __name__ == "__main__":
    main()
