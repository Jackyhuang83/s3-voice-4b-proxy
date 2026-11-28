"""stdlib-only tests, never touch real VPS, browser or paid API."""
import http.client
import importlib.util
import json
import pathlib
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("webui_auth", ROOT / "tools/ai/webui_auth.py")
webui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(webui)

DEVICE = "02:55:66:77:88:99"
CLIENT = "f1a2b3c4-a1b2-c3d4-e5f6-a1b2c3d4e5f6"
OWNER = "test-owner-8a1e739ae37e04bc8f53d183d10f35b1"
GATE = "test-gateway-d19d03c217adcdbccf101bf128a2201c"
ORIGIN = "https://voice.example.test"
TOKEN = "test-hmac-upstream-token-unchanged"

def cfg_env():
    return {
        "S3_WEBUI_ORIGIN": ORIGIN,
        "S3_WEBUI_OWNER_SECRET": OWNER,
        "S3_WEBUI_GATE_SECRET": GATE,
        "S3_WEBUI_DEVICE_ID": DEVICE,
        "S3_WEBUI_CLIENT_ID": CLIENT,
        "S3_WEBUI_UPSTREAM_OTA": "http://127.0.0.1:18003/xiaozhi/ota/",
    }

class FakeOTA(BaseHTTPRequestHandler):
    should_fail = False
    def log_message(self, *_):
        pass
    def do_POST(self):
        size = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(size))
        if not self.path == "/xiaozhi/ota/":
            self.send_error(404);return
        if self.should_fail:
            self.send_response(503);self.end_headers();return
        if (self.headers.get("Device-Id") != DEVICE or self.headers.get("Client-Id") != CLIENT or
                data.get("mac_address") != DEVICE):
            self.send_response(403);self.end_headers();return
        payload = json.dumps({"websocket":{"url":"ws://invalid.local/xiaozhi/v1/", "token": TOKEN}}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers();self.wfile.write(payload)

class SecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ota = ThreadingHTTPServer(("127.0.0.1", 0), FakeOTA)
        cls.ota_thread = threading.Thread(target=cls.ota.serve_forever, daemon=True)
        cls.ota_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.ota.shutdown();cls.ota.server_close()

    def setUp(self):
        self.config = webui.Config(cfg_env())
        self.config.ota = f"http://127.0.0.1:{self.ota.server_port}/xiaozhi/ota/"
        self.app = webui.AuthServer(("127.0.0.1", 0), self.config)
        self.runner = threading.Thread(target=self.app.serve_forever, daemon=True)
        self.runner.start()

    def tearDown(self):
        self.app.shutdown();self.app.server_close()
        FakeOTA.should_fail = False

    def req(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.app.server_port, timeout=4)
        try:
            request_headers = dict(headers or {})
            if data is not None:
                request_headers.setdefault("Content-Type", "application/json")
                data = json.dumps(data).encode()
            conn.request(method, path, body=data, headers=request_headers)
            result = conn.getresponse()
            return (result.status, dict(result.getheaders()), result.read())
        finally:
            conn.close()

    def login(self):
        status, headers, _ = self.req("POST", "/webui/api/login", {"secret": OWNER}, {"Origin": ORIGIN})
        self.assertEqual(200, status)
        self.assertIn("__Host-s3voice=", headers["Set-Cookie"])
        self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("Secure", headers["Set-Cookie"])
        self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def auth_headers(self, cookie, **extra):
        return {"Origin": ORIGIN, "Cookie": cookie,
                "X-S3-Gateway-Secret": GATE, "X-Forwarded-Method": "GET",
                "X-Forwarded-Uri": "/webui/ws", **extra}

    def test_config_rejects_unsafe_origin_and_identity(self):
        for key, bad in (("S3_WEBUI_ORIGIN", "http://voice.example.test"),
                         ("S3_WEBUI_ORIGIN", "https://voice.example.test/path"),
                         ("S3_WEBUI_UPSTREAM_OTA", "http://evil.test/xiaozhi/ota/"),
                         ("S3_WEBUI_DEVICE_ID", ""),
                         ("S3_WEBUI_CLIENT_ID", ""),
                         ("S3_WEBUI_OWNER_SECRET", "short"),
                         ("S3_WEBUI_GATE_SECRET", "short")):
            with self.subTest(key=key, bad=bad):
                env = cfg_env();env[key] = bad
                with self.assertRaises(ValueError):
                    webui.Config(env)

    def test_private_auth_not_public_token_api(self):
        for path in ("/", "/xiaozhi/ota/", "/webui/api/token", "/internal/health"):
            status, _, _ = self.req("GET", path)
            self.assertEqual(404, status)
        status, _, body = self.req("GET", "/webui/api/session")
        self.assertEqual((200, False), (status, json.loads(body)["authenticated"]))
        self.assertEqual(403, self.req("GET", "/internal/ws-auth")[0])

    def test_access_callback_landing_query_only_and_strict_protected_routes(self):
        # The public login shell is always reachable without an owner cookie,
        # even if Cloudflare Access returns to it with a query suffix.
        for path in ("/webui/", "/webui/?CF_Authorization=synthetic",
                     "/webui/?returnTo=%2Fwebui%2F"):
            with self.subTest(path=path):
                status, hdr, body = self.req("GET", path)
                self.assertEqual(200, status)
                self.assertIn("text/html", hdr.get("Content-Type", ""))
                self.assertIn(b'id="loginView"', body)
                self.assertNotIn(b"synthetic", body)
        status, hdr, body = self.req("GET", "/webui?code=private-example")
        self.assertEqual(302, status)
        self.assertEqual("/webui/", hdr.get("Location"))
        self.assertNotIn(b"private-example", body)

        # Still fail closed on all APIs, WebSocket handshakes and unknown
        # paths, even when supplied the same Access-like query string.
        for path in ("/", "/?code=example", "/webui/api/session?code=x",
                     "/webui/api/models?code=x", "/internal/ws-auth?code=x",
                     "/webui/api/login?code=x",
                     "/webui/audio-ui.mjs?code=x", "/webui/unknown?code=x"):
            with self.subTest(path=path):
                self.assertEqual(404, self.req("GET", path)[0])
        self.assertEqual(404, self.req("POST", "/webui/api/login?code=x",
                                        {"secret": OWNER}, {"Origin": ORIGIN})[0])

    def test_login_fail_closed_csrf_expiry_and_logout(self):
        self.assertEqual(403, self.req("POST", "/webui/api/login", {"secret":OWNER})[0])
        self.assertEqual(403, self.req("POST", "/webui/api/login", {"secret":OWNER}, {"Origin":"https://evil.example"})[0])
        self.assertEqual(401, self.req("POST", "/webui/api/login", {"secret":"wrong"}, {"Origin":ORIGIN})[0])
        cookie = self.login()
        self.assertTrue(json.loads(self.req("GET", "/webui/api/session", headers={"Cookie":cookie})[2])["authenticated"])
        good = self.auth_headers(cookie)
        status, auth_headers, _ = self.req("GET", "/internal/ws-auth", headers=good)
        self.assertEqual(200, status)
        self.assertEqual("Bearer " + TOKEN, auth_headers.get("X-S3-WS-Authorization"))
        self.assertEqual(DEVICE, auth_headers.get("X-S3-WS-Device"))
        self.assertEqual(CLIENT, auth_headers.get("X-S3-WS-Client"))
        # Secret must never appear in browser API replies.
        self.assertNotIn(TOKEN.encode(), self.req("GET", "/webui/api/session", headers={"Cookie":cookie})[2])
        self.assertEqual(403, self.req("POST", "/webui/api/logout", headers={"Cookie":cookie})[0])
        self.assertEqual(200, self.req("POST", "/webui/api/logout", headers={"Cookie":cookie,"Origin":ORIGIN})[0])
        self.assertEqual(403, self.req("GET", "/internal/ws-auth", headers=good)[0])

    def test_gateway_secret_origin_path_headers_required(self):
        cookie = self.login()
        headers = self.auth_headers(cookie)
        for bad in ({"X-S3-Gateway-Secret": "attacker"},
                    {"Origin":"https://evil.example"},
                    {"X-Forwarded-Method":"POST"},
                    {"X-Forwarded-Uri":"/webui/ws?authorization=secret"},
                    {"Cookie":"__Host-s3voice=forged"}):
            with self.subTest(bad=bad):
                modified = {**headers, **bad}
                self.assertEqual(403, self.req("GET", "/internal/ws-auth", headers=modified)[0])
        self.assertEqual(200, self.req("GET", "/internal/ws-auth", headers=headers)[0])

    def test_ota_network_failure_is_503_no_secret(self):
        cookie = self.login()
        FakeOTA.should_fail = True
        status, headers, body = self.req("GET", "/internal/ws-auth", headers=self.auth_headers(cookie))
        self.assertEqual(503, status)
        self.assertNotIn(TOKEN.encode(), body)
        self.assertNotIn("X-S3-WS-Authorization", headers)

    def test_wrong_password_attempts_are_rate_limited(self):
        for i in range(webui.MAX_FAILURES):
            self.assertEqual(401, self.req("POST", "/webui/api/login", {"secret":"bad"}, {"Origin":ORIGIN})[0])
        self.assertEqual(429, self.req("POST", "/webui/api/login", {"secret":OWNER}, {"Origin":ORIGIN})[0])

    def test_expired_session_rejected(self):
        cookie = self.login()
        token = cookie.split("=",1)[1]
        with self.app.state.lock:
            self.app.state.sessions[token] = 0
        self.assertEqual(403,self.req("GET","/internal/ws-auth",headers=self.auth_headers(cookie))[0])

if __name__ == "__main__":
    unittest.main()
