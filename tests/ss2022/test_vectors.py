#!/usr/bin/env python3
"""Independent SIP022 vector/negative tests against the imported production C.

Uses Python blake3 and cryptography AESGCM, NOT the vendored C cryptography.
The fixed values are public test fixtures, never real VPS credentials.
"""
from __future__ import annotations

import os
import struct
import subprocess
import sys

from blake3 import blake3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROBE = os.environ.get("SS2022_PROBE", "/tmp/s3_ss2022_probe")
PSK = bytes(range(16))
REQ_SALT = bytes(range(0x10, 0x20))
RESP_SALT = bytes(range(0x20, 0x30))
NOW = 1_700_000_000
CONTEXT = "shadowsocks 2022 session subkey"


def subkey(salt: bytes, psk: bytes = PSK) -> bytes:
    h = blake3(derive_key_context=CONTEXT)
    h.update(psk + salt)
    return h.digest(length=16)


def seal(aes: AESGCM, nonce: int, data: bytes) -> bytes:
    return aes.encrypt(nonce.to_bytes(12, "little"), data, None)


def call(*args: str) -> str:
    result = subprocess.run(
        [PROBE, *args], check=True, capture_output=True, text=True
    )
    return result.stdout


def check_request() -> None:
    domain = b"example.org"
    padding = bytes(range(9))
    variable = (
        bytes([3, len(domain)])
        + domain
        + struct.pack("!H", 443)
        + struct.pack("!H", len(padding))
        + padding
    )
    fixed = bytes([0]) + struct.pack("!QH", NOW, len(variable))
    aes = AESGCM(subkey(REQ_SALT))
    expected_request = (
        REQ_SALT
        + seal(aes, 0, fixed)
        + seal(aes, 1, variable)
    )
    expected_payload = (
        seal(aes, 2, struct.pack("!H", 5))
        + seal(aes, 3, b"hello")
    )
    lines = dict(line.split(" ", 1) for line in call("request").strip().splitlines())
    assert bytes.fromhex(lines["REQUEST"]) == expected_request, "SIP022 request vector mismatch"
    assert bytes.fromhex(lines["PAYLOAD"]) == expected_payload, "SIP022 TCP payload vector mismatch"
    print("PASS independent BLAKE3/AES-GCM request and payload vectors")


def make_response(
    *,
    timestamp: int = NOW,
    request_salt: bytes = REQ_SALT,
    psk: bytes = PSK,
    body: bytes = b"server",
    later: bytes = b"reply",
) -> bytes:
    aes = AESGCM(subkey(RESP_SALT, psk))
    fixed = (
        b"\x01"
        + struct.pack("!Q", timestamp)
        + request_salt
        + struct.pack("!H", len(body))
    )
    return (
        RESP_SALT
        + seal(aes, 0, fixed)
        + seal(aes, 1, body)
        + seal(aes, 2, struct.pack("!H", len(later)))
        + seal(aes, 3, later)
    )


def check_response() -> None:
    stream = make_response()
    for chunk in (1, 2, 3, 7, 16, 64, len(stream)):
        lines = dict(line.split(" ", 1) for line in
                     call("response", stream.hex(), "valid", str(chunk)).strip().splitlines())
        assert bytes.fromhex(lines["RESPONSE"]) == b"serverreply"
    print("PASS authenticated response, fragmented reads and incremental chunk parser")
    assert "RESPONSE" in call(
        "response", make_response(timestamp=NOW + 30).hex(), "valid", "1"
    )
    for desc, wire in (
        ("timestamp >30s", make_response(timestamp=NOW + 31)),
        ("request salt binding", make_response(request_salt=bytes(16))),
        ("wrong PSK", make_response(psk=bytes([0xff] * 16))),
    ):
        assert "PASS invalid response rejected" in call(
            "response", wire.hex(), "invalid", "1"
        ), desc
    corrupt_header = bytearray(stream)
    corrupt_header[58] ^= 1
    corrupt_payload = bytearray(stream)
    corrupt_payload[-1] ^= 1
    for desc, wire in (
        ("header AEAD tag corruption", corrupt_header),
        ("payload AEAD tag corruption", corrupt_payload),
    ):
        assert "PASS invalid response rejected" in call(
            "response", bytes(wire).hex(), "invalid", "7"
        ), desc
    print("PASS timestamp, PSK, salt binding and AES-GCM tamper rejection")


if __name__ == "__main__":
    check_request()
    check_response()
    assert "PASS request rejection" in call("negative")
    print("PASS request size checks and maximum TCP frame 65535")
    print("SS2022 P2-1 independent test vectors: PASS")
