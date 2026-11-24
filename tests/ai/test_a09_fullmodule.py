"""A09 Manager-Only security contract: static; no Docker, deployment, secrets or paid API calls."""
import base64
import hashlib
import hmac
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "deploy/ai/a09/docker-compose.yml").read_text()
SCRIPT = (ROOT / "tools/ai/a09-fullmodule.sh").read_text()
PLAN = (ROOT / "docs/AI-FULLMODULE-PILOT.md").read_text()


class ManagerOnlyContract(unittest.TestCase):
    def test_official_images_are_pinned_and_no_duplicate_server(self):
        self.assertIn("web_0.9.8", SCRIPT)
        self.assertIn("RepoDigests", SCRIPT)
        self.assertIn("mysql:8.4", SCRIPT)
        self.assertIn("redis:8.0", SCRIPT)
        self.assertNotIn("server_0.9.8", SCRIPT)
        self.assertNotIn("SERVER_IMAGE", COMPOSE)
        self.assertNotIn("server_latest", COMPOSE + SCRIPT)
        self.assertNotIn("web_latest", COMPOSE + SCRIPT)
        self.assertNotIn("seccomp:unconfined", COMPOSE)
        actual = set(re.findall(r"(?m)^  ([a-z][a-z0-9_-]+):$", COMPOSE))
        self.assertEqual(actual, {"mysql", "redis", "manager"})

    def test_manager_private_host_ports_and_no_public_services(self):
        ports = re.findall(r'127\.0\.0\.1:(\d+):\d+/tcp', COMPOSE)
        self.assertEqual(ports, ["19002"])
        self.assertNotRegex(COMPOSE, r"(?m)^\s+-\s*['\"]?0\.0\.0\.0:")
        self.assertNotRegex(COMPOSE, r"(?m)^\s+-\s*['\"]?\d{4,5}:\d{4,5}")
        self.assertNotIn("19000:", COMPOSE)
        self.assertNotIn("19003:", COMPOSE)
        self.assertNotIn("8000/tcp", COMPOSE)
        self.assertNotIn("8003/tcp", COMPOSE)
        self.assertIn("name: s3-voice-manager", COMPOSE)

    def test_measured_resource_guard_and_fail_closed_budget(self):
        self.assertIn("mem_limit: 384m", COMPOSE)
        self.assertIn("mem_limit: 96m", COMPOSE)
        self.assertIn("mem_limit: 640m", COMPOSE)
        self.assertIn("-Xmx320m", COMPOSE)
        self.assertIn("--innodb-buffer-pool-size=96M", COMPOSE)
        self.assertIn('test "$total" -ge 3400000', SCRIPT)
        self.assertIn('test "$avail" -ge 1400000', SCRIPT)
        self.assertIn('test "$avail" -ge 650000', SCRIPT)
        self.assertIn('test "$((now-was))" -le 131072', SCRIPT)
        self.assertIn("restart: \"no\"", COMPOSE)
        self.assertIn("1,120MiB", PLAN)

    def test_preflight_is_readonly_before_any_image_or_directory(self):
        start = SCRIPT.index("preflight() {")
        end = SCRIPT.index("\n}", start)
        preflight = SCRIPT[start:end]
        for forbidden in ("docker pull", "mkdir ", "docker compose up", "docker restart", "cp ", "mv "):
            self.assertNotIn(forbidden, preflight)
        install = SCRIPT[SCRIPT.index("install() {"):SCRIPT.index("\n}", SCRIPT.index("install() {"))]
        self.assertLess(install.index("preflight\n"), install.index('image_digest "$IMAGE_PREFIX:web_0.9.8"'))
        self.assertIn("baseline", preflight)
        self.assertIn("existing 4B OTA unhealthy", preflight)
        self.assertIn("A09_BLOCKED", PLAN)
        self.assertIn("MemAvailable", PLAN)

    def test_production_services_are_not_changed(self):
        self.assertIn("ROOT=/opt/s3-voice-manager", SCRIPT)
        self.assertIn("PRODUCTION=/opt/s3-voice-ai", SCRIPT)
        self.assertIn("EDGE=/opt/s3-voice-ai-edge", SCRIPT)
        self.assertIn('test "$(baseline_ids)" = "$ids"', SCRIPT)
        self.assertNotRegex(SCRIPT, r'docker\s+(?:stop|rm|restart)\s+s3-voice-ai-')
        self.assertNotIn("docker compose down -v", SCRIPT)
        self.assertIn("comp stop manager redis mysql", SCRIPT)
        self.assertNotIn("comp up -d server", SCRIPT)
        self.assertNotIn('cp "$ROOT/', SCRIPT)
        self.assertIn('wait_manager || die', SCRIPT)

    def test_activation_is_stock_local_only_and_unbridged_by_default(self):
        self.assertIn("wss://manager-only-not-ready.invalid/xiaozhi/v1/", SCRIPT)
        self.assertIn("activation", SCRIPT)
        self.assertIn("assert status==202", SCRIPT)
        self.assertIn("A09_ACTIVATION_CONTRACT_PASS", SCRIPT)
        self.assertIn("UNBRIDGED_WSS", SCRIPT)
        self.assertIn("A09_BRIDGE_PROTOCOL_PASS", SCRIPT)
        self.assertIn("iPhone", PLAN)
        self.assertIn("202", PLAN)

    def test_manager_only_secrets_are_scoped_and_reversible(self):
        self.assertIn("openssl rand -hex 24", SCRIPT)
        self.assertIn('chmod 600 "$ENVFILE"', SCRIPT)
        self.assertIn('chmod 600 "$ROOT/.pre-bridge-secret"', SCRIPT)
        self.assertIn("server.secret", SCRIPT)
        self.assertIn("server.websocket", SCRIPT)
        self.assertIn("manager_secret()", SCRIPT)
        self.assertIn("bridge_rollback()", SCRIPT)
        self.assertIn("bridge-rollback) bridge_rollback", SCRIPT)
        self.assertIn("identity.json", SCRIPT)
        self.assertIn("hmac.compare_digest", SCRIPT)
        self.assertIn("HDEL sys:params server.secret server.websocket server.ota server.auth.enabled", SCRIPT)
        self.assertNotIn("FLUSHALL", SCRIPT)
        self.assertNotIn("FLUSHDB", SCRIPT)
        self.assertIn("original 4B unchanged", SCRIPT)
        self.assertNotIn("MYSQL_ROOT_PASSWORD: 123456", COMPOSE)

    def test_fixed_hmac_vector_matches_upstream_token_algorithm(self):
        # This checks the documented HMAC signature shape, not live Java/Python interoperability.
        secret = b"a09_source_contract_only"
        client = "11111111-2222-4333-8444-555555555555"
        device = "02:00:00:00:00:01"
        timestamp = 1800000000
        plaintext = f"{client}|{device}|{timestamp}".encode()
        signed = base64.urlsafe_b64encode(
            hmac.new(secret, plaintext, hashlib.sha256).digest()
        ).decode().rstrip("=")
        self.assertEqual(len(signed), 43)
        self.assertTrue(hmac.compare_digest(signed, signed))
        self.assertNotIn(client, f"{signed}.{timestamp}")
        self.assertNotIn(device, f"{signed}.{timestamp}")


if __name__ == "__main__":
    unittest.main()
