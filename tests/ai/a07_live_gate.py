#!/usr/bin/env python3
"""Exercise the real running Caddy A07 enrollment endpoint in ephemeral CI.

No real board or firmware required; CI sends one synthetic, valid-shaped
real-device OTA request and confirms 403 until owner explicitly binds it.
"""
import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path

P = argparse.ArgumentParser()
P.add_argument("--state", required=True)
P.add_argument("--mode", choices=["stage", "bound"], required=True)
a = P.parse_args()
secret = json.loads(Path(a.state).read_text())["pair_secret"]
url = "http://127.0.0.1:18080/xiaozhi/ota/" + secret
real_id = "ac:de:48:11:22:33"
client = "aa001122-bb33-4cc4-8dd5-ee6677889900"
headers = {"Device-Id": real_id, "Client-Id": client, "Content-Type": "application/json"}
body = json.dumps({"application": {"version": "2.4.0"},
                   "board": {"type": "waveshare-esp32-s3-touch-lcd-4b"}}).encode()


def code(uri, heads=None, method="POST"):
    request = urllib.request.Request(uri, data=body if method == "POST" else None,
                                     headers=heads or headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=12) as res:
            return res.status
    except urllib.error.HTTPError as e:
        return e.code

if a.mode == "stage":
    assert code(url) == 403
    assert code(url.replace(secret, "0" * 64)) == 403
    assert code(url, method="GET") == 403
    assert code(url, {**headers, "Client-Id": "bogus"}) == 403
    print("A07_STAGE_PASS: HTTP 403 for real-shaped device before owner binding")
    print("A07_STAGE_PASS: invalid secret, unauthorized GET, wrong UUID denied")
else:
    assert code(url) == 200
    assert code(url, {**headers, "Client-Id": "00000000-0000-4000-8000-000000000000"}) == 403
    assert code(url, {**headers, "Device-Id": "aa:bb:cc:dd:ee:ff"}) == 403
    assert code(url, method="GET") == 403
    print("A07_BIND_PASS: real-shaped identity OTA 200, wrong identities/GET 403")
