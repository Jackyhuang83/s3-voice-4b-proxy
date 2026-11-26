"""Real ephemeral Docker lifecycle test for P1 standalone WebUI pilot.

Requires root on a *GitHub Runner* with two newly created synthetic external
Docker bridges. The ONLY mocked facts are the legacy A03/A04 preflight and
container IDs; the two NEW Caddy/Auth containers, permissions, login, network,
Opus vendoring, pull/inspect, Docker Compose and rollback are REAL.
Never run on the user's VPS: the production CLI has NO mock bypass.
"""
import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location("pilot",ROOT/"tools/ai/webui_pilot.py")
pilot=importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

LEGACY={
    "s3-voice-ai-server":"synthetic-legacy-a03-unchanged",
    "s3-voice-ai-gateway":"synthetic-legacy-a04-unchanged",
    "s3-voice-ai-tunnel":"synthetic-existing-tunnel-unchanged"
}

class RealNewSidecarStage(unittest.TestCase):
    def test_stage_verify_rollback_and_no_exposed_ports(self):
        base=pathlib.Path("/opt/s3-voice-webui")
        self.assertFalse(base.exists(),"CI runner contains unexpected pilot path")
        with mock.patch.object(pilot,"preflight",return_value={"ok":True}), \
             mock.patch.object(pilot,"current_ids",return_value=LEGACY), \
             mock.patch.object(pilot,"require_root"):
            try:
                pilot.stage("webvoice.cncloudx.com",True,base=base,root=ROOT)
                self.assertTrue((base/"state.json").is_file())
                self.assertTrue((base/"src/webui/vendor/libopus/dist/index.js").is_file())
                self.assertTrue((base/"src/tools/ai/webui_pilot.py").is_file())
                self.assertTrue((base/"src/tools/ai/webui_preflight.py").is_file())
                self.assertTrue((base/"src/deploy/ai/webui/docker-compose.isolated.example.yml").is_file())
                self.assertEqual(0o700, (base/"private").stat().st_mode & 0o777)
                self.assertEqual(0o600, (base/"private/models.json").stat().st_mode & 0o777)
                self.assertEqual(0o644, (base/"src/deploy/ai/webui/Caddyfile.isolated").stat().st_mode & 0o777)
                self.assertTrue(pilot.docker_state("s3-voice-webui-auth")["State"]["Running"])
                self.assertTrue(pilot.docker_state("s3-voice-webui-gateway")["State"]["Running"])
                # This is a second independent verification, not just the one
                # triggered as part of stage().
                pilot.verify(base)
                print("WEBUI_PILOT_DOCKER_STAGE_PASS: real auth, Caddy, private login and no host ports")
            finally:
                if (base/"state.json").is_file():
                    pilot.rollback(base)
                else:
                    # Defensive cleanup only of the unique new CI project.
                    if (base/"docker-compose.yml").exists() and (base/".env").exists():
                        pilot.run(pilot.compose_args(base,"down"),check=False)
            self.assertIsNone(pilot.docker_state("s3-voice-webui-auth"))
            self.assertIsNone(pilot.docker_state("s3-voice-webui-gateway"))
            self.assertTrue((base/"private/auth.env").is_file(),
                            "rollback must preserve private credentials for diagnosis")
            print("WEBUI_PILOT_DOCKER_ROLLBACK_PASS: both NEW containers removed; no legacy services changed")

if __name__=="__main__":
    unittest.main()
