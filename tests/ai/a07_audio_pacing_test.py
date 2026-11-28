#!/usr/bin/env python3
"""Official config-only 60ms audio pacing: byte-preserving reversible tests."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = spec_from_file_location("pacing", root / "tools/ai/a07-audio-pacing.py")
p = module_from_spec(spec)
spec.loader.exec_module(p)

base = (
    "server:\n  websocket: wss://voice.cncloudx.com/xiaozhi/v1/PRIVATE_PATH\n"
    "selected_module:\n  ASR: VoskASR\n  LLM: GenericGPTLLM\n  TTS: EdgeTTS\n"
    "LLM:\n  GenericGPTLLM:\n    api_key: PRIVATE_NOT_REAL\n"
)
assert p.render(base) == base + "tts_audio_send_delay: 60\n"
original = base + "tts_audio_send_delay: 0\n"
trial = p.render(original)
assert trial == base + "tts_audio_send_delay: 60\n"
assert p.sha(original) != p.sha(trial)
assert p.sha(trial) == p.sha(p.render(original))
assert "PRIVATE_NOT_REAL" in trial
assert "  ASR: VoskASR" in trial and "  LLM: GenericGPTLLM" in trial
assert "wss://voice.cncloudx.com/xiaozhi/v1/PRIVATE_PATH" in trial
with_comment = base + "tts_audio_send_delay: 0 # official default\n"
assert p.render(with_comment).endswith("tts_audio_send_delay: 60 # official default\n")
for bad in (base+"tts_audio_send_delay: 40\n",
            base+"tts_audio_send_delay: 0\ntts_audio_send_delay: 0\n",
            base.rstrip("\n")):
    try:
        p.render(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe existing config accepted")
print("A07_PACING_STATIC_PASS: original 0 -> official 60ms; all A03/A04/A05/A06 credentials/routes preserved")


# v0.9.8 audit must match the running sender before a production config edit.
from unittest.mock import patch
from types import SimpleNamespace
import json
import tempfile
import ast

v098 = {
    "frame_duration_ms": 60,
    "default_prebuffer_packets": 5,
    "reads_native_delay": True,
    "positive_delay_queues_all": True,
    "stop_waits_for_audio": True,
}
assert p.check_runtime_metadata(v098) == v098
for altered in ({**v098, "default_prebuffer_packets": 2},
                {**v098, "reads_native_delay": False},
                {**v098, "positive_delay_queues_all": False},
                {**v098, "stop_waits_for_audio": False}, {}):
    try:
        p.check_runtime_metadata(altered)
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected runtime source accepted")

def fake_inspect(cmd, **kwargs):
    assert cmd[:5] == ["docker","exec","-w","/opt/xiaozhi-esp32-server",
                       "s3-voice-ai-server"]
    assert cmd[-2:] and cmd[-2] == "-c"
    assert "tts_audio_send_delay" in cmd[-1]
    ast.parse(cmd[-1])  # must be runnable python, not literal escaped newlines
    return SimpleNamespace(returncode=0, stdout=json.dumps(v098) + "\n")

with patch.object(p.subprocess, "run", side_effect=fake_inspect):
    assert p.runtime_source_audit() == v098

# The old baseline accidentally pinned a particular LLM adapter.
# Choosing another compatible API module must not block a pacing-only trial.
with tempfile.TemporaryDirectory(prefix="a07-provider-neutral-") as td:
    from pathlib import Path
    cfgfile = Path(td) / "config.yaml"
    identfile = Path(td) / "identity.json"
    identfile.write_text('{"mode":"hardware"}')
    for adapter in ["GenericGPTLLM", "AlternateCompatibleAPI"]:
        safe_cfg = (f"selected_module:\n  ASR: VoskASR\n"
                    f"  LLM: {adapter}\n  TTS: EdgeTTS\n"
                    "LLM:\n  credentials: PRIVATE_PLACEHOLDER\n")
        cfgfile.write_text(safe_cfg)
        with patch.object(p, "CFG", cfgfile), patch.object(p, "IDENTITY", identfile), \
             patch.object(p.os, "geteuid", return_value=0):
            assert p.ensure_baseline() == safe_cfg
    cfgfile.write_text("selected_module:\n  ASR: VoskASR\n  TTS: EdgeTTS\n")
    with patch.object(p, "CFG", cfgfile), patch.object(p, "IDENTITY", identfile), \
         patch.object(p.os, "geteuid", return_value=0):
        try:
            p.ensure_baseline()
        except ValueError:
            pass
        else:
            raise AssertionError("missing LLM selection accepted")
print("A07_RUNTIME_AUDIT_PASS: pinned v0.9.8 source, no credentials, provider-neutral selection")
