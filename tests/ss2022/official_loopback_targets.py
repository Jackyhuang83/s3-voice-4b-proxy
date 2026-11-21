#!/usr/bin/env python3
"""Loopback-only TCP target pair for shadowsocks-rust integration CI.

Run with elevated privileges ONLY because 127.0.0.1:53 is a privileged DNS TCP
port. Neither service binds publicly. No real DNS resolver is contacted.
"""
import argparse
import os
import signal
import socket
import socketserver
import threading
import time
from pathlib import Path

ECHO_PORT = 19443
DNS_PORT = 53


class LoopbackServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        payload = self.request.recv(2048)
        if payload == b"ping":
            # Record exactly one successful proxy target hit; replay/offline
            # attempts must NOT create a second target connection.
            with open(self.server.echo_log, "a", encoding="utf-8") as output:
                output.write("ping\n")
            self.request.sendall(b"pong")
        else:
            raise AssertionError(f"invalid echo payload length: {len(payload)}")


def recv_exact(sock, length):
    data = bytearray()
    while len(data) < length:
        block = sock.recv(length - len(data))
        if not block:
            raise AssertionError("unexpected EOF from encrypted TCP DNS stream")
        data.extend(block)
    return bytes(data)


class DnsTcp(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        size = int.from_bytes(recv_exact(self.request, 2), "big")
        if not 12 <= size <= 512:
            raise AssertionError("invalid TCP DNS frame length")
        request = bytearray(recv_exact(self.request, size))
        assert request[0:2] == b"\x12\x34"
        request[2:4] = b"\x81\x80"  # Standard success, zero answers.
        response = len(request).to_bytes(2, "big") + request
        self.request.sendall(response)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", required=True)
    parser.add_argument("--echo-log", required=True)
    args = parser.parse_args()
    assert not os.path.exists(args.ready)
    Path(args.echo_log).write_text("", encoding="utf-8")
    server_echo = LoopbackServer(("127.0.0.1", ECHO_PORT), Echo)
    server_echo.echo_log = args.echo_log
    server_dns = LoopbackServer(("127.0.0.1", DNS_PORT), DnsTcp)
    for server in (server_echo, server_dns):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    Path(args.ready).write_text("127.0.0.1 only\n", encoding="utf-8")
    print(f"READY TCP echo on 127.0.0.1:{ECHO_PORT}, TCP DNS on 127.0.0.1:{DNS_PORT}", flush=True)
    signal.signal(signal.SIGTERM, lambda *_: exit(0))
    while True:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
