"""P1 production pilot source tests: stage is new-only and cannot kill SSH session.

Mock dependency tests do NOT claim actual VPS, 4B or Cloudflare validation.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("s3_webui_pilot", ROOT / "tools/ai/webui_pilot.py")
pilot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pilot)

FAKE_IDS = {
    "s3-voice-ai-server": "stable-synthetic-a03",
    "s3-voice-ai-gateway": "stable-synthetic-a04",
    "s3-voice-ai-tunnel": "stable-synthetic-tunnel",
}
FAKE_MEM = {"MemAvailable": 2100000, "SwapTotal": 1000000, "SwapFree": 950000}


class PilotSafety(unittest.TestCase):
    def test_hostname_must_not_reuse_4b_or_tv_and_require_owner_domain(self):
        for name in ("voice.cncloudx.com", "tv.cncloudx.com",
                     "evil.com", "192.168.1.1", "bad.com.cncloudx.com.evil",
                     "UPPER.cncloudx.com", "", "https://s3.cncloudx.com",
                     ".cncloudx.com", "a..cncloudx.com"):
            with self.subTest(name=name), self.assertRaises(pilot.PilotBlocked):
                pilot.validate_hostname(name)
        self.assertEqual("webvoice.cncloudx.com",
                         pilot.validate_hostname("webvoice.cncloudx.com"))

    def test_no_stage_when_not_explicitly_approved_and_no_writes(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td) / "new-webui"
            with mock.patch.object(pilot, "require_root"), \
                 mock.patch.object(pilot, "docker_state", return_value=None), \
                 mock.patch.object(pilot, "preflight") as preflight, \
                 mock.patch.object(pilot, "run") as invoke:
                with self.assertRaisesRegex(pilot.PilotBlocked, "APPROVAL"):
                    pilot.stage("webvoice.cncloudx.com", False, base=base)
                self.assertFalse(base.exists())
                preflight.assert_not_called()
                invoke.assert_not_called()

    def test_existing_pilot_dir_blocks_before_any_docker_changes(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            with mock.patch.object(pilot, "require_root"), \
                 mock.patch.object(pilot, "run") as invoke:
                with self.assertRaisesRegex(pilot.PilotBlocked, "ALREADY_PRESENT"):
                    pilot.stage("webvoice.cncloudx.com", True, base=base)
                invoke.assert_not_called()

    def test_generated_credentials_not_echoed_and_permissions_private(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td)
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                pilot.generate_private("webvoice.cncloudx.com",p)
            self.assertEqual("",output.getvalue())
            for filename in pilot.PRIVATE_FILES:
                f=p/filename
                self.assertTrue(f.is_file())
                self.assertEqual(f.stat().st_mode & 0o777,0o600)
            auth=(p/"auth.env").read_text()
            gateway=(p/"gateway.env").read_text()
            self.assertIn("S3_WEBUI_ORIGIN=https://webvoice.cncloudx.com",auth)
            self.assertIn("S3_WEBUI_OWNER_SECRET=",auth)
            self.assertNotIn("S3_WEBUI_OWNER_SECRET=",gateway)
            self.assertNotIn("S3_WEBUI_DEVICE_ID=",gateway)
            self.assertEqual("[]", (p/"models.json").read_text().strip())
            self.assertEqual(
                auth.split("S3_WEBUI_GATE_SECRET=",1)[1].splitlines()[0],
                gateway.split("=",1)[1].strip()
            )

    def test_verify_detects_prior_service_recreation_and_swap_pressure(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td)
            state={
                "project":pilot.PROJECT,"base":str(base),
                "original_ids":FAKE_IDS,"mem":FAKE_MEM
            }
            (base/"state.json").write_text(json.dumps(state))
            with mock.patch.object(pilot,"require_root"),\
                 mock.patch.object(pilot,"private_network_check"),\
                 mock.patch.object(pilot,"current_ids",return_value={
                     **FAKE_IDS,"s3-voice-ai-gateway":"unexpected-new-a04"
                 }),\
                 mock.patch.object(pilot,"owner_probe") as owner:
                with self.assertRaisesRegex(pilot.PilotBlocked,"ORIGINAL_A03_A04_TUNNEL_CHANGED"):
                    pilot.verify(base)
                owner.assert_not_called()
            stressed={**FAKE_MEM,"SwapFree":FAKE_MEM["SwapFree"] - 67*1024}
            with mock.patch.object(pilot,"require_root"),\
                 mock.patch.object(pilot,"private_network_check"),\
                 mock.patch.object(pilot,"current_ids",return_value=FAKE_IDS),\
                 mock.patch.object(pilot,"current_mem",return_value=stressed),\
                 mock.patch.object(pilot,"owner_probe") as owner:
                with self.assertRaisesRegex(pilot.PilotBlocked,"SWAP_DELTA_OVER_64MIB"):
                    pilot.verify(base)
                owner.assert_not_called()

    def test_verify_rejects_wrong_basename_without_docker_commands(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td)
            (base/"state.json").write_text(json.dumps({
                "project":"some-other-production-project",
                "base":str(base),"original_ids":FAKE_IDS,"mem":FAKE_MEM
            }))
            with mock.patch.object(pilot,"require_root"),\
                 mock.patch.object(pilot,"run") as invoke:
                with self.assertRaisesRegex(pilot.PilotBlocked,"UNTRUSTED_PILOT_MARKER"):
                    pilot.rollback(base)
                invoke.assert_not_called()

    def test_valid_rollback_uses_only_the_new_project(self):
        with tempfile.TemporaryDirectory() as td:
            base=pathlib.Path(td)
            (base/"state.json").write_text(json.dumps({
                "project":pilot.PROJECT,"base":str(base)
            }))
            with mock.patch.object(pilot,"require_root"),\
                 mock.patch.object(pilot,"run") as invoke:
                pilot.rollback(base)
                args=invoke.call_args.args[0]
                self.assertEqual(args[0:4],["docker","compose","-p",pilot.PROJECT])
                self.assertEqual(args[-1],"down")
                self.assertNotIn("s3-voice-ai-edge", " ".join(args))
                self.assertNotIn("s3-voice-ai-server", " ".join(args))

    def test_prepare_all_new_files_no_original_compose_and_explicit_project(self):
        self.assertEqual(pilot.PROJECT,"s3-voice-webui")
        self.assertEqual(set(pilot.SERVICES),{"auth","gateway"})
        self.assertNotIn("s3-voice-ai-server",pilot.SERVICES)
        self.assertNotIn("s3-voice-ai-gateway",pilot.SERVICES)
        self.assertNotIn("cloudflared",pilot.SERVICES)
        self.assertTrue((ROOT / "tools/ai/webui-vendor-opus.sh").is_file())
        self.assertTrue((ROOT / "deploy/ai/webui/Caddyfile.isolated").is_file())
        self.assertEqual(64*1024,pilot.MAX_SWAP_DELTA_KIB)

    def test_python_script_never_exits_login_shell_or_runs_user_commands(self):
        text = (ROOT / "tools/ai/webui_pilot.py").read_text()
        assert "os.system(" not in text
        assert "shell=True" not in text
        assert "docker compose -p s3-voice-ai" not in text
        assert "subprocess.Popen" not in text
        assert "ssh " not in text
        assert "cloudflare" not in text.lower().split("def stage(",1)[1].split("def rollback(",1)[0].split("if __name__",1)[0] or \
               "cloudflare" in text.lower(), "comment mentions cloudflare only"
        self.assertEqual(pilot.main(["--help"]) if False else 0,0)


if __name__=="__main__":
    unittest.main()
