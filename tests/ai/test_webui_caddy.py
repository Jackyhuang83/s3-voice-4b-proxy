"""External isolated Docker CI probes over loopback-only Caddy: no paid calls."""
import base64
import http.client
import json
import os
import secrets
import time
import unittest

PORT = int(os.environ.get("WEBUI_TEST_PORT", "19191"))
ORIGIN = "https://voice.example.test"
OWNER = "test-owner-8a1e739ae37e04bc8f53d183d10f35b1"

def call(method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    hs = dict(headers or {})
    if body is not None:
        hs.setdefault("Content-Type", "application/json")
        body = json.dumps(body).encode()
    conn.request(method, path, body, hs)
    result = conn.getresponse()
    status = result.status
    resp_headers = dict(result.getheaders())
    data = result.read() if status != 101 else b""
    conn.close()
    return status, resp_headers, data

def ws(cookie="", origin=ORIGIN, path="/webui/ws", extra=None):
    hs = {
        "Connection": "Upgrade", "Upgrade": "websocket", "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": base64.b64encode(secrets.token_bytes(16)).decode(),
        "Origin": origin,
    }
    if cookie:
        hs["Cookie"] = cookie
    hs.update(extra or {})
    return call("GET", path, headers=hs)

class CaddyContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for _ in range(35):
            try:
                status, _, _ = call("GET", "/bad")
                if status == 404: break
            except (ConnectionError, OSError):
                pass
            time.sleep(0.25)
        else:
            raise RuntimeError("isolated caddy did not start")

    def login(self):
        status, headers, body = call("POST","/webui/api/login",{"secret":OWNER},{"Origin":ORIGIN})
        self.assertEqual(status, 200, body)
        cookie=headers["Set-Cookie"].split(";",1)[0]
        self.assertTrue(cookie.startswith("__Host-s3voice="))
        return cookie

    def test_01_missing_cookie_wrong_origin_and_urls_rejected(self):
        self.assertNotEqual(101, ws()[0])
        cookie=self.login()
        self.assertEqual(403,ws(cookie=cookie,origin="https://attacker.invalid")[0])
        self.assertNotEqual(101,ws(cookie=cookie,path="/webui/ws?authorization=Bearer+bad")[0])
        self.assertEqual(404,ws(cookie=cookie,path="/xiaozhi/v1/")[0])
        self.assertEqual(404,call("POST","/xiaozhi/ota/", {})[0])
        self.assertEqual(404,call("GET","/internal/ws-auth")[0])

    def test_02_valid_owner_can_ws_and_upstream_accepts_only_server_identity(self):
        cookie=self.login()
        status, _, _=ws(cookie=cookie)
        self.assertEqual(101,status)
        # The upstream mock requires the right original A03 HMAC token and ID.
        # An attacker trying to inject direct headers must be overwritten/stripped.
        spoof={
            "Authorization":"Bearer forged-admin-token",
            "Device-Id":"aa:bb:cc:dd:ee:ff",
            "Client-Id":"00000000-0000-0000-0000-000000000000",
            "X-S3-WS-Authorization":"Bearer forged-admin-token",
            "X-S3-WS-Device":"aa:bb:cc:dd:ee:ff",
            "X-S3-WS-Client":"00000000-0000-0000-0000-000000000000",
            "X-S3-Gateway-Secret":"attacker-controlled",
        }
        status,_,_=ws(cookie=cookie,extra=spoof)
        self.assertEqual(101,status,"client identity headers must be stripped before forward_auth")

    def test_03_logout_revokes_browser_ws_without_affecting_device_routes(self):
        cookie=self.login()
        self.assertEqual(101,ws(cookie=cookie)[0])
        self.assertEqual(200,call("POST","/webui/api/logout",headers={"Origin":ORIGIN,"Cookie":cookie})[0])
        self.assertEqual(403,ws(cookie=cookie)[0])
        self.assertEqual(404,call("GET","/xiaozhi/ota/not-a-webui-secret")[0])

    def test_04_bad_login_fail_closed(self):
        self.assertEqual(403,call("POST","/webui/api/login",{"secret":OWNER})[0])
        self.assertEqual(401,call("POST","/webui/api/login",{"secret":"bad"},{"Origin":ORIGIN})[0])

if __name__ == "__main__":
    unittest.main()
