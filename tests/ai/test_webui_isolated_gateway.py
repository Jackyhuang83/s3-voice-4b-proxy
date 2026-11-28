"""P1-3-R2: black-box two-Caddy coexistence with only synthetic credentials.

This is NOT a real A04 or physical 4B test. It checks a separate WebUI
gateway cannot serve the original A04 path and vice versa, with positive 101
WS upgrades on both isolated Caddy instances.
"""
import base64
import http.client
import json
import secrets
import time
import unittest

WEBUI_PORT = 19192
LEGACY_PORT = 19193
ORIGIN = "https://voice.example.test"
OWNER = "test-owner-8a1e739ae37e04bc8f53d183d10f35b1"
DEVICE = "02:55:66:77:88:99"
CLIENT = "f1a2b3c4-a1b2-c3d4-e5f6-a1b2c3d4e5f6"
TOKEN = "Bearer synthetic-hmac-token-not-a-real-secret"
PATH_SECRET = "synthetic-path-not-real"

def call(port, method, path, payload=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    h = dict(headers or {})
    if payload is not None:
        h.setdefault("Content-Type", "application/json")
        payload = json.dumps(payload).encode()
    try:
        conn.request(method, path, body=payload, headers=h)
        res = conn.getresponse()
        return res.status, dict(res.getheaders()), res.read() if res.status != 101 else b""
    finally:
        conn.close()

def ws(port, path, extra=None):
    headers = {
        "Connection": "Upgrade",
        "Upgrade": "websocket",
        "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": base64.b64encode(secrets.token_bytes(16)).decode(),
    }
    headers.update(extra or {})
    return call(port, "GET", path, headers=headers)

class TwoGatewayIsolation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for _ in range(100):
            try:
                s, _, body = call(WEBUI_PORT, "GET", "/webui/api/session")
                l, _, _ = call(LEGACY_PORT, "GET", "/")
                if s == 200 and l == 403 and json.loads(body) == {"authenticated": False}:
                    return
            except (ConnectionError, OSError, ValueError):
                pass
            time.sleep(0.3)
        raise RuntimeError("both isolated Caddy instances not ready")

    def login(self):
        status, hdr, _ = call(
            WEBUI_PORT, "POST", "/webui/api/login",
            {"secret": OWNER}, {"Origin": ORIGIN}
        )
        self.assertEqual(200, status)
        cookie = hdr["Set-Cookie"].split(";", 1)[0]
        self.assertTrue(cookie.startswith("__Host-s3voice="))
        return cookie

    def test_01_webui_owner_ws_101_and_header_injection_safe(self):
        cookie = self.login()
        identity_forgery = {
            "Origin": ORIGIN,
            "Cookie": cookie,
            "Authorization": "Bearer attacker",
            "Device-Id": "aa:bb:cc:dd:ee:ff",
            "Client-Id": "11111111-0000-0000-0000-000000000000",
            "X-S3-WS-Authorization": "Bearer attacker",
            "X-S3-WS-Device": "aa:bb:cc:dd:ee:ff",
            "X-S3-WS-Client": "11111111-0000-0000-0000-000000000000",
            "X-S3-Gateway-Secret": "attacker",
        }
        self.assertEqual(101, ws(WEBUI_PORT, "/webui/ws", identity_forgery)[0])

    def test_02_legacy_original_ws_still_101(self):
        identity = {
            "Device-Id": DEVICE,
            "Client-Id": CLIENT,
            "Authorization": TOKEN
        }
        self.assertEqual(
            101,
            ws(LEGACY_PORT, "/xiaozhi/v1/" + PATH_SECRET, identity)[0]
        )

    def test_03_cross_gateway_and_guest_cannot_bypass(self):
        self.assertNotEqual(101, ws(WEBUI_PORT, "/webui/ws", {"Origin": ORIGIN})[0])
        self.assertEqual(403, ws(WEBUI_PORT, "/xiaozhi/v1/" + PATH_SECRET)[0])
        self.assertEqual(403, ws(LEGACY_PORT, "/webui/ws")[0])
        self.assertEqual(403, call(WEBUI_PORT, "GET", "/internal/ws-auth")[0])
        self.assertEqual(403, call(LEGACY_PORT, "GET", "/")[0])
        self.assertEqual(401, call(WEBUI_PORT, "GET", "/webui/api/models")[0])

    def test_04_access_callback_root_redirect_and_query_landing(self):
        # The new gateway, not the original A04 or private auth container,
        # owns the public root redirect after Cloudflare Access OTP.
        status, hdr, body = call(WEBUI_PORT, "GET", "/")
        self.assertEqual(302, status)
        self.assertEqual("/webui/", hdr.get("Location"))
        self.assertNotIn(b"access denied", body.lower())
        for path in ("/webui/", "/webui/?CF_Authorization=synthetic",
                     "/webui?callback=synthetic"):
            with self.subTest(path=path):
                status, hdr, body = call(WEBUI_PORT, "GET", path)
                if path.startswith("/webui?"):
                    self.assertEqual(302, status)
                    self.assertEqual("/webui/", hdr.get("Location"))
                else:
                    self.assertEqual(200, status)
                    self.assertIn("text/html", hdr.get("Content-Type", ""))
                    self.assertIn(b'id="loginView"', body)
        # No broad rewrite: old A04, private API, OTA, static variations
        # and unknown routes stay inaccessible.
        for path in ("/invalid", "/webui/api/models?callback=synthetic",
                     "/internal/ws-auth?callback=synthetic", "/xiaozhi/v1/"):
            self.assertEqual(403, call(WEBUI_PORT, "GET", path)[0])
        self.assertEqual(403, call(LEGACY_PORT, "GET", "/")[0])

    def test_04_legacy_ota_denies_wrong_identity_and_validates_right_one(self):
        data = {
            "application": {"name": "ci", "version": "0.1"},
            "board": {"type": "ci", "name": "fake", "mac": DEVICE},
            "mac_address": DEVICE
        }
        url = "/xiaozhi/ota/" + PATH_SECRET
        wrong = {"Device-Id": "00:00:00:00:00:01", "Client-Id": CLIENT}
        status, _, _ = call(LEGACY_PORT, "POST", url, data, wrong)
        self.assertEqual(403, status)
        good = {"Device-Id": DEVICE, "Client-Id": CLIENT}
        status, _, body = call(LEGACY_PORT, "POST", url, data, good)
        self.assertEqual(200, status)
        self.assertIn(b"synthetic-hmac-token", body)

if __name__ == "__main__":
    unittest.main()
