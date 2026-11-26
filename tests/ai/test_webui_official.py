"""Official pinned A03 integration: no model, microphone, firmware or paid calls."""
import base64
import http.client
import importlib.util
import json
import pathlib
import secrets
import socket
import threading
import unittest

HERE = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("webui_auth", HERE / "tools/ai/webui_auth.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)

ORIGIN = "https://voice.example.test"
OWNER = "official-a03-ci-only-owner-f4f7c29f2c42e136"
GATE = "official-a03-ci-only-gate-5bff9fa191d8cdce"
DEVICE = "02:90:12:34:56:78"
CLIENT = "11111111-2222-4333-8444-555555555556"

class OfficialA03(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cfg = web.Config({
            "S3_WEBUI_ORIGIN": ORIGIN,
            "S3_WEBUI_OWNER_SECRET": OWNER,
            "S3_WEBUI_GATE_SECRET": GATE,
            "S3_WEBUI_DEVICE_ID": DEVICE,
            "S3_WEBUI_CLIENT_ID": CLIENT,
            "S3_WEBUI_UPSTREAM_OTA": "http://127.0.0.1:18003/xiaozhi/ota/",
        })
        cls.auth = web.AuthServer(("127.0.0.1", 0), cfg)
        cls.worker = threading.Thread(target=cls.auth.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.auth.shutdown(); cls.auth.server_close()

    def req(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.auth.server_port, timeout=8)
        try:
            hs = dict(headers or {})
            if body is not None:
                hs["Content-Type"] = "application/json"
                body = json.dumps(body).encode()
            conn.request(method, path, body, hs)
            r=conn.getresponse()
            return r.status, dict(r.getheaders()), r.read()
        finally:
            conn.close()

    def handshake(self, authorization):
        sock = socket.create_connection(("127.0.0.1", 18000), timeout=8)
        sock.settimeout(8)
        try:
            key = base64.b64encode(secrets.token_bytes(16)).decode()
            lines = [
                "GET /xiaozhi/v1/ HTTP/1.1", "Host: 127.0.0.1:18000",
                "Connection: Upgrade", "Upgrade: websocket",
                "Sec-WebSocket-Version: 13", "Sec-WebSocket-Key: " + key,
                "Protocol-Version: 1", "Device-Id: " + DEVICE,
                "Client-Id: " + CLIENT, "Authorization: " + authorization,
                "", "",
            ]
            sock.sendall("\r\n".join(lines).encode())
            response = sock.recv(4096).split(b"\r\n", 1)[0]
            return int(response.split()[1])
        finally:
            sock.close()

    def test_official_ota_signed_ws_token_roundtrip(self):
        status, headers, _ = self.req("POST", "/webui/api/login", {"secret": OWNER}, {"Origin": ORIGIN})
        self.assertEqual(200, status)
        cookie = headers["Set-Cookie"].split(";",1)[0]
        status, headers, _ = self.req("GET", "/internal/ws-auth", headers={
            "Origin": ORIGIN, "Cookie": cookie,
            "X-Forwarded-Method": "GET", "X-Forwarded-Uri": "/webui/ws",
            "X-S3-Gateway-Secret": GATE,
        })
        self.assertEqual(200,status)
        token = headers.get("X-S3-WS-Authorization", "")
        self.assertTrue(token.startswith("Bearer ") and len(token)>40)
        self.assertEqual(DEVICE,headers.get("X-S3-WS-Device"))
        self.assertEqual(CLIENT,headers.get("X-S3-WS-Client"))
        self.assertEqual(101,self.handshake(token))
        print("WEBUI_P1_REAL_A03_PASS: official v0.9.8 OTA token and WS 101, no paid models")

if __name__ == "__main__":
    unittest.main()
