"""P1-3 fail-closed offline fixture contract. Never inspects the actual VPS."""
import contextlib
import importlib.util
import io
import pathlib
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("s3_preflight", ROOT / "tools/ai/webui_preflight.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
DIGEST = "sha256:" + "a" * 64

def container(networks, ports):
    return {
        "State": {"Running": True},
        "Config": {"Image": "ghcr.io/example/voice@" + DIGEST, "Env": ["FAKE_PRIVATE_KEY=DO_NOT_PRINT_ME"]},
        "NetworkSettings": {"Networks": {n: {"Aliases": [n]} for n in networks}},
        "HostConfig": {
            "PortBindings": {
                key + "/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(val)}]
                for key, val in ports.items()
            }
        },
    }

def passing():
    return {
        "mem": {"MemAvailable": 1200000, "SwapTotal": 1048576, "SwapFree": 900000},
        "disk_free_bytes": 2 * 1024 ** 3,
        "a03_lock": True,
        "a03_private_config": True,
        "a04_identity_private": True,
        "a04_env_private": True,
        "a04_log_discard": True,
        "a04_reject_default": True,
        "a03_health_code": 200,
        "a04_health_code": 403,
        "a03": container(["s3-voice-ai_default"], {"8000": 18000, "8003": 18003}),
        "a04": container(["s3-voice-ai_default", "s3-voice-ai-edge_front"], {"8080": 18080}),
        "a04_fingerprint": "aaaabbbbcccc",
        "manager_active": False,
    }

class Ready(unittest.TestCase):
    def test_happy_path_and_no_secret_in_summary(self):
        result = p.evaluate(passing())
        self.assertTrue(result["ok"], result["failures"])
        self.assertEqual([], result["failures"])
        self.assertEqual(1, result["facts"]["a04_front_network_count"])
        self.assertTrue(result["facts"]["a03_a04_network_shared"])
        self.assertNotIn("DO_NOT_PRINT_ME", str(result))
        self.assertEqual(1200000 // 1024, result["facts"]["available_mib"])

    def test_critical_gates_fail_closed(self):
        changes = [
            ("low mem", "mem", {"MemAvailable": 1090000, "SwapTotal": 0, "SwapFree": 0}, "RAM_AVAILABLE_BELOW_1_05GIB"),
            ("disk", "disk_free_bytes", 1000, "DISK_FREE_BELOW_1GIB"),
            ("a03 lock", "a03_lock", False, "A03_IMAGE_LOCK_MISSING"),
            ("a03 private", "a03_private_config", False, "A03_PRIVATE_CONFIG_UNSAFE"),
            ("a04 identity", "a04_identity_private", False, "A04_IDENTITY_UNSAFE"),
            ("a04 env", "a04_env_private", False, "A04_ENV_UNSAFE"),
            ("a04 logs", "a04_log_discard", False, "A04_PATH_LOGGING_NOT_PROVEN_DISABLED"),
            ("a04 deny", "a04_reject_default", False, "A04_DEFAULT_DENY_NOT_PROVEN"),
            ("a03 health", "a03_health_code", 503, "A03_OTA_HEALTH_NOT_200"),
            ("a04 health", "a04_health_code", 200, "A04_DEFAULT_DENY_NOT_403"),
            ("manager", "manager_active", True, "A09_MANAGER_RESOURCE_ISOLATION_UNKNOWN"),
            ("a03 missing", "a03", None, "A03_CONTAINER_UNHEALTHY"),
            ("a04 missing", "a04", None, "A04_GATEWAY_UNHEALTHY"),
        ]
        for label,key,value,expected in changes:
            with self.subTest(label=label):
                info=passing();info[key]=value
                result=p.evaluate(info)
                self.assertFalse(result["ok"])
                self.assertIn(expected,result["failures"])

    def test_wrong_network_no_implicit_bridge(self):
        for target,networks,expected in [
            ("a03", ["not-s3"], "A03_NETWORK_MISMATCH"),
            ("a04", ["not-s3"], "A04_BACKEND_NETWORK_MISMATCH"),
            ("a04", ["s3-voice-ai_default"], "A04_FRONT_BRIDGE_NOT_UNIQUE"),
            ("a04", ["s3-voice-ai_default","front1","front2"], "A04_FRONT_BRIDGE_NOT_UNIQUE"),
        ]:
            with self.subTest(target=target,networks=networks):
                info=passing()
                info[target]["NetworkSettings"]["Networks"]={s:{} for s in networks}
                self.assertIn(expected,p.evaluate(info)["failures"])

    def test_any_nonloopback_port_or_mutable_image_fails(self):
        for service,port,expected in [
            ("a03","8000","A03_WS_NOT_LOOPBACK_ONLY"),
            ("a03","8003","A03_OTA_NOT_LOOPBACK_ONLY"),
            ("a04","8080","A04_GATE_NOT_LOOPBACK_ONLY"),
        ]:
            with self.subTest(service=service,port=port):
                info=passing()
                info[service]["HostConfig"]["PortBindings"][port+"/tcp"][0]["HostIp"]="0.0.0.0"
                self.assertIn(expected,p.evaluate(info)["failures"])
        for service in ("a03","a04"):
            info=passing()
            info[service]["Config"]["Image"]="caddy:latest"
            self.assertTrue(any("NOT_DIGEST_PINNED" in x for x in p.evaluate(info)["failures"]))

    def test_config_fingerprint_without_disclosure(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=pathlib.Path(tmp)/"Caddyfile"
            secret="my-unique-private-pair-secret-123"
            f.write_text('path /xiaozhi/v1/'+secret+'\n')
            fingerprint,body=p.config_evidence(f)
            self.assertEqual(12,len(fingerprint))
            self.assertIn(secret,body)
            summary=p.evaluate({**passing(),"a04_fingerprint":fingerprint})
            self.assertNotIn(secret,str(summary))

    def test_private_file_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=pathlib.Path(tmp)/"identity.json"
            f.write_text("CI_FAKE_ONLY")
            f.chmod(0o600)
            self.assertTrue(p.safe_file(f))
            f.chmod(0o644)
            self.assertFalse(p.safe_file(f))

    def test_cli_redaction_and_read_only_semantics(self):
        with patch.object(p, "gather", return_value=passing()), patch.object(p.sys, "argv", ["webui_preflight.py"]):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(0,p.main())
            result=output.getvalue()
            self.assertIn("WEBUI_P1_PREFLIGHT_PASS", result)
            self.assertIn("NO production deployment", result)
            self.assertNotIn("DO_NOT_PRINT_ME", result)
        fail={**passing(), "a03_health_code": 0}
        with patch.object(p, "gather", return_value=fail), patch.object(p.sys,"argv", ["webui_preflight.py"]):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(1,p.main())
            self.assertIn("A03_OTA_HEALTH_NOT_200",output.getvalue())

if __name__ == "__main__":
    unittest.main()
