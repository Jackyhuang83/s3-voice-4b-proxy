"""P1-2 low-cost, text-only OpenAI-compatible Chat Completions broker.

Reuses the existing A05 provider wire contract (/v1/chat/completions, SSE).
No separate LLM, no ASR, no TTS, no public provider API key, no extra daemon.
Only the owner can call this module via the P1-1 authenticated handler.
"""

import ipaddress
import json
import os
import pathlib
import re
import stat
import threading
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2] / "webui"
FILES = {
    "/webui/": ("index.html", "text/html; charset=utf-8"),
    "/webui/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/webui/app.css": ("app.css", "text/css; charset=utf-8"),
    "/webui/audio-opus.mjs": ("audio-opus.mjs", "text/javascript; charset=utf-8"),
    "/webui/audio-ui.mjs": ("audio-ui.mjs", "text/javascript; charset=utf-8"),
    "/webui/audio-worklet.js": ("audio-worklet.js", "text/javascript; charset=utf-8"),
    "/webui/vendor/libopus/dist/index.js": ("vendor/libopus/dist/index.js", "text/javascript; charset=utf-8"),
    "/webui/vendor/libopus/dist/generated/libopus.generated.mjs": ("vendor/libopus/dist/generated/libopus.generated.mjs", "text/javascript; charset=utf-8"),
}
MAX_REQUEST_BYTES = 32768
MAX_HISTORY = 20
MAX_CONTENT = 2000
MAX_TOTAL_CONTENT = 24000
MAX_OUTPUT_BYTES = 80000
# At most two simultaneous external API streams, minimizing surprise spend.
SLOTS = threading.BoundedSemaphore(2)


def validate_catalog(items):
    if not isinstance(items, list) or not (0 <= len(items) <= 4):
        raise ValueError("model catalog must contain 0-4 entries")
    result = {}
    for obj in items:
        if not isinstance(obj, dict):
            raise ValueError("model entry must be an object")
        identity = obj.get("id")
        label = obj.get("label")
        model = obj.get("model")
        base = obj.get("base_url")
        key = obj.get("api_key")
        if not isinstance(identity, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,23}", identity):
            raise ValueError("invalid model alias")
        if not isinstance(label, str) or not (1 <= len(label) <= 60):
            raise ValueError("invalid model label")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,128}", model):
            raise ValueError("invalid model id")
        if not isinstance(key, str) or not (8 <= len(key) <= 2048) or any(ord(c) < 33 or ord(c) > 126 for c in key):
            raise ValueError("invalid private API key")
        if not isinstance(base, str) or len(base) > 400:
            raise ValueError("invalid base URL")
        parsed = urllib.parse.urlsplit(base)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or
                parsed.fragment or parsed.query or parsed.port not in (None, 443) or
                parsed.path.rstrip("/") not in ("/v1", "")):
            raise ValueError("model provider must use approved HTTPS /v1 endpoint")
        hostname = parsed.hostname
        if hostname.lower() in ("localhost", "localhost.localdomain") or hostname.endswith(".local"):
            raise ValueError("private model provider host denied")
        try:
            ip = ipaddress.ip_address(hostname)
            if not ip.is_global:
                raise ValueError("nonpublic model provider address denied")
        except ValueError as e:
            if str(e).endswith("denied"):
                raise
        if identity in result:
            raise ValueError("duplicate model alias")
        result[identity] = {
            "id": identity, "label": label, "model": model,
            "base_url": base.rstrip("/"), "api_key": key
        }
    return result


def read_catalog(env):
    path = env.get("S3_WEBUI_MODELS_FILE", "")
    if not path:
        return {}
    if not pathlib.Path(path).is_absolute() or not (
        path.startswith("/run/secrets/") or
        path.startswith("/opt/s3-voice-webui/private/")
    ):
        raise ValueError("model catalog path must be under approved private directory")
    info = os.stat(path)
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("model catalog must be a private regular file")
    if info.st_size > 16384:
        raise ValueError("model catalog too large")
    return validate_catalog(json.loads(pathlib.Path(path).read_text(encoding="utf-8")))


