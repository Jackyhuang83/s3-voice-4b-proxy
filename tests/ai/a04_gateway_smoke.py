#!/usr/bin/env python3
"""A04 fail-closed OTA/WebSocket smoke using Python stdlib only.

Known IDs are synthetic in A04. The 256-bit route secret is loaded from a
private server-side file, never printed or passed on the process command line.
"""
import argparse
import base64
import json
import os
import socket
import ssl
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--identity", required=True)
parser.add_argument("--origin", required=True)
args = parser.parse_args()
data = json.loads(Path(args.identity).read_text())
origin = urllib.parse.urlsplit(args.origin)
assert origin.scheme in ("http", "https")
host, port = origin.hostname, origin.port or (443 if origin.scheme == "https" else 80)
assert host and not origin.path or origin.path in ("", "/")

secret = data["pair_secret"]
device_id = data["device_id"]
client_id = data["client_id"]
expected_ws_url = "wss://" + data["hostname"] + "/xiaozhi/v1/" + secret
ota_path = "/xiaozhi/ota/" + secret
ws_path = "/xiaozhi/v1/" + secret
headers = {"Device-Id": device_id, "Client-Id": client_id,
           "Content-Type": "application/json", "User-Agent": "a04-integration-smoke"}
payload = json.dumps({"application":{"version":"2.6.0"},
                      "board":{"type":"a04-synthetic-board"}}).encode()

def status_http(path, request_headers, method="POST"):
    body = payload if method == "POST" else None
    req = urllib.request.Request(args.origin.rstrip("/") + path, data=body,
                                 headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status, resp.read(16384)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(16384)

def check_status(name, got, expected):
    if got != expected:
        raise AssertionError("%s expected HTTP %d, got %d" % (name, expected, got))
    print("A04_TEST_PASS: " + name + " HTTP " + str(got))

status, body = status_http(ota_path, headers)
check_status("known identity + secret OTA", status, 200)
response = json.loads(body)
assert response.get("firmware", {}).get("url", "wrong") == "", "OTA offers unexpected firmware"
assert response.get("firmware", {}).get("version") == "2.6.0", "version mismatch"
assert response.get("websocket", {}).get("url") == expected_ws_url, "incorrect WSS URI"
token = response.get("websocket", {}).get("token", "")
assert isinstance(token, str) and len(token) > 24, "missing upstream JWT"
assert not response.get("mqtt"), "unexpected MQTT config"
print("A04_TEST_PASS: version, no firmware update, WSS address, JWT, no MQTT")

check_status("wrong device ID",status_http(ota_path,dict(headers,**{"Device-Id":"02:00:00:00:00:02"}))[0],403)
check_status("wrong client ID",status_http(ota_path,dict(headers,**{"Client-Id":"00000000-0000-4000-8000-000000000000"}))[0],403)
check_status("wrong shared secret",status_http("/xiaozhi/ota/"+"0"*64,headers)[0],403)
check_status("unauthorized OTA GET",status_http(ota_path,headers,method="GET")[0],403)
check_status("deny firmware binary download",status_http("/xiaozhi/ota/download/fake.bin",headers,method="GET")[0],403)
check_status("deny public generic HTTP route",status_http("/",headers,method="GET")[0],403)
check_status("deny ordinary WS-path GET",status_http(ws_path,headers,method="GET")[0],403)

def websocket_handshake(path, who, client, auth, expect):
    conn = socket.create_connection((host, port), timeout=12)
    if origin.scheme == "https":
        conn = ssl.create_default_context().wrap_socket(conn, server_hostname=host)
    conn.settimeout(8)
    key = base64.b64encode(os.urandom(16)).decode()
    request = ("GET " + path + " HTTP/1.1\r\n" +
               "Host: " + host + "\r\n" +
               "Upgrade: websocket\r\n" +
               "Connection: Upgrade\r\n" +
               "Sec-WebSocket-Key: " + key + "\r\n" +
               "Sec-WebSocket-Version: 13\r\n" +
               "Device-Id: " + who + "\r\n" +
               "Client-Id: " + client + "\r\n" +
               "Authorization: Bearer " + auth + "\r\n" +
               "\r\n").encode()
    conn.sendall(request)
    received = b""
    while b"\r\n\r\n" not in received and len(received) < 16384:
        block = conn.recv(2048)
        if not block: break
        received += block
    first = received.split(b"\r\n",1)[0].decode("ascii","replace")
    try: code = int(first.split()[1])
    except (IndexError,ValueError): raise AssertionError("invalid HTTP handshake response")
    if code != expect:
        raise AssertionError("WebSocket handshake expected HTTP %d got %d" % (expect,code))
    if code == 101:
        # Send one masked v1 hello message (not listen/start and no paid AI calls).
        hello = json.dumps({"type":"hello","version":1,"transport":"websocket",
                "audio_params":{"format":"opus","sample_rate":24000,
                                "channels":1,"frame_duration":60}}).encode()
        mask = os.urandom(4)
        if len(hello) < 126:
            header = bytes([0x81,0x80 | len(hello)])
        else:
            header = bytes([0x81,0x80 | 126]) + struct.pack("!H",len(hello))
        conn.sendall(header + mask + bytes(v ^ mask[i%4] for i,v in enumerate(hello)))
        # No fake Opus or "listen" message: server contains intentionally invalid ASR/LLM keys.
        time.sleep(0.1)
    conn.close()
    return code

check_status("reject WS wrong client before upgrade",websocket_handshake(ws_path,device_id,"00000000-0000-4000-8000-000000000000",token,403),403)
check_status("reject WS wrong shared secret",websocket_handshake("/xiaozhi/v1/"+"0"*64,device_id,client_id,token,403),403)
check_status("accept known WS upgrade and v1 hello",websocket_handshake(ws_path,device_id,client_id,token,101),101)
print("A04_TEST_PASS: OTA and WebSocket gateway admission (synthetic IDs)")
