"""A09-Lite contract tests: stdlib, ephemeral servers, zero VPS/AI changes."""
import importlib.util
import json
import os
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("a09_lite", ROOT / "tools/ai/a09_lite.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

D1 = "02:23:45:67:89:ab"
C1 = "c54d9471-484d-4b53-89b8-42ec88d735af"
D2 = "02:bc:de:fa:12:34"
C2 = "cd5d9471-484d-4b53-89b8-42ec88d735ab"
WS_URL = "wss://ios.example.test/xiaozhi/v1/private-scope"
TOKEN = "valid-hmac-token-from-real-upstream"


class FakeUpstream(BaseHTTPRequestHandler):
    response = None
    requests = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        size = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(size)
        type(self).requests.append((self.path, self.headers.get("Device-Id"), self.headers.get("Client-Id")))
        data = type(self).response or {
            "server_time": {"timestamp": 1000, "timezone_offset": 480},
            "firmware": {"version": "2.6.0", "url": "https://should-not-reach-device.invalid/update.bin"},
            "websocket": {"url": "wss://voice.example.test/xiaozhi/v1/old-scope", "token": TOKEN},
        }
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def run_server(handler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, f"http://127.0.0.1:{server.server_port}"


class ActivationContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [100000]
        self.store = mod.ActivationStore(pathlib.Path(self.tmp.name) / "db.sqlite", now=lambda: self.now[0])
        self.store.initialize()
        FakeUpstream.response = None
        FakeUpstream.requests = []
        self.upstream_server, self.upstream_url = run_server(FakeUpstream)
        self.adapter_server, self.adapter_url = run_server(
            mod.create_handler(self.store, self.upstream_url + "/xiaozhi/ota/", WS_URL))
        self.opener = request.build_opener(request.ProxyHandler({}))

    def tearDown(self):
        for server in [self.adapter_server, self.upstream_server]:
            server.shutdown()
            server.server_close()
        self.tmp.cleanup()

    def call(self, path="/xiaozhi/ota/", device=D1, client=C1, body=b'{"application":{"version":"2.6.0"}}', method="POST"):
        headers = {"Device-Id": device, "Client-Id": client, "Content-Type": "application/json"}
        req = request.Request(self.adapter_url + path, headers=headers, data=body if method == "POST" else None, method=method)
        try:
            with self.opener.open(req, timeout=4) as resp:
                return resp.status, resp.read()
        except error.HTTPError as e:
            return e.code, e.read()

    def first_code(self):
        status, raw = self.call()
        self.assertEqual(status, 200)
        result = json.loads(raw)
        self.assertEqual(result["websocket"]["token"], TOKEN)
        return result

    def test_diagnostics_are_aggregate_only_and_missing_client_is_denied(self):
        url = self.adapter_url + "/internal/diagnostics"
        with self.opener.open(url, timeout=4) as response:
            before = json.load(response)
        self.assertEqual(before["counts"]["ota_seen"], 0)
        self.assertEqual(before["counts"]["missing_client_id"], 0)
        req = request.Request(
            self.adapter_url + "/xiaozhi/ota/",
            data=b'{"application":{"version":"2.6.0"}}',
            headers={"Device-Id": D1, "Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(error.HTTPError) as denied:
            self.opener.open(req, timeout=4)
        self.assertEqual(denied.exception.code, 400)
        with self.opener.open(url, timeout=4) as response:
            after = json.load(response)
        self.assertEqual(after["counts"]["ota_seen"], 1)
        self.assertEqual(after["counts"]["missing_client_id"], 1)
        self.assertEqual(after["counts"]["ota_code_in_response"], 0)
        self.assertNotIn(D1, json.dumps(after))
        self.assertNotIn(C1, json.dumps(after))
        self.assertNotIn("device_id", after)
        self.assertEqual(FakeUpstream.requests, [])
        self.assertEqual(self.call(path="/xiaozhi/ota/", method="GET")[0], 405)
        with self.opener.open(url, timeout=4) as response:
            get_stats = json.load(response)
        self.assertEqual(get_stats["counts"]["ota_get_seen"], 1)

    def test_diagnostics_upstream_errors_do_not_expose_private_fields(self):
        self.upstream_server.shutdown()
        self.upstream_server.server_close()
        status, _ = self.call()
        self.assertEqual(status, 503)
        with self.opener.open(self.adapter_url + "/internal/diagnostics", timeout=4) as response:
            data = json.load(response)
        self.assertEqual(data["counts"]["upstream_error"], 1)
        self.assertEqual(data["counts"]["ota_code_in_response"], 0)
        self.assertNotIn(D1, json.dumps(data))

    def test_init_private_and_no_external_dependencies(self):
        db = pathlib.Path(self.tmp.name) / "db.sqlite"
        self.assertEqual(db.stat().st_mode & 0o777, 0o600)
        self.assertEqual(db.parent.stat().st_mode & 0o777, 0o700)

    def test_first_ota_has_six_digits_and_unmodified_token(self):
        result = self.first_code()
        self.assertRegex(result["activation"]["code"], r"^\d{6}$")
        self.assertEqual(result["activation"]["challenge"], D1)
        self.assertIn(result["activation"]["code"], result["activation"]["message"])
        self.assertEqual(result["websocket"]["url"], WS_URL)
        self.assertEqual(result["firmware"]["url"], "")
        self.assertEqual(FakeUpstream.requests[-1], ("/xiaozhi/ota/", D1, C1))

    def test_pending_202_approve_then_200_without_activation(self):
        code = self.first_code()["activation"]["code"]
        self.assertEqual(self.call("/xiaozhi/ota/activate")[0], 202)
        self.assertEqual(self.call("/internal/authorize-ws", method="GET")[0], 403)
        self.assertEqual(self.store.approve(code), D1)
        self.assertEqual(self.call("/xiaozhi/ota/activate")[0], 200)
        self.assertEqual(self.call("/internal/authorize-ws", method="GET")[0], 200)
        status, raw = self.call()
        self.assertEqual(status, 200)
        self.assertNotIn("activation", json.loads(raw))
        self.assertEqual(json.loads(raw)["websocket"]["token"], TOKEN)

    def test_code_is_stable_until_expired(self):
        first = self.first_code()["activation"]["code"]
        self.now[0] += 50
        self.assertEqual(self.first_code()["activation"]["code"], first)
        self.now[0] += mod.TTL_SECONDS + 1
        with self.assertRaises(ValueError):
            self.store.approve(first)
        next_code = self.first_code()["activation"]["code"]
        self.assertRegex(next_code, r"^\d{6}$")

    def test_wrong_code_cannot_approve_and_other_device_unbound(self):
        code = self.first_code()["activation"]["code"]
        bad = "000000" if code != "000000" else "000001"
        with self.assertRaises(ValueError):
            self.store.approve(bad)
        self.assertEqual(self.call("/xiaozhi/ota/activate", device=D2, client=C2)[0], 202)
        self.store.approve(code)
        self.assertEqual(self.call("/xiaozhi/ota/activate", device=D2, client=C2)[0], 202)
        self.assertEqual(self.call("/internal/authorize-ws", device=D2, client=C2, method="GET")[0], 403)

    def test_identity_change_is_rejected_and_bound_identity_unchanged(self):
        self.first_code()
        self.assertEqual(self.call(client=C2)[0], 403)
        self.assertEqual(self.call("/xiaozhi/ota/activate", client=C2)[0], 202)

    def test_revoke_and_reactivate(self):
        code = self.first_code()["activation"]["code"]
        self.store.approve(code)
        self.assertEqual(self.store.revoke(D1), 1)
        self.assertEqual(self.call("/xiaozhi/ota/activate")[0], 202)
        self.assertIn("activation", json.loads(self.call()[1]))

    def test_bad_requests_have_no_activation(self):
        for device, client, body in [
            ("bad", C1, b"{}"), (D1, "", b"{}"), (D1, C1, b"not-json"), (D1, C1, b"[]"),
            (D1, C1, b" " * (mod.MAX_BODY + 1)),
        ]:
            self.assertEqual(self.call(device=device, client=client, body=body)[0], 400)
        self.assertEqual(self.call("/private/approve")[0], 404)
        self.assertEqual(self.call("/health", method="GET")[0], 200)

    def test_upstream_unavailable_fails_closed(self):
        self.upstream_server.shutdown()
        self.upstream_server.server_close()
        self.assertEqual(self.call()[0], 503)

    def test_upstream_missing_token_is_not_forged(self):
        FakeUpstream.response = {"websocket": {"url": "wss://fake.invalid/xiaozhi/v1/", "token": ""}}
        self.assertEqual(self.call()[0], 400)
        self.assertFalse(self.store.approved(D1, C1))

    def test_origin_and_wss_guards(self):
        self.assertEqual(mod.validate_origin(mod.DEFAULT_UPSTREAM), mod.DEFAULT_UPSTREAM)
        for origin in ["https://example.com/xiaozhi/ota/", "http://localhost:18003/xiaozhi/ota/",
                       "http://127.0.0.1:19009/xiaozhi/ota/", "http://127.0.0.1:18003/evil"]:
            with self.assertRaises(ValueError):
                mod.validate_origin(origin)
        with self.assertRaises(ValueError):
            mod.validate_wss("http://example.com/xiaozhi/v1/")


if __name__ == "__main__":
    unittest.main()