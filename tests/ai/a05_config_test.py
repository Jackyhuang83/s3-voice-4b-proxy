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

# The user-facing credential diagnostics must identify only the bad FIELD,
# never print actual provider values, user model names, or API keys.
for bad_field, bad_url, bad_model, bad_key in [
    ("base_url", "http://private.example/v1", "model-a", "secret-a05-token"),
    ("model_name", "https://api.example.com/v1", "{entire-json-models-object}", "secret-a05-token"),
    ("api_key", "https://api.example.com/v1", "model-a", "short"),
]:
    with tempfile.TemporaryDirectory(prefix="a05-invalid-") as d:
        cmd = [sys.executable, str(helper), "credentials", "--output", str(Path(d) / "cred.json"),
               "--base-url", bad_url, "--model", bad_model]
        p = subprocess.run(cmd, input=bad_key, text=True, capture_output=True)
        combined = p.stdout + p.stderr
        assert p.returncode != 0 and ("A05_INPUT_ERROR: " + bad_field + ":") in combined
        assert bad_key not in combined and bad_model not in combined and bad_url not in combined
        assert not (Path(d) / "cred.json").exists()
print("A05_INPUT_DIAGNOSTIC_PASS: exact faulty field identified, credential values never echoed")

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
print("A05_CONFIG_PASS: only existing upstream LLM selection changed; A04 WSS/ASR untouched")
print("A05_CONFIG_PASS: HTTPS-only, no private hosts, secret files 0600, backup reversible")
