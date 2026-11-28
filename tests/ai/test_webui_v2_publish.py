"""UI-v2 publisher tests. Mock-only; no Docker/SSH/network/production files."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import hashlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("ui_v2_publish", ROOT / "tools/ai/webui_v2_publish.py")
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)


class PublishingSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reviewed = {
            name: (ROOT / "webui" / name).read_bytes()
            for name in pub.EXPECTED_GIT_BLOBS
        }

    def test_reviewed_github_blobs_and_ui_contracts(self):
        pub.validate_source(self.reviewed)
        for name, data in self.reviewed.items():
            self.assertEqual(pub.EXPECTED_GIT_BLOBS[name],pub.git_blob(data))
        broken = dict(self.reviewed)
        broken["app.js"] += b"// unsafe mutation"
        with self.assertRaisesRegex(RuntimeError, "DOWNLOADED_GIT_BLOB_MISMATCH_app.js"):
            pub.validate_source(broken)
        self.assertNotIn("webui/audio-ui.mjs", pub.EXPECTED_GIT_BLOBS)
        self.assertNotIn("tools/ai/webui_auth.py", pub.EXPECTED_GIT_BLOBS)

    def make_sandbox(self):
        folder = tempfile.TemporaryDirectory()
        base = Path(folder.name)
        webui = base / "webui"
        private = base / "private"
        webui.mkdir()
        private.mkdir()
        old = {name:(b"BASELINE_CUSTOM_" + name.encode()) for name in self.reviewed}
        for name, data in old.items():
            (webui / name).write_bytes(data)
        return folder, webui, private, old

    def patch_runtime(self, webui, private, *, fail_after=False):
        # No real docker/container access. Use fixed identities and record
        # expected probe content, failing exactly after candidate publish.
        token = "unchanged container identity"
        def verify(expected, wait_seconds=12):
            if fail_after and expected == self.reviewed:
                raise RuntimeError("SIMULATED_HTTP_FAILURE")
            for name, data in expected.items():
                if (webui / name).read_bytes() != data:
                    raise RuntimeError("DUMMY_HTTP_RESPONSE_WRONG_" + name)
        patches = [
            mock.patch.object(pub, "WEBUI", webui),
            mock.patch.object(pub, "PRIVATE", private),
            mock.patch.object(pub, "assert_safe_files", return_value=None),
            mock.patch.object(pub, "runtime_identities", return_value={name:(token,"date") for name in pub.IMMUTABLE_CONTAINERS}),
            mock.patch.object(pub, "identity", return_value=(token,"date")),
            mock.patch.object(pub, "protected_hashes", return_value={"fake-code-guard":"unchanged"}),
            mock.patch.object(pub, "fetch_reviewed_source", return_value=self.reviewed),
            mock.patch.object(pub, "verify", side_effect=verify),
        ]
        return patches

    def test_success_atomic_bytes_preserved_code_and_reversible_backup(self):
        temp, webui, private, old = self.make_sandbox()
        try:
            with self.patch_runtime_context(webui, private):
                pub.main()
            for name, data in self.reviewed.items():
                self.assertEqual(data,(webui/name).read_bytes())
            backups = list((private/"backups").glob("webui-v2-*"))
            self.assertEqual(1,len(backups))
            for name, data in old.items():
                self.assertEqual(data,(backups[0]/name).read_bytes())
            manifest = (backups[0]/"manifest.json").read_text()
            self.assertNotIn("secret", manifest.lower())
            self.assertIn(pub.SOURCE_COMMIT, manifest)
        finally:
            temp.cleanup()

    def test_failure_rolls_back_all_3_original_customized_bytes(self):
        temp, webui, private, old = self.make_sandbox()
        try:
            with self.patch_runtime_context(webui, private, fail_after=True):
                with self.assertRaisesRegex(RuntimeError, "SIMULATED_HTTP_FAILURE"):
                    pub.main()
            for name, data in old.items():
                self.assertEqual(data,(webui/name).read_bytes())
            self.assertEqual(1,len(list((private/"backups").glob("webui-v2-*"))))
        finally:
            temp.cleanup()

    def test_identical_source_noop_without_backup(self):
        temp, webui, private, _ = self.make_sandbox()
        try:
            for name, data in self.reviewed.items():
                (webui/name).write_bytes(data)
            with self.patch_runtime_context(webui, private):
                pub.main()
            self.assertFalse((private/"backups").exists())
        finally:
            temp.cleanup()

    from contextlib import contextmanager
    @contextmanager
    def patch_runtime_context(self, webui, private, fail_after=False):
        patches=self.patch_runtime(webui, private, fail_after=fail_after)
        try:
            for patch in patches:patch.start()
            yield
        finally:
            for patch in reversed(patches):patch.stop()


if __name__ == "__main__":
    unittest.main()
