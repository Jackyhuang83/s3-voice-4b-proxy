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
