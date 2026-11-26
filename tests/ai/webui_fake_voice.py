"""Disposable OTA + WebSocket HTTP handshake mock used ONLY in CI."""
import hashlib
import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEVICE = "02:55:66:77:88:99"
CLIENT = "f1a2b3c4-a1b2-c3d4-e5f6-a1b2c3d4e5f6"
TOKEN = "synthetic-hmac-token-not-a-real-secret"

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass
    def do_POST(self):
        if self.server.server_port != 8003 or self.path != "/xiaozhi/ota/":
            self.send_error(404); return
        size = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(size))
        except Exception:
            self.send_error(400); return
        if (self.headers.get("Device-Id") != DEVICE or self.headers.get("Client-Id") != CLIENT
                or body.get("board", {}).get("mac") != DEVICE):
            self.send_error(403); return
        payload = json.dumps({"websocket": {"url": "ws://upstream:8000/xiaozhi/v1/", "token": TOKEN}, "firmware": {"url": ""}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload))); self.end_headers(); self.wfile.write(payload)
    def do_GET(self):
        if self.server.server_port != 8000 or self.path != "/xiaozhi/v1/":
            self.send_error(404); return
        if (self.headers.get("Device-Id") != DEVICE or self.headers.get("Client-Id") != CLIENT or
                self.headers.get("Authorization") != "Bearer " + TOKEN or
                self.headers.get("Cookie") or self.headers.get("Origin")):
            self.send_error(403); return
        if self.headers.get("Upgrade", "").lower() != "websocket":
            self.send_error(400); return
        key = self.headers.get("Sec-WebSocket-Key", "")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
        self.send_response(101, "Switching Protocols")
        self.send_header("Connection", "Upgrade")
        self.send_header("Upgrade", "websocket")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        # The connector probes successful HTTP 101 only; no audio frames here.

def main():
    servers = [ThreadingHTTPServer(("0.0.0.0", port), Fake) for port in (8000, 8003)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    threading.Event().wait()

if __name__ == "__main__":
    main()
