"""Offline P4-3 safety tests: no real ESP32 required."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import p4_flash_backup as safe

def sample():
    buf = bytearray(b"\xff") * safe.FLASH_SIZE
    for i, (name, (start, length, kind, subtype)) in enumerate(safe.EXPECTED.items()):
        struct.pack_into("<HBBII16sI", buf, safe.TABLE_OFFSET + 32*i,
                         0x50aa, kind, subtype, start, length,
                         name.encode().ljust(16, b"\0"), 0)
    buf[safe.EXPECTED["ota_0"][0]] = 0xe9
    return bytes(buf)

class TestBackups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob = sample()

    def test_layout_and_hash(self):
        r = safe.inspect(self.blob)
        self.assertEqual(len(r["partitions"]), 6)
        self.assertTrue(r["contains_credentials"])

    def test_truncated_stop(self):
        with self.assertRaises(ValueError):
            safe.inspect(self.blob[:-1])

    def test_drift_stop(self):
        b = bytearray(self.blob)
        b[safe.TABLE_OFFSET+4] ^= 1
        with self.assertRaises(ValueError):
            safe.inspect(b)

    def test_missing_boot_slot_stop(self):
        b = bytearray(self.blob)
        b[safe.EXPECTED["ota_0"][0]] = 0xff
        with self.assertRaises(ValueError):
            safe.inspect(b)

    def test_tampered_nvs_stop(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            (d/"fullflash-private.bin").write_bytes(self.blob)
            (d/"manifest.json").write_text(json.dumps(safe.inspect(self.blob)))
            self.assertEqual(safe.verify(d)["sha256"], safe.digest(self.blob))
            b = bytearray(self.blob)
            b[safe.EXPECTED["nvs"][0]] ^= 1
            (d/"fullflash-private.bin").write_bytes(b)
            with self.assertRaises(ValueError):
                safe.verify(d)

    def test_capture_read_only_and_private(self):
        def fake_read(cmd, check):
            self.assertTrue(check)
            self.assertIn("read-flash", cmd)
            self.assertNotIn("write-flash", cmd)
            self.assertNotIn("erase-flash", cmd)
            Path(cmd[-1]).write_bytes(self.blob)
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)/"private"
            with patch.object(safe.subprocess, "run", side_effect=fake_read):
                safe.capture("/dev/ttyUSB0", d)
            self.assertEqual(d.stat().st_mode & 0o777, 0o700)
            self.assertEqual((d/"fullflash-private.bin").stat().st_mode & 0o777, 0o600)
            self.assertEqual((d/"manifest.json").stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                safe.capture("/dev/ttyUSB0", d)

if __name__ == "__main__":
    unittest.main()
