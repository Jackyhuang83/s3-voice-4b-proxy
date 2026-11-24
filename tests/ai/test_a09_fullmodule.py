"""Static fail-closed security gates for official full module pilot.

Never runs Docker, touches production files or executes AI APIs.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / 'deploy/ai/a09/docker-compose.yml').read_text()
INSTALL = (ROOT / 'tools/ai/a09-fullmodule.sh').read_text()
PLAN = (ROOT / 'docs/AI-FULLMODULE-PILOT.md').read_text()


class FullPilotContract(unittest.TestCase):
    def test_version_pin_and_official_images(self):
        self.assertIn('server_0.9.8', INSTALL)
        self.assertIn('web_0.9.8', INSTALL)
        self.assertIn('RepoDigests', INSTALL)
        self.assertNotIn('server_latest', INSTALL)
        self.assertNotIn('web_latest', INSTALL)
        self.assertNotIn('seccomp:unconfined', COMPOSE)

    def test_all_ports_are_explicit_loopback(self):
        self.assertEqual(set(re.findall(r"127\.0\.0\.1:(\d+):\d+/tcp", COMPOSE)), {'19000', '19002', '19003'})
        self.assertNotRegex(COMPOSE, r"(?m)^\s+-\s*['\"]?0\.0\.0\.0:")
        self.assertNotRegex(COMPOSE, r"(?m)^\s+-\s*['\"]?\d{4,5}:\d{4,5}")
        self.assertIn('profiles: [voice]', COMPOSE)

    def test_independent_files_and_services(self):
        self.assertIn('ROOT=/opt/s3-voice-fullpilot', INSTALL)
        self.assertIn('name: s3-voice-fullpilot', COMPOSE)
        self.assertIn('containers_in_scope', INSTALL)
        self.assertNotRegex(INSTALL, r'(?<!-)docker\s+(?:stop|rm|restart|rmi)\s+s3-voice-ai-')
        self.assertNotIn('docker compose down -v', INSTALL)
        for service in ('server', 'manager', 'mysql', 'redis'):
            self.assertRegex(COMPOSE, rf'(?m)^  {service}:$')

    def test_credentials_not_hardcoded(self):
        self.assertIn('openssl rand -hex 24', INSTALL)
        self.assertIn('chmod 600 "$ENVFILE"', INSTALL)
        self.assertIn('chmod 600 "$ROOT/data/.config.yaml"', INSTALL)
        self.assertNotIn('MYSQL_ROOT_PASSWORD: 123456', COMPOSE)
        self.assertIn('server.auth.enabled', INSTALL)
        self.assertIn('manager_secret()', INSTALL)
        self.assertIn('activation.code', PLAN)

    def test_preflight_avoids_production_edit(self):
        block = INSTALL.split('preflight() {', 1)[1].split('\n}', 1)[0]
        for forbidden in ('docker pull', 'mkdir', 'docker compose up', 'docker restart', 'cp ', 'mv '):
            self.assertNotIn(forbidden, block)
        self.assertIn('mem_available', block)
        self.assertIn('containers_in_scope', block)


if __name__ == '__main__':
    unittest.main()
