"""Read-only Cloudflare/Caddy ingress audit contract; no live VPS access."""
import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "tools/ai/a09_edge_audit.py"
spec = importlib.util.spec_from_file_location("a09_edge_audit", PATH)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class OneShotServer(BaseHTTPRequestHandler):
    requests = []
    redirect = False

    def log_message(self, *_):
        pass

    def do_GET(self):
        type(self).requests.append(("GET", self.path, b""))
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        data = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).requests.append(("POST", self.path, data))
        if type(self).redirect:
            self.send_response(302)
            self.send_header("Location", "/secret-should-not-follow")
        else:
            self.send_response(400)
            self.send_header("Cf-Ray", "internal-test-only")
        self.end_headers()
        self.wfile.write(b'{"error":"rejected"}')


class EdgeAudit(unittest.TestCase):
    def test_status_classification_keeps_cf_and_caddy_separate(self):
        cases = [
            (400, 400, "PUBLIC_AND_LOCAL_A09_ROUTE_PASS"),
            (403, 403, "CADDY_403_LOCAL"),
            (502, 400, "A09_ORIGIN_UNAVAILABLE_LOCAL"),
            (400, 403, "PUBLIC_DENIED_OR_CHALLENGED"),
            (400, 302, "PUBLIC_REDIRECT_OR_ACCESS_AUTH"),
            (400, 530, "PUBLIC_TUNNEL_OR_EDGE_ROUTE_ERROR"),
            (400, 0, "PUBLIC_PROBE_UNREACHABLE_FROM_VPS"),
            (400, 200, "PUBLIC_UNEXPECTED_RESPONSE"),
        ]
        for local, public, expected in cases:
            with self.subTest(local=local, public=public):
                self.assertTrue(module.verdict(local, public).startswith(expected))

    def test_invalid_json_array_never_creates_code_or_follows_redirect(self):
        OneShotServer.requests = []
        OneShotServer.redirect = False
        server = ThreadingHTTPServer(("127.0.0.1", 0), OneShotServer)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = "http://127.0.0.1:" + str(server.server_port)
        try:
            status, cf_seen = module.request_status(base, "a" * 64)
            self.assertEqual((status, cf_seen), (400, True))
            self.assertEqual(OneShotServer.requests[0],
                             ("POST", "/xiaozhi/ota/" + "a" * 64, b"[]"))
            self.assertIsInstance(json.loads(module.NEGATIVE_BODY), list)
            OneShotServer.redirect = True
            self.assertEqual(module.request_status(base, "a" * 64)[0], 302)
            self.assertFalse(any(request[0] == "GET" for request in OneShotServer.requests))
        finally:
            server.shutdown()
            server.server_close()

    def test_source_makes_no_changes_or_secret_outputs(self):
        source = PATH.read_text()
        for prohibited in ("docker restart", "docker rm", "docker compose up",
                           "caddy reload", "write_text(", "write_bytes(",
                           "chmod(", "chown(", "os.environ.get('CF_API"):
            self.assertNotIn(prohibited, source)
        for expected in ("same-host-active", "A09-P2-SAME-HOST-BEGIN",
                         "LOCAL_HTTP", "PUBLIC_HTTP", "READ_ONLY_PASS",
                         "NoRedirect", "Cf-Ray", "NEGATIVE_BODY"):
            self.assertIn(expected.lower(), source.lower())


if __name__ == "__main__":
    unittest.main()
