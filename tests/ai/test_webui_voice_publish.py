#!/usr/bin/env python3
"""WebUI voice-only publisher: isolated, mocked, no Docker/network/keys."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "voice_release", BASE / "tools/ai/webui_voice_publish.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def exercise(mode, failure=None, already=False):
    old = b"/* current UI v3 */\n"
    new = b"/* reviewed voice onended */\n"
    with tempfile.TemporaryDirectory(prefix="webui-voice-publish-ci-") as folder:
        root = Path(folder)
        src = root / "src"
        voice = src / "webui/audio-ui.mjs"
        voice.parent.mkdir(parents=True)
        voice.write_bytes(new if already else old)
        private = root / "private"
        private.mkdir(mode=0o700)
        folders = {"VOICE": voice, "PRIVATE": private, "BACKUPS": private / "backups",
                   "LOCK": private / "voice.lock"}
        states = {"gateway":("immutable-id","immutable-started-at")}
        def routed(expected):
            if failure == "routes" and voice.read_bytes() == new:
                raise p.Blocked("MOCK_ROUTE_FAIL")
            if p.digest(voice.read_bytes()) != expected:
                raise p.Blocked("SOURCE_NOT_SERVED")
        def install():
            return contextlib.ExitStack()
        patches = install()
        for key, value in folders.items():
            patches.enter_context(patch.object(p,key,value))
        patches.enter_context(patch.object(p,"safe_paths",return_value=None))
        patches.enter_context(patch.object(p,"container_states",return_value=states))
        patches.enter_context(patch.object(p,"guarded_hashes",return_value={"all":"stable"}))
        patches.enter_context(patch.object(p,"verify_routes",side_effect=routed))
        patches.enter_context(patch.object(p,"pinned_voice",return_value=new))
        patches.enter_context(patch.object(p,"BEFORE_BLOB",p.blob(old)))
        patches.enter_context(patch.object(p,"AFTER_BLOB",p.blob(new)))
        output = io.StringIO()
        with patches,contextlib.redirect_stdout(output):
            error=None
            try:
                p.release(mode)
            except p.Blocked as e:
                error=str(e)
            final=voice.read_bytes()
            backups=list((private/"backups").glob("webui-voice-*/before.mjs")) if (private/"backups").exists() else []
            preserved=[x.read_bytes() for x in backups]
            markers=list((private/"backups").glob("webui-voice-*/rolled-back")) if backups else []
            if mode=="apply" and error is None and not already:
                assert final==new and preserved==[old]
                p.release("apply") # Idempotent second invocation.
                assert voice.read_bytes()==new
                p.release("rollback")
                assert voice.read_bytes()==old and len(list((private/"backups").glob("webui-voice-*/rolled-back")))==1
            return final, preserved, markers, error, output.getvalue()


final, backups, _, err, out=exercise("apply")
assert final == b"/* reviewed voice onended */\n" and err is None
assert "WEBUI_VOICE_AUDIO_ONLY_ACTIVE_PASS" in out
assert "WEBUI_VOICE_ALREADY_ACTIVE_PASS" in out
assert "WEBUI_VOICE_MANUAL_ROLLBACK_PASS" in out
final, backups, _, err, out=exercise("apply",failure="routes")
assert final == b"/* current UI v3 */\n" and backups==[final]
assert err=="MOCK_ROUTE_FAIL" and "WEBUI_VOICE_FAILED_APPLY_ROLLBACK_PASS" in out
final, backups, _, err, out=exercise("apply",already=True)
assert final == b"/* reviewed voice onended */\n" and err is None and not backups
assert "WEBUI_VOICE_ALREADY_ACTIVE_PASS" in out
final, backups, _, err, out=exercise("rollback")
assert err=="NO_VOICE_BACKUP" and not backups
assert p.blob(b"hello")=="b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
print("WEBUI_VOICE_PUBLISH_TEST_PASS: immutable blob, audio-only apply/idempotency, private backup, explicit rollback, failed-verify recovery, no restarts")
