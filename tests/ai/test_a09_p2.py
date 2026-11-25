"""P2 fail-closed deployment contracts; no Docker or paid API on local runner."""
import importlib.util
import io
import os
import pathlib
import re
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
ADAPTER = (ROOT / "tools/ai/a09_lite.py").read_text()
COMPOSE = (ROOT / "deploy/ai/a09-lite/docker-compose.yml").read_text()
CADDY = (ROOT / "deploy/ai/a09-lite/Caddyfile.in").read_text()
DEPLOY = (ROOT / "tools/ai/a09-lite-deploy.sh").read_text()
DOCS = (ROOT / "docs/ai/A09-P2-ISOLATED-IOS.md").read_text()
spec = importlib.util.spec_from_file_location("a09_lite_p2", ROOT / "tools/ai/a09_lite.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class P2Isolation(unittest.TestCase):
    def test_exact_new_containers_and_no_second_voice(self):
        self.assertEqual(set(re.findall(r"(?m)^  (\w+):$", COMPOSE.split("\nnetworks:\n", 1)[0])), {"adapter", "gateway"})
        self.assertIn("s3-voice-ai_default", COMPOSE)
        self.assertIn("s3-voice-ai-edge_front", COMPOSE)
        self.assertNotIn("web_0.9.8", COMPOSE)
        self.assertNotIn("server_0.9.8", COMPOSE)
        self.assertNotIn("mysql", COMPOSE.lower())
        self.assertNotIn("redis", COMPOSE.lower())

    def test_no_host_listener_published_and_no_prod_data_bind_mount(self):
        self.assertNotIn("ports:", COMPOSE)
        self.assertNotIn("network_mode:", COMPOSE)
        self.assertIn("internal: true", COMPOSE)
        self.assertNotIn("/opt/s3-voice-ai/", COMPOSE)
        self.assertNotIn("/opt/s3-voice-ai-edge/", COMPOSE)
        self.assertIn("./data:/var/lib/s3-voice-a09-lite:rw", COMPOSE)
        self.assertIn("./Caddyfile:/etc/caddy/Caddyfile:ro", COMPOSE)
        self.assertIn("./a09_lite.py:/app/a09_lite.py:ro", COMPOSE)

    def test_container_caps_and_low_memory_limits(self):
        self.assertIn("mem_limit: 128m", COMPOSE)
        self.assertIn("mem_limit: 96m", COMPOSE)
        self.assertEqual(COMPOSE.count("no-new-privileges:true"), 2)
        self.assertEqual(COMPOSE.count("cap_drop: [ALL]"), 2)
        self.assertIn("read_only: true", COMPOSE)
        self.assertIn("user: '10001:10001'", COMPOSE)
        self.assertIn("restart: 'no'", COMPOSE)

    def test_public_caddy_strict_exclusions_and_root_403(self):
        self.assertEqual(CADDY.count("__IOS_SECRET__"), 2)
        self.assertIn("output discard", CADDY)
        self.assertIn("path /xiaozhi/ota/__IOS_SECRET__", CADDY)
        self.assertIn("path /xiaozhi/v1/__IOS_SECRET__", CADDY)
        self.assertIn("path /xiaozhi/ota/activate", CADDY)
        self.assertIn("method POST", CADDY)
        self.assertIn("method GET", CADDY)
        self.assertIn('respond "Forbidden" 403', CADDY)
        self.assertNotIn("/internal/authorize-ws\n    reverse_proxy", CADDY)
        self.assertNotIn("handle_path", CADDY)

    def test_ws_requires_owner_approval_before_real_hmac_server(self):
        m = re.search(r"handle @ios_ws \{([\s\S]+?)\n  \}", CADDY)
        self.assertIsNotNone(m)
        ws = m.group(1)
        self.assertLess(ws.index("forward_auth"), ws.index("reverse_proxy"))
        self.assertIn("uri /internal/authorize-ws", ws)
        self.assertIn("reverse_proxy s3-voice-ai-server:8000", ws)
        self.assertNotIn("header_up -Authorization", CADDY)
        self.assertNotIn("header_up Authorization", CADDY)

    def test_preflight_readonly_is_first_install_operation(self):
        pre = DEPLOY.split("preflight() {", 1)[1].split("\n}", 1)[0]
        for text in ("docker pull", "docker compose up", "comp up", "mkdir ", "install -d", "docker restart", "cp ", "chown"):
            self.assertNotIn(text, pre)
        install = DEPLOY.split("install() {", 1)[1].split("\n}", 1)[0]
        self.assertLess(install.index("preflight\n"), install.index("image_digest"))
        self.assertIn("original_healthy", pre)
        self.assertIn("resources_pre", pre)

    def test_guards_and_rollback_never_affect_old_voice(self):
        for text in ('test "$avail" -ge 1400000', 'test "$(mem_available)" -ge 1100000',
                     'test "$((now-was))" -le 65536', 'stop_new_on_error', 'comp stop gateway adapter'):
            self.assertIn(text, DEPLOY)
        self.assertNotRegex(DEPLOY, r"docker\s+(stop|restart|rm)\s+s3-voice-ai-")
        self.assertNotRegex(DEPLOY, r"comp\s+down\b")
        self.assertNotIn("docker system prune", DEPLOY)
        self.assertNotIn("swapoff", DEPLOY)
        self.assertIn("original_ids=", DEPLOY)

    def test_allow_only_exact_docker_origin_when_real_container(self):
        with patch.dict(os.environ, {"A09_LITE_DOCKER_INTERNAL": "1"}), patch.object(module.Path, "is_file", return_value=True):
            self.assertEqual(module.validate_origin(module.DOCKER_UPSTREAM), module.DOCKER_UPSTREAM)
            self.assertTrue(module.docker_internal())
        with patch.dict(os.environ, {"A09_LITE_DOCKER_INTERNAL": "1"}), patch.object(module.Path, "is_file", return_value=False):
            self.assertFalse(module.docker_internal())
            with self.assertRaises(ValueError):
                module.validate_origin(module.DOCKER_UPSTREAM)
        for evil in ("http://evil:8003/xiaozhi/ota/", "http://s3-voice-ai-server:8003/admin", "http://s3-voice-ai-server:8003/xiaozhi/ota/?p=x"):
            with self.assertRaises(ValueError):
                module.validate_origin(evil)

    def test_owner_approve_stdin_is_not_logged_in_command_arguments(self):
        self.assertIn("approve -", DEPLOY)
        self.assertIn("read -r -s", DEPLOY)
        self.assertIn("sys.stdin.readline().strip()", ADAPTER)
        with tempfile.TemporaryDirectory() as folder:
            db = pathlib.Path(folder) / "test.sqlite"
            store = module.ActivationStore(db)
            store.initialize()
            code = store.issue("02:23:45:67:89:ab", "uuid-4")
            with patch("sys.stdin", io.StringIO(code + "\n")), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(module.main(["--db", str(db), "approve", "-"]), 0)
            self.assertTrue(store.approved("02:23:45:67:89:ab", "uuid-4"))

    def test_cloudflare_owner_action_and_real_audio_not_claimed(self):
        self.assertIn("ios-voice.cncloudx.com", DEPLOY)
        self.assertIn("s3-voice-a09-lite-gateway:8080", DOCS)
        self.assertIn("Cloudflare", DOCS)
        self.assertIn("Hi 小智", DOCS)
        self.assertIn("P2 BLOCKED", DOCS)
        self.assertNotIn("cloudflared tunnel run", DEPLOY)


if __name__ == "__main__":
    unittest.main()