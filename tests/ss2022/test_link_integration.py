#!/usr/bin/env python3
"""Independent loopback-only SIP022 TCP peer for real S3-Voice C adapter tests.

Does not use the vendored C core to produce server frames.
No external IP addresses or any real user credential are contacted.
"""
import os
import socket
import struct
import subprocess
import threading
import time

from blake3 import blake3
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PROBE = os.environ.get("S3_LINK_PROBE", "/tmp/s3_ss2022_link_probe")
PSK = bytes(range(16))
RESPONSE_SALT = bytes(range(0x40, 0x50))


def key(salt):
    h = blake3(derive_key_context="shadowsocks 2022 session subkey")
    h.update(PSK + salt)
    return h.digest(length=16)


def decrypt(aes, nonce, frame):
    return aes.decrypt(nonce.to_bytes(12, "little"), frame, None)


def encrypt(aes, nonce, frame):
    return aes.encrypt(nonce.to_bytes(12, "little"), frame, None)


def read_n(sock, size):
    result = bytearray()
    while len(result) < size:
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise AssertionError("EOF before full AEAD frame")
        result.extend(chunk)
    return bytes(result)


def handle_server(sock, mode):
    sock.settimeout(12)
    salt = read_n(sock, 16)
    aes = AESGCM(key(salt))
    header = decrypt(aes, 0, read_n(sock, 27))
    assert header[0] == 0, "request type must be 0"
    timestamp = int.from_bytes(header[1:9], "big")
    assert abs(timestamp - int(time.time())) <= 30, "SNTP timestamp must be recent"
    variable_length = int.from_bytes(header[9:11], "big")
    variable = decrypt(aes, 1, read_n(sock, variable_length + 16))
    assert variable[0] == 3, "domain target required by pinned core"
    host_len = variable[1]
    host = variable[2:2 + host_len].decode("ascii")
    port = int.from_bytes(variable[2 + host_len:4 + host_len], "big")
    pad_len = int.from_bytes(variable[4 + host_len:6 + host_len], "big")
    assert pad_len > 0 and len(variable) == 6 + host_len + pad_len
    is_dns = mode.startswith("dns")
    expected_host = "1.1.1.1" if is_dns else "198.51.100.7"
    assert (host, port) == (expected_host, 53 if is_dns else 443)

    size = int.from_bytes(decrypt(aes, 2, read_n(sock, 18)), "big")
    assert 1 <= size <= 2048
    client_data = decrypt(aes, 3, read_n(sock, size + 16))
    if is_dns:
        assert client_data[:2] == b"\x00\x0c"
        assert client_data[2:4] == b"\x12\x34"
        answer = bytearray(client_data[2:])
        answer[2:4] = b"\x81\x80"
        if mode == "dns-wrong-id":
            answer[1] ^= 0x01
        if mode == "dns-no-qr":
            answer[2] &= 0x7f
        reply = struct.pack("!H", len(answer)) + answer
    else:
        assert client_data == b"ping"
        reply = b"pong"

    response_aes = AESGCM(key(RESPONSE_SALT))
    fixed = b"\x01" + struct.pack("!Q", int(time.time())) + salt + struct.pack("!H", len(reply))
    data = (
        RESPONSE_SALT
        + encrypt(response_aes, 0, fixed)
        + encrypt(response_aes, 1, reply)
    )
    # Exercise partial socket reads and incremental authenticated framing.
    if mode in ("dns-wrong-id", "dns-no-qr"):
        # A complete authenticated but semantically wrong DNS response.
        # Avoid a spurious server-side BrokenPipe when client rejects it.
        sock.sendall(data)
    else:
        for offset in range(0, len(data), 7):
            sock.sendall(data[offset:offset + 7])
            time.sleep(0.001)


def run(mode):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    sock.settimeout(15)
    port = sock.getsockname()[1]
    errors = []

    def server():
        try:
            conn, address = sock.accept()
            assert address[0] == "127.0.0.1"
            with conn:
                handle_server(conn, mode)
        except Exception as exc:
            errors.append(exc)
        finally:
            sock.close()

    thread = threading.Thread(target=server)
    thread.start()
    probe_mode = "dns-reject" if mode in ("dns-wrong-id", "dns-no-qr") else mode
    proc = subprocess.run([PROBE, probe_mode, str(port)], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
    thread.join(timeout=20)
    assert not thread.is_alive(), "mock server hung"
    assert proc.returncode == 0, f"probe failed: {proc.stdout}\n{proc.stderr}; server errors: {errors}"
    assert not errors, f"server failure: {errors}"
    assert "PASS SS2022" in proc.stdout, proc.stdout
    print(proc.stdout.strip())


if __name__ == "__main__":
    subprocess.run([PROBE, "config"], check=True)
    run("relay")
    run("dns")
    run("dns-wrong-id")
    run("dns-no-qr")
    print("PASS P3-3 SS2022 independent AES-GCM TCP/DNS and wrong-ID/QR rejection")
