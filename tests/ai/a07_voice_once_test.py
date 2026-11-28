#!/usr/bin/env python3
"""No-network, no-Docker regression for A07 one-shot release."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("release", ROOT / "tools/ai/a07-voice-once.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
assert len(p.BLOBS) == 2
assert p.git_blob(b"hello") == "b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0"
for source, expected in [
    ("A07_PACING_ENGINE_PASS:\nA07_PACING_STATUS: no active trial", "baseline"),
    ("A07_PACING_ENGINE_PASS:\nA07_PACING_STATUS: active send_delay=60ms, original backup present", "active"),
    ("A07_PACING_ENGINE_PASS:\nA07_PACING_STATUS: baseline restored; snapshot retained", "restored"),
]:
    assert p.status_kind(source) == expected
for bad in ["A07_PACING_STATUS: active send_delay=60ms, original backup present", ""]:
    try:
        p.status_kind(bad)
    except p.SafeStop:
        pass
    else:
        raise AssertionError("status guard missing")


def fake_release(mode, states, changed=False, failed=False):
    observed = []
    statuses = iter(states)
    def fake_helper(_, action):
        observed.append(action)
        if action == "status":
            return "A07_PACING_ENGINE_PASS:\nA07_PACING_STATUS: " + next(statuses)
        if failed:
            raise p.SafeStop("PACING_HELPER_APPLY_BLOCKED")
        return ""
    with tempfile.TemporaryDirectory(prefix="a07-offline-") as tmp:
        root = Path(tmp)
        def immutable():
            return {"one": ("changed" if changed and "apply" in observed else "baseline")}
        buf = io.StringIO()
        with patch.object(p, "ROOT", root), patch.object(p, "LOCK", root / ".a07-voice-once.lock"), \
             patch.object(p, "fetch_pinned", return_value={path:b"fixture" for path in p.BLOBS}), \
             patch.object(p, "protected_fingerprint", side_effect=immutable), \
             patch.object(p, "helper_call", side_effect=fake_helper), \
             patch.object(p.os, "geteuid", return_value=0), \
             contextlib.redirect_stdout(buf):
            try:
                p.release(mode)
                error = None
            except p.SafeStop as err:
                error = str(err)
        return observed, error, buf.getvalue()

baseline = "no active trial"
active = "active send_delay=60ms, original backup present"
obs, err, out = fake_release("apply", [baseline, active])
assert err is None and obs == ["status", "apply", "status"]
assert "A07_VOICE_PACING_60MS_ACTIVE_PASS" in out
assert "A07_CHECK_1_4_DOCKER_CONTAINERS_START" in out
assert "A07_CHECK_2_4_AUDIO_ENGINE_READ_ONLY_START" in out
assert "A07_CHECK_3_4_BACKUP_AND_A03_ONLY_RESTART_START" in out
assert "A07_CHECK_4_4_FINAL_AUDIO_CONFIG_AND_CONTAINERS_START" in out
obs, err, out = fake_release("apply", [active])
assert err is None and obs == ["status"]
assert "A07_VOICE_PACING_ALREADY_ACTIVE_PASS" in out
obs, err, out = fake_release("rollback", [active, baseline])
assert err is None and obs == ["status", "rollback", "status"]
assert "A07_VOICE_ROLLBACK_AND_OTA_WSS_PASS" in out
obs, err, out = fake_release("rollback", [baseline])
assert err == "ROLLBACK_REQUIRES_ACTIVE_TRIAL" and obs == ["status"]
obs, err, out = fake_release("apply", ["configuration drift; do not overwrite until reviewed"])
assert err == "PREVIOUS_TRIAL_REQUIRES_REVIEW" and obs == ["status"]
obs, err, out = fake_release("apply", [baseline], failed=True)
assert err == "PACING_HELPER_APPLY_BLOCKED" and obs == ["status", "apply"]
obs, err, out = fake_release("apply", [baseline, active], changed=True)
assert err == "PROTECTED_CONTAINERS_CHANGED" and obs == ["status","apply","status","rollback"]
assert "A07_VOICE_POSTCHECK_ROLLBACK_PASS" in out
assert "PRIVATE" not in out and "fixture" not in out
print("A07_VOICE_ONE_SHOT_TEST_PASS: base, idempotency, rollback and protected-container guards")
