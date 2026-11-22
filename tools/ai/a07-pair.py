#!/usr/bin/env python3
"""A07: firmware-independent one-time OTA pairing with original Caddy.

The enrollment endpoint always returns HTTP 403; only an owner-authorized
pairing step enables the upstream OTA. Device IDs are captured in container
tmpfs and never written into Caddy's public access logs. No firmware mods.
"""
import argparse
import json
import os
import re
from pathlib import Path

MAC = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CATCHALL = '  handle {\n    respond "Forbidden" 403\n  }\n'
OLD_LOG = '  log {\n    output discard\n  }\n'


def load(path):
    return json.loads(Path(path).read_text())


def private_json(path, obj):
    p = Path(path)
    fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(obj, out)
        out.write("\n")


def enroll_caddy(original, secret):
    if not re.fullmatch(r"[a-f0-9]{64}", secret):
        raise ValueError("invalid secret format")
    if original.count(OLD_LOG) != 1 or original.count(CATCHALL) != 1:
        raise ValueError("current Caddy template differs from A04 baseline")
    logs = (
        "  # A07 only: container tmpfs. Delete entire request/headers/URI from logs.\n"
        "  log {\n"
        "    output file /config/a07-pair.log {\n"
        "      mode 0600\n"
        "      roll_size 1MiB\n"
        "      roll_keep 1\n"
        "    }\n"
        "    format filter {\n"
        "      request delete\n"
        "      resp_headers delete\n"
        "    }\n"
        "  }\n"
    )
    enrolled = (
        "  @a07_enroll {\n"
        "    method POST\n"
        "    path /xiaozhi/ota/" + secret + "\n"
        '    header_regexp Device-Id "^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$"\n'
        '    header_regexp Client-Id "^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"\n'
        "  }\n"
        "  handle @a07_enroll {\n"
        "    log_append pair_device {http.request.header.Device-Id}\n"
        "    log_append pair_client {http.request.header.Client-Id}\n"
        '    respond "A07 enrollment pending approval" 403\n'
        "  }\n\n"
    )
    return original.replace(OLD_LOG, logs, 1).replace(CATCHALL, enrolled + CATCHALL, 1)


def capture(raw, secret):
    candidates = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if "request" in event or secret in line:
            raise ValueError("enrollment log is not sanitized (may contain private URL)")
        a = event.get("pair_device", "").strip().lower()
        b = event.get("pair_client", "").strip().lower()
        if a and b:
            if not MAC.fullmatch(a) or not UUID.fullmatch(b):
                raise ValueError("malformed captured device identity")
            candidates.add((a, b))
    if len(candidates) != 1:
        raise ValueError("must capture exactly one distinct valid real device")
    return next(iter(candidates))


def bound_caddy(original, current, device, client, secret):
    if not MAC.fullmatch(device) or not UUID.fullmatch(client):
        raise ValueError("invalid real hardware identity")
    if not re.fullmatch(r"[a-f0-9]{64}", secret):
        raise ValueError("invalid bearer")
    if current["mode"] != "synthetic":
        raise ValueError("A04 synthetic enrollment already replaced")
    expected = {
        "__PAIR_SECRET__": secret,
        "__DEVICE_ID__": device,
        "__CLIENT_ID__": client,
    }
    # Build *from* the reviewed A04 template, not the temporary log-enabled stage.
    for token, value in expected.items():
        if token not in original:
            raise ValueError("A04 template missing token")
        original = original.replace(token, value)
    return original


def update_ws(original, existing, secret, hostname):
    old = f"  websocket: wss://{hostname}/xiaozhi/v1/{existing}\n"
    new = f"  websocket: wss://{hostname}/xiaozhi/v1/{secret}\n"
    if original.count(old) != 1:
        raise ValueError("A04 configured WSS address changed")
    return original.replace(old, new, 1)


def replace_private(path, text, mode=0o600):
    p = Path(path)
    tmp = p.with_name(p.name + ".a07tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w") as fp:
        fp.write(text)
    os.replace(tmp, p)
    os.chmod(p, mode)


def main():
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="action", required=True)
    s = sp.add_parser("stage-render")
    s.add_argument("--original", required=True)
    s.add_argument("--state", required=True)
    s.add_argument("--output", required=True)
    s = sp.add_parser("capture")
    s.add_argument("--log", required=True)
    s.add_argument("--state", required=True)
    s.add_argument("--output", required=True)
    s = sp.add_parser("bind-render")
    s.add_argument("--template", required=True)
    s.add_argument("--synthetic", required=True)
    s.add_argument("--candidate", required=True)
    s.add_argument("--state", required=True)
    s.add_argument("--out-caddy", required=True)
    s.add_argument("--out-identity", required=True)
    s.add_argument("--config", required=True)
    s.add_argument("--out-config", required=True)
    a = p.parse_args()
    if a.action == "stage-render":
        replace_private(a.output, enroll_caddy(Path(a.original).read_text(), load(a.state)["pair_secret"]), 0o444)
        print("A07_OK: staging-only Caddy gate rendered; unknown device always HTTP 403")
    elif a.action == "capture":
        device, client = capture(Path(a.log).read_text(), load(a.state)["pair_secret"])
        private_json(a.output, {"device_id": device, "client_id": client})
        print("A07_CANDIDATE: one hardware identity captured in private root-only file")
        print("A07_CANDIDATE: device_id suffix=" + device[-5:] + "; client_id suffix=" + client[-6:])
    else:
        current = load(a.synthetic)
        candidate = load(a.candidate)
        original = Path(a.template).read_text()
        device = candidate["device_id"]
        client = candidate["client_id"]
        config = Path(a.config).read_text()
        caddy = bound_caddy(original, current, device, client, load(a.state)["pair_secret"])
        updated = update_ws(config, current["pair_secret"], load(a.state)["pair_secret"], current["hostname"])
        identity = {
            "device_id": device,
            "client_id": client,
            "pair_secret": load(a.state)["pair_secret"],
            "hostname": current["hostname"],
            "mode": "hardware",
        }
        replace_private(a.out_caddy, caddy, 0o444)
        replace_private(a.out_identity, json.dumps(identity) + "\n")
        replace_private(a.out_config, updated)
        print("A07_OK: real-device OTA + WSS Caddy gate rendered with original A04 strict matching")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        # Never print user identities, path secrets or API key-bearing YAML.
        raise SystemExit("A07_BLOCKED: enrollment state/log/config not in expected format; no secrets printed") from None
