#!/usr/bin/env python3
"""A06 source-only config regression; no secrets, paid calls or device required."""
import importlib.util
import tempfile
from pathlib import Path

module_path = Path(__file__).resolve().parents[2] / "tools/ai/a06-config.py"
spec = importlib.util.spec_from_file_location("a06", module_path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

original = (
    "server:\n"
    "  websocket: wss://voice.cncloudx.com/xiaozhi/v1/SECRET_NOT_REAL\n"
    "selected_module:\n"
    "  VAD: SileroVAD\n"
    "  ASR: OpenaiASR\n"
    "  LLM: GenericGPTLLM\n"
    "  TTS: EdgeTTS\n"
    "  Memory: nomem\n"
    "ASR:\n"
    "  OpenaiASR:\n"
    "    api_key: PENDING_A05_NOT_A_REAL_KEY\n"
    "LLM:\n"
    "  GenericGPTLLM:\n"
    "    type: openai\n"
    "    base_url: https://service.example/v1\n"
    "    api_key: DUMMY_CI_NOT_VALID\n"
    "    model_name: example-model\n"
    "enable_greeting: false\n"
)
changed = m.transform(original)
assert changed != original
assert changed.count("  ASR: VoskASR\n") == 1
assert changed.count("  LLM: GenericGPTLLM\n") == 1
assert changed.count("  TTS: EdgeTTS\n") == 1
assert changed.count("  VoskASR:\n") == 1
assert "    type: vosk" in changed
assert "    model_path: data/models/vosk/vosk-model-small-cn-0.22" in changed
assert "DUMMY_CI_NOT_VALID" in changed
assert "wss://voice.cncloudx.com/xiaozhi/v1/SECRET_NOT_REAL" in changed
for invalid in (changed, original.replace("  LLM: GenericGPTLLM\n", "  LLM: DeepSeekLLM\n")):
    try:
        m.transform(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("unexpected baseline accepted")

with tempfile.TemporaryDirectory(prefix="a06-") as tmp:
    c = Path(tmp) / ".config.yaml"
    c.write_text(original)
    old = c.read_bytes()
    m.apply(str(c))
    assert c.read_text() == changed
    assert c.stat().st_mode & 0o077 == 0
    c.write_bytes(old)
    assert c.read_bytes() == old
print("A06_CONFIG_PASS: only ASR selection and official Vosk block changed; existing A04 WSS, GPT, EdgeTTS preserved and reversible")
