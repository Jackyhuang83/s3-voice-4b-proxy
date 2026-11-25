"""CI-only fake A03 OTA & HMAC WebSocket upgrade, not an LLM or audio server."""
import base64
import hashlib
import hmac
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = "a09-lite-ci-hmac-key-only"
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body=None):
        data = json.dumps(body).encode() if body else b""
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.server.server_port == 8003:
            if self.path == "/xiaozhi/ota/":
                return self.respond(200, {"healthy": True})
            return self.respond(404)
        if self.path != "/xiaozhi/v1/" or self.headers.get("Upgrade", "").lower() != "websocket":
            return self.respond(403)
        device = self.headers.get("Device-Id", "")
        client = self.headers.get("Client-Id", "")
        auth = self.headers.get("Authorization", "")
        try:
            signed, timestamp = auth.removeprefix("Bearer ").split(".", 1)
            message = f"{client}|{device}|{int(timestamp)}".encode()
            expected = base64.urlsafe_b64encode(hmac.new(KEY.encode(), message, hashlib.sha256).digest()).decode().rstrip("=")
            if not hmac.compare_digest(signed, expected):
                raise ValueError("bad token")
        except (ValueError, TypeError):
            return self.respond(403)
        wskey = self.headers.get("Sec-WebSocket-Key", "")
        if not wskey:
            return self.respond(400)
        answer = base64.b64encode(hashlib.sha1((wskey + GUID).encode()).digest()).decode()
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", answer)
        self.end_headers()
        self.wfile.flush()
        time.sleep(0.2)

    def do_POST(self):
        if self.server.server_port != 8003 or self.path != "/xiaozhi/ota/":
            return self.respond(403)
        device = self.headers.get("Device-Id", "")
        client = self.headers.get("Client-Id", "")
        size = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(size)
        timestamp = int(time.time())
        content = f"{client}|{device}|{timestamp}".encode()
        sig = base64.urlsafe_b64encode(hmac.new(KEY.encode(), content, hashlib.sha256).digest()).decode().rstrip("=")
        self.respond(200, {
            "server_time": {"timestamp": timestamp * 1000},
            "firmware": {"version": "2.6.0", "url": ""},
            "websocket": {"url": "wss://old.example.invalid/xiaozhi/v1/", "token": f"{sig}.{timestamp}"},
        })


def main():
    a = ThreadingHTTPServer(("0.0.0.0", 8003), Handler)
    b = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    threading.Thread(target=a.serve_forever, daemon=True).start()
    b.serve_forever()


if __name__ == "__main__":
    main()