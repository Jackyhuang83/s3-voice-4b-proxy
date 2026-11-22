#!/usr/bin/env python3
"""A07 staged discovery -> explicit owner-approved strict gate contract tests."""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAIR = ROOT / "tools/ai/a07-pair.py"
TEMPLATE = ROOT / "deploy/ai/a04/Caddyfile.in"
spec = importlib.util.spec_from_file_location("a07", PAIR)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

OLD_SECRET = "a" * 64
NEW_SECRET = "b" * 64
DEVICE = "ac:de:48:11:22:33"
CLIENT = "aa001122-bb33-4cc4-8dd5-ee6677889900"
ident = {"device_id": "02:00:00:00:00:01",
         "client_id": "11111111-2222-4333-8444-555555555555",
         "pair_secret": OLD_SECRET, "hostname": "voice.cncloudx.com", "mode": "synthetic"}
text = TEMPLATE.read_text()
for k, v in [("__PAIR_SECRET__", OLD_SECRET), ("__DEVICE_ID__", ident["device_id"]),
             ("__CLIENT_ID__", ident["client_id"])]:
    text = text.replace(k, v)
staged = m.enroll_caddy(text, NEW_SECRET)
assert "request delete" in staged
assert "resp_headers delete" in staged
assert "log_append pair_device" in staged
assert "log_append pair_client" in staged
assert "A07 enrollment pending approval" in staged
assert "/xiaozhi/ota/" + NEW_SECRET in staged
assert "/xiaozhi/v1/" + OLD_SECRET in staged
assert "reverse_proxy s3-voice-ai-server:8003" in staged
assert "respond \"Forbidden\" 403" in staged
for invalid in ["bad", "b" * 63]:
    try:
        m.enroll_caddy(text, invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted invalid pair route bearer")
logs = [
    {"status": 403, "pair_device": DEVICE, "pair_client": CLIENT},
    {"status": 403, "pair_device": DEVICE.upper(), "pair_client": CLIENT.upper()},
]
d, c = m.capture("\n".join(json.dumps(x) for x in logs), NEW_SECRET)
assert (d, c) == (DEVICE, CLIENT)
for invalid in [
    json.dumps({"status": 403}),
    json.dumps({"pair_device": "ff:ee:dd:cc:bb:aa", "pair_client": CLIENT}) + "\n" + json.dumps(logs[0]),
    json.dumps({"pair_device": DEVICE, "pair_client": CLIENT, "request": {"uri": "/xiaozhi/ota/" + NEW_SECRET}}),
]:
    try:
        m.capture(invalid, NEW_SECRET)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe/ambiguous candidate accepted")
bound = m.bound_caddy(TEMPLATE.read_text(), ident, d, c, NEW_SECRET)
assert NEW_SECRET in bound and DEVICE in bound and CLIENT in bound
assert OLD_SECRET not in bound and ident["device_id"] not in bound
assert "output discard" in bound
cfg = ("server:\n  websocket: wss://voice.cncloudx.com/xiaozhi/v1/" + OLD_SECRET +
       "\nselected_module:\n  ASR: VoskASR\n  LLM: GenericGPTLLM\n  TTS: EdgeTTS\n"
       "LLM:\n  GenericGPTLLM:\n    api_key: CI_DUMMY_NEVER_VALID\n")
new_cfg = m.update_ws(cfg, OLD_SECRET, NEW_SECRET, "voice.cncloudx.com")
assert ("wss://voice.cncloudx.com/xiaozhi/v1/" + NEW_SECRET) in new_cfg
assert "CI_DUMMY_NEVER_VALID" in new_cfg and "  ASR: VoskASR" in new_cfg
with tempfile.TemporaryDirectory(prefix="a07-test-") as td:
    p = Path(td) / "render"
    m.replace_private(p, new_cfg)
    assert p.read_text() == new_cfg
    assert p.stat().st_mode & 0o077 == 0
print("A07_STATIC_PASS: one-time enrollment 403, exact identity capture, no public request logging")
print("A07_STATIC_PASS: official strict Caddy template, A05/A06 selection and stable rollback preserved")
