#!/usr/bin/env python3
"""Real TLS 1.2/1.3 VLESS TCP host tests using ephemeral OpenSSL certificate.

Server performs only VLESS request/response framing, not TLS crypto.
Actual production C s3_vless_tls.c -> ESP-TLS API host shim -> OpenSSL.
Uses no remote addresses and no production secrets.
"""
from __future__ import annotations
import argparse
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from pathlib import Path

UUID = bytes(range(16))
PROBE = os.environ.get("S3_VLESS_TLS_PROBE", "/tmp/s3_vless_tls_probe")


def mk_cert(root: Path, stem: str, host: str) -> tuple[str, str]:
    cert, key = root / (stem + ".crt"), root / (stem + ".key")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "2", "-sha256", "-subj", f"/CN={host}",
            "-addext", f"subjectAltName=DNS:{host}",
            "-addext", "basicConstraints=critical,CA:TRUE",
            "-keyout", str(key), "-out", str(cert),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return str(cert), str(key)


def mk_expired_cert(root: Path) -> tuple[str, str, str]:
    """Valid test CA signs a deliberately EXPIRED vless.test leaf/SAN."""
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "P3-3 test CA")])
    root_cert = (
        x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
        .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    server_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    hostname = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vless.test")])
    expired = (
        x509.CertificateBuilder().subject_name(hostname).issuer_name(ca_name)
        .public_key(server_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=30))
        .not_valid_after(now - timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("vless.test")]),
                       critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_file, cert_file, key_file = [root / name for name in
                                    ("expired-ca.pem", "expired-leaf.pem", "expired-key.pem")]
    ca_file.write_bytes(root_cert.public_bytes(serialization.Encoding.PEM))
    cert_file.write_bytes(expired.public_bytes(serialization.Encoding.PEM))
    key_file.write_bytes(server_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    return str(cert_file), str(key_file), str(ca_file)


def read_exact(conn: ssl.SSLSocket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise AssertionError("VLESS peer EOF before request")
        buf.extend(chunk)
    return bytes(buf)


def vless_server(conn: ssl.SSLSocket, mode: str) -> None:
    conn.settimeout(8)
    prefix = read_exact(conn, 23)
    assert prefix[0] == 0 and prefix[1:17] == UUID
    assert prefix[17] == 0 and prefix[18] == 1  # no addons, TCP
    target_port = int.from_bytes(prefix[19:21], "big")
    assert prefix[21] == 2  # domain encoding from upstream
    host_len = prefix[22]
    host = read_exact(conn, host_len).decode("ascii")
    is_dns = mode == "dns" or mode.startswith("dns-")
    assert (host, target_port) == (
        ("1.1.1.1", 53) if is_dns else ("198.51.100.7", 443)
    )
    if is_dns:
        length = int.from_bytes(read_exact(conn, 2), "big")
        assert length == 22
        q = bytearray(read_exact(conn, length))
        assert q[:2] == b"\x12\x34"
        q[2:4] = b"\x81\x80"
        if mode == "dns-bad-id":
            q[1] ^= 1
        if mode == "dns-no-qr":
            q[2] &= 0x7f
        response = len(q).to_bytes(2, "big") + q
    else:
        assert read_exact(conn, 4) == b"ping"
        response = b"pong"
    response_header = b"\xff\x00" if mode == "bad-header" else b"\x00\x00"
    payload = response_header + response
    for index in range(0, len(payload), 3):
        conn.sendall(payload[index:index + 3])
        time.sleep(0.003)
    # Keep the TLS session open until the client closes, so a valid
    # authenticated response is not raced by a server-side abrupt EOF.
    conn.settimeout(3)
    try:
        conn.recv(1)
    except (ssl.SSLError, TimeoutError, ConnectionError):
        pass


def run_case(case: str, pem: str, key: str, unrelated_ca: str,
             trusted_ca: str | None = None) -> None:
    env = os.environ.copy()
    ipv6 = os.environ.get("S3_VLESS_TEST_FAMILY") == "6"
    if ipv6:
        # No direct-IP override: force the host shim to resolve vless.test
        # through the system resolver /etc/hosts AAAA fixture in CI.
        env.pop("S3_VLESS_TEST_CONNECT_IP", None)
    else:
        env["S3_VLESS_TEST_CONNECT_IP"] = "127.0.0.1"
    env["S3_VLESS_TEST_CA"] = unrelated_ca if case == "bad-ca" else (trusted_ca or pem)
    with socket.socket(socket.AF_INET6 if ipv6 else socket.AF_INET,
                       socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if ipv6:
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        sock.bind(("::1" if ipv6 else "127.0.0.1", 0))
        port = sock.getsockname()[1]
        should_accept = case not in ("offline", "numeric-host")
        errors: list[Exception] = []
        received_sni: list[str | None] = []
        if should_accept:
            sock.listen(1)
            sock.settimeout(10)

            def server():
                try:
                    peer, addr = sock.accept()
                    assert addr[0] == ("::1" if ipv6 else "127.0.0.1")
                    with peer:
                        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                        ctx.load_cert_chain(certfile=pem, keyfile=key)
                        ctx.set_servername_callback(
                            lambda _sock, name, _ctx: received_sni.append(name)
                        )
                        try:
                            with ctx.wrap_socket(peer, server_side=True) as conn:
                                if case in ("bad-ca", "wrong-host", "wrong-host-dns", "expired"):
                                    # A rejecting TLS client may disconnect after
                                    # handshake and before sending any VLESS data.
                                    try:
                                        conn.recv(1)
                                    except (ssl.SSLError, ConnectionError, TimeoutError):
                                        pass
                                    return
                                vless_server(conn, case)
                        except (ssl.SSLError, ConnectionError, BrokenPipeError):
                            if case not in ("bad-ca", "wrong-host", "wrong-host-dns", "expired"):
                                raise
                except Exception as exc:
                    errors.append(exc)

            thread = threading.Thread(target=server)
            thread.start()
        else:
            # Close listener immediately: connection must fail without a plain
            # TCP retry, including when numeric-host is rejected before dial.
            pass
        probe_case = "dns-reject" if case in ("dns-bad-id", "dns-no-qr") else case
        result = subprocess.run([PROBE, probe_case, str(port)], env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=22)
        if should_accept:
            thread.join(timeout=11)
            assert not thread.is_alive(), "TLS peer hung"
            assert not errors, f"TLS server errors {errors}"
            expected_sni = "wrong.test" if case.startswith("wrong-host") else "vless.test"
            assert received_sni == [expected_sni], (case, received_sni)
        assert result.returncode == 0, f"{case}: {result.stdout}\n{result.stderr}"
        print(result.stdout.strip(), flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="s3-vless-tls-") as d:
        root = Path(d)
        pem, key = mk_cert(root, "server", "vless.test")
        bad, _ = mk_cert(root, "other", "untrusted.test")
        for case in [
            "relay", "dns", "wrong-host", "wrong-host-dns",
            "bad-ca", "bad-header", "offline", "numeric-host",
            "dns-bad-id", "dns-no-qr",
        ]:
            run_case(case, pem, key, bad)
        if os.environ.get("S3_P3_EXTENDED_TLS") == "1":
            expired_pem, expired_key, ca_pem = mk_expired_cert(root)
            run_case("expired", expired_pem, expired_key, bad, trusted_ca=ca_pem)
        print("PASS VLESS verified TLS IPv4/IPv6, DNS binding and optional expired-chain failure")
