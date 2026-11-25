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
        install = DEPLOY.split("install_pilot() {", 1)[1].split("\n}", 1)[0]
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

    def test_ci_uses_real_websocket_upgrade_not_urllib_connection_close(self):
        docker_test = (ROOT / "tests/ai/a09_p2_docker.sh").read_text()
        self.assertIn("http_client.HTTPConnection", docker_test)
        self.assertIn("'Connection':'Upgrade'", docker_test)
        self.assertIn("approved_ws==101", docker_test)
        self.assertIn('ready=0', docker_test)

    def test_install_invocation_cannot_shadow_coreutils_or_recurse(self):
        # Regression for the actual phone VPS issue: install() called itself at
        # "install -d", continuously repeating PRECHECK / IMAGE_CACHED.
        import subprocess

        self.assertNotRegex(DEPLOY, r"(?m)^install\(\) \{")
        self.assertIn("install_pilot() {", DEPLOY)
        self.assertIn("  install) install_pilot ;;", DEPLOY)
        self.assertIn('command install -d -m 0700 "$ROOT" "$ROOT/data"', DEPLOY)
        body = DEPLOY.split("install_pilot() {", 1)[1].split("\n}", 1)[0]
        # Execute the REAL install_pilot body with harmless Docker stubs. Exit
        # immediately after coreutils creates a temporary directory.
        shell = r"""
set -Eeuo pipefail
ROOT="$1"
PYTHON_TAG="synthetic"
preflight() { printf 'PREFLIGHT_ONCE\n'; }
baseline_ids() { printf 'same-original-containers'; }
docker() { :; }
image_digest() { printf 'python@sha256:synthetic'; }
resources_pre() { :; }
msg() { :; }
chown() {
  test -d "$ROOT/data"
  printf 'INSTALL_DIR_CREATED\n'
  exit 0
}
""" + "install_pilot() {\n" + body + "\n}\ninstall_pilot\n"
        with tempfile.TemporaryDirectory() as folder:
            stage = str(pathlib.Path(folder) / "install-stage")
            p = subprocess.run(
                ["bash", "-c", shell, "bash", stage],
                capture_output=True, text=True, timeout=5,
            )
            self.assertEqual(p.returncode, 0, p.stderr[-1500:])
            self.assertEqual(p.stdout.count("PREFLIGHT_ONCE"), 1)
            self.assertEqual(p.stdout.count("INSTALL_DIR_CREATED"), 1)
            self.assertTrue((pathlib.Path(stage) / "data").is_dir())

    def test_cached_digest_skips_pull_and_shows_progress_on_fallback(self):
        # Avoid a second hidden image pull after Ctrl+C on a phone SSH session.
        script = DEPLOY.split("image_digest() {", 1)[1].split("stop_new_on_error() {", 1)[0]
        self.assertIn("IMAGE_CACHED", script)
        self.assertIn("IMAGE_PULL", script)
        self.assertLess(script.index("docker image inspect"), script.index("docker pull"))
        self.assertIn('docker pull "$img" >&2', script)
        self.assertIn("immutable Python digest unavailable", script)

    def test_single_existing_hostname_exact_a04_patch(self):
        # The previous A04 device-specific paths and 403 default deny must be
        # byte-for-byte unchanged except for an inserted A09 section.
        path = ROOT / "tools/ai/a09_same_host.py"
        spec = importlib.util.spec_from_file_location("a09_same_host_test", path)
        sh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sh)
        original = (ROOT / "deploy/ai/a04/Caddyfile.in").read_text()
        original = original.replace("__PAIR_SECRET__", "a" * 64)
        original = original.replace("__DEVICE_ID__", "02:01:02:03:04:05")
        original = original.replace("__CLIENT_ID__", "original-client")
        self.assertEqual(sh.original_secret(original), "a" * 64)
        extended = sh.extend_caddy(original, "b" * 64)
        self.assertIn("/xiaozhi/ota/" + "b" * 64, extended)
        self.assertIn("/xiaozhi/v1/" + "b" * 64, extended)
        self.assertIn("reverse_proxy s3-voice-a09-lite-gateway:8080", extended)
        self.assertIn('    respond "Forbidden" 403', extended)
        self.assertEqual(extended.count("A09-P2-SAME-HOST-BEGIN"), 1)
        self.assertEqual(extended.count("A09-P2-SAME-HOST-END"), 1)
        self.assertIn("/xiaozhi/ota/" + "a" * 64, extended)
        self.assertIn("/xiaozhi/v1/" + "a" * 64, extended)
        start = extended.index(sh.START)
        end = extended.index(sh.END) + len(sh.END) + 1
        self.assertEqual(extended[:start] + extended[end:], original)
        with self.assertRaises(sh.Stop):
            sh.extend_caddy(extended, "c" * 64)
        with self.assertRaises(sh.Stop):
            sh.extend_caddy(original, "a" * 64)
        with self.assertRaises(sh.Stop):
            sh.extend_caddy(original.replace("Forbidden", "OK"), "b" * 64)

    def test_same_host_script_has_scope_safety_and_private_reveal(self):
        script = (ROOT / "tools/ai/a09_same_host.py").read_text()
        sh = (ROOT / "tools/ai/a09-same-host.sh").read_text()
        self.assertIn('HOST = "voice.cncloudx.com"', script)
        self.assertNotIn("ios-voice.cncloudx.com/", script)
        self.assertIn("same_inode_write(CADDY, candidate)", script)
        self.assertIn("caddy_reload()", script)
        self.assertIn("original_health()", script)
        self.assertIn("private_create(OLD_CADDY, a04)", script)
        self.assertIn("private_create(OLD_ENV, env)", script)
        self.assertIn("ROLLED_BACK", script)
        self.assertIn("sys.stdout.isatty()", script)
        self.assertIn('choices=["apply", "status", "rollback", "show-url"]', script)
        self.assertNotRegex(script, r"docker.*(stop|restart|rm).*(s3-voice-ai-server|s3-voice-ai-gateway|s3-voice-ai-tunnel)")
        self.assertIn("a09_same_host.py", sh)

    def test_cloudflare_owner_action_and_real_audio_not_claimed(self):
        self.assertIn("ios-voice.cncloudx.com", DEPLOY)
        self.assertIn("s3-voice-a09-lite-gateway:8080", DOCS)
        self.assertIn("Cloudflare", DOCS)
        self.assertIn("Hi 小智", DOCS)
        self.assertIn("P2 BLOCKED", DOCS)
        self.assertNotIn("cloudflared tunnel run", DEPLOY)


if __name__ == "__main__":
    unittest.main()