import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import p4_release_gate as gate

class TestReleaseGate(unittest.TestCase):
    def test_no_device_refused(self):
        self.assertEqual(len(gate.missing({})), 8)

    def test_green_ci_does_not_equal_encryption(self):
        evidence = {k: True for k in gate.FIELDS}
        evidence["credential_encryption_verified"] = False
        evidence["private_fullflash_sha256"] = "a"*64
        evidence["board_serial"] = "synthetic-only"
        self.assertIn("credential_encryption_verified", gate.missing(evidence))

    def test_paperwork_is_not_automatic_deploy(self):
        evidence = {k: True for k in gate.FIELDS}
        evidence["private_fullflash_sha256"] = "a"*64
        evidence["board_serial"] = "synthetic-only"
        self.assertEqual(gate.missing(evidence), [])

if __name__ == "__main__":
    unittest.main()
