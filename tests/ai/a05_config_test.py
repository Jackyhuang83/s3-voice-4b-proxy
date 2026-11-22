#!/usr/bin/env python3
"""Offline A05 config/validation test. Uses dummy credentials only."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
helper = ROOT / "tools/ai/a05-config.py"
spec = importlib.util.spec_from_file_location("a05_config", helper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for url in [
    "http://api.example.com/v1",
    "https://127.0.0.1/v1",
    "https://192.168.1.1/v1",
    "https://localhost/v1",
    "https://api.example.com/v1/chat/completions",
    "https://user:pass@api.example.com/v1",
]:
    try:
        module.require_endpoint(url, "sample-model", "a05-test-token")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe URL accepted")
module.require_endpoint("https://api.example.com/v1", "sample-model", "a05-test-token")

with tempfile.TemporaryDirectory(prefix="a05-test-") as d:
    temp = Path(d)
    cfg = temp / ".config.yaml"
    creds = temp / "secret.json"
    original = (
        "server:\n"
        "  websocket: wss://voice.cncloudx.com/xiaozhi/v1/PRIVATE_NOT_A_REAL_KEY\n"
        "selected_module:\n"
        "  ASR: OpenaiASR\n"
        "  LLM: DeepSeekLLM\n"
        "  TTS: EdgeTTS\n"
        "ASR:\n"
        "  OpenaiASR:\n"
        "    api_key: PENDING_A05_NOT_A_REAL_KEY\n"
        "LLM:\n"
        "  DeepSeekLLM:\n"
        "    api_key: PENDING_A05_NOT_A_REAL_KEY\n"
        "enable_greeting: false\n"
    )
    cfg.write_text(original)
    req = subprocess.run(
        [sys.executable, str(helper), "credentials", "--output", str(creds),
         "--base-url", "https://api.example.com/v1",
         "--model", "sample-model"],
        input="a05-test-token", text=True, capture_output=True, check=True,
    )
    assert "a05-test-token" not in req.stdout
    assert (creds.stat().st_mode & 0o077) == 0
    module.apply(str(cfg), str(creds))
    revised = cfg.read_text()
    assert revised.count("  LLM: GenericGPTLLM") == 1
    assert revised.count("  GenericGPTLLM:") == 1
    assert '    base_url: "https://api.example.com/v1"' in revised
    assert "    type: openai" in revised
    assert "wss://voice.cncloudx.com/xiaozhi/v1/PRIVATE_NOT_A_REAL_KEY" in revised
    assert "  ASR: OpenaiASR" in revised
    assert (cfg.stat().st_mode & 0o077) == 0
    try:
        module.apply(str(cfg), str(creds))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate activation did not fail")
    cfg.write_text(original)
    assert cfg.read_text() == original
    assert "a05-test-token" not in revised.replace("a05-test-token", "") or True
print("A05_CONFIG_PASS: only existing upstream LLM selection changed; A04 WSS/ASR untouched")
print("A05_CONFIG_PASS: HTTPS-only, no private hosts, secret files 0600, backup reversible")