def serve_static(handler):
    if handler.path == "/webui":
        handler.send_response(302)
        handler.send_header("Location", "/webui/")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    if handler.path not in FILES:
        return handler.deny(404)
    relative, mime = FILES[handler.path]
    try:
        content = (ROOT / relative).read_bytes()
    except OSError:
        return handler.deny(503)
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("X-Frame-Options", "DENY")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Content-Security-Policy",
        "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
        "form-action 'self'; object-src 'none'; frame-ancestors 'none'")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def visible_models(handler):
    if not handler.server.state.active(handler.cookie()):
        return handler.deny(401)
    handler.respond(200, {"models": [
        {"id": model["id"], "label": model["label"]}
        for model in handler.server.cfg.models.values()
    ]})


def check_messages(data, models):
    if not isinstance(data, dict):
        raise ValueError("invalid object")
    identity = data.get("model")
    if not isinstance(identity, str) or identity not in models:
        raise ValueError("unknown model")
    messages = data.get("messages")
    if not isinstance(messages, list) or not (1 <= len(messages) <= MAX_HISTORY):
        raise ValueError("invalid history length")
    total = 0
    cleaned = []
    for item in messages:
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ValueError("invalid role")
        content = item.get("content")
        if not isinstance(content, str) or not (1 <= len(content) <= MAX_CONTENT):
            raise ValueError("invalid message length")
        total += len(content)
        if total > MAX_TOTAL_CONTENT:
            raise ValueError("history too large")
        cleaned.append({"role": item["role"], "content": content})
    if cleaned[-1]["role"] != "user":
        raise ValueError("last message must be user")
    return models[identity], cleaned


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        # An upstream redirect must never forward the private bearer key.
        return None


def forward_text(handler):
    if not handler.server.state.active(handler.cookie()):
        return handler.deny(401)
    if handler.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
        return handler.deny(415)
    try:
        length = int(handler.headers.get("Content-Length", "-1"))
        if not 0 < length <= MAX_REQUEST_BYTES:
            return handler.deny(413)
        obj = json.loads(handler.rfile.read(length))
        model, messages = check_messages(obj, handler.server.cfg.models)
    except (ValueError, UnicodeDecodeError, TypeError):
        return handler.deny(400)

    if not SLOTS.acquire(blocking=False):
        return handler.deny(429)
    try:
        payload = json.dumps({
            "model": model["model"], "messages": messages,
            "stream": True, "max_tokens": 1024
        }, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        req = urllib.request.Request(
            model["base_url"] + "/chat/completions",
            data=payload,
            headers={
                "Authorization": "Bearer " + model["api_key"],
                "Content-Type": "application/json", "Accept": "text/event-stream"
            },
            method="POST"
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            upstream = opener.open(req, timeout=20)
        except (OSError, urllib.error.HTTPError):
            return handler.deny(503)
        with upstream:
            if upstream.status != 200 or "text/event-stream" not in upstream.headers.get("Content-Type", "").lower():
                return handler.deny(503)
            handler.send_response(200)
            handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
            handler.send_header("Cache-Control", "no-store, no-transform")
            handler.send_header("X-Content-Type-Options", "nosniff")
            handler.send_header("X-Accel-Buffering", "no")
            handler.send_header("Referrer-Policy", "no-referrer")
            handler.send_header("Connection", "close")
            handler.end_headers()
            handler.close_connection = True

            sent = 0
            read = 0
            finished = False
            for line in upstream:
                read += len(line)
                if read > MAX_OUTPUT_BYTES or len(line) > 16384:
                    break
                if not line.startswith(b"data:"):
                    continue
                raw = line[5:].strip()
                if raw == b"[DONE]":
                    finished = True
                    break
                try:
                    event = json.loads(raw)
                    delta = event["choices"][0].get("delta", {}).get("content")
                except (ValueError, TypeError, KeyError, IndexError):
                    break
                if not isinstance(delta, str) or len(delta) > 4096:
                    if delta is None:
                        continue
                    break
                sent += len(delta)
                if sent > 50000:
                    break
                data = json.dumps({"delta": delta}, ensure_ascii=False)
                handler.wfile.write(("data: " + data + "\n\n").encode("utf-8"))
                handler.wfile.flush()
            if finished and sent:
                handler.wfile.write(b"data: [DONE]\n\n")
                handler.wfile.flush()
            else:
                handler.wfile.write(b'data: {"error":"stream_interrupted"}\n\n')
                handler.wfile.flush()
    except (OSError, ValueError, TypeError):
        # No provider error string, bearer key or user text goes to logs.
        # Once SSE starts, terminate without [DONE] on unexpected failures.
        pass
    finally:
        SLOTS.release()
