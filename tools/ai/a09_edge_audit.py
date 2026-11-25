#!/usr/bin/env python3
"""A09-P2 edge ingress audit: read-only checks, no real phone and no binding code.

Compare a deliberately invalid JSON-array POST at the existing local A04 Caddy
listener and public Cloudflare hostname. Both should return 400 *from A09*.
Do not log or disclose the bearer route secret, URL, request headers, or bodies.
This does not inspect historical requests, Cloudflare account WAF events or
prove what an iPhone app attempted.
"""
import argparse
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request

A09_ROOT = Path("/opt/s3-voice-a09-lite")
A04_CADDY = Path("/opt/s3-voice-ai-edge/Caddyfile")
A09_ENV = A09_ROOT / ".env"
A09_MARKER = A09_ROOT / ".same-host-active"
HOST = "voice.cncloudx.com"
NEW_GATEWAY = "s3-voice-a09-lite-gateway"
ADAPTER = "s3-voice-a09-lite-adapter"
ORIGINAL = ("s3-voice-ai-server", "s3-voice-ai-gateway", "s3-voice-ai-tunnel")
PRIVATE_URL = "http://127.0.0.1:18080"
PUBLIC_URL = "https://" + HOST
DUMMY_HEADERS = {
    "Device-Id": "02:00:00:00:00:fc",
    "Client-Id": "a09-p2-edge-audit",
    "Content-Type": "application/json",
}
# JSON array (not object): rejected inside A09 BEFORE upstream/SQLite.issue.
NEGATIVE_BODY = b"[]"


class Stop(Exception):
    pass


def guard(condition, description):
    if not condition:
        raise Stop(description)


def print_status(key, value):
    # All output fields are static labels or numeric HTTP statuses.
    print("A09_EDGE_%s: %s" % (key, value), flush=True)


def command(*args):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=10, check=False)
    guard(p.returncode == 0, "required Docker read-only inspection failed")
    return p.stdout.decode("utf-8", "replace").strip()


def load_private():
    guard(os.geteuid() == 0, "root required to inspect protected config")
    for p in (A09_ROOT, A04_CADDY, A09_ENV, A09_MARKER):
        guard(p.exists() and not p.is_symlink(), "existing same-host config not installed")
    guard(A09_ROOT.is_dir() and A09_ROOT.stat().st_mode & 0o077 == 0,
          "A09 owner-only directory permission mismatch")
    env = {}
    for line in A09_ENV.read_text().splitlines():
        key, sep, value = line.partition("=")
        guard(sep == "=" and key not in env, "unexpected private environment")
        env[key] = value
    guard(env.get("IOS_HOSTNAME") == HOST, "A09 public hostname does not match existing Tunnel")
    secret = env.get("IOS_SECRET", "")
    guard(re.fullmatch(r"[a-f0-9]{64}", secret) is not None, "invalid existing A09 secret")
    return secret


def inspect_caddy(secret):
    config = A04_CADDY.read_text()
    guard(config.startswith(":8080 {\n"), "unexpected existing A04 gateway")
    guard(config.count("  @ota {") == 1 and config.count("  @ws {") == 1,
          "original 4B identity matchers not found")
    guard(config.count("  # A09-P2-SAME-HOST-BEGIN") == 1 and
          config.count("  # A09-P2-SAME-HOST-END") == 1,
          "original A04 Caddy lacks expected A09 same-host section")
    rule = (
        "  @a09_ota {\n"
        "    method POST\n"
        "    path /xiaozhi/ota/" + secret + "\n"
        "    header Device-Id *\n"
        "    header Client-Id *\n"
        "  }\n"
        "  handle @a09_ota {\n"
        "    reverse_proxy s3-voice-a09-lite-gateway:8080\n"
        "  }\n"
    )
    guard(config.count(rule) == 1, "A04 exact A09 OTA route matcher missing")
    guard('  handle {\n    respond "Forbidden" 403\n  }' in config,
          "default-deny 403 changed")
    print_status("CADDY_CONFIG", "EXACT_A09_ROUTE_PRESENT; ORIGINAL_4B_MATCHERS_PRESENT")


def inspect_docker():
    for name in ORIGINAL + (ADAPTER, NEW_GATEWAY):
        guard(command("docker", "inspect", "-f", "{{.State.Running}}", name) == "true",
              "required original/new container not running")
    mounts = json.loads(command("docker", "inspect", "-f", "{{json .Mounts}}",
                               "s3-voice-ai-gateway"))
    guard(any(m.get("Destination") == "/etc/caddy/Caddyfile"
              and m.get("Source") == str(A04_CADDY)
              and m.get("RW") is False for m in mounts),
          "A04 is not using the inspected bind-mounted Caddyfile")
    gateway_net = json.loads(command("docker", "inspect", "-f",
                                    "{{json .NetworkSettings.Networks}}",
                                    "s3-voice-ai-gateway"))
    new_net = json.loads(command("docker", "inspect", "-f",
                                "{{json .NetworkSettings.Networks}}", NEW_GATEWAY))
    tunnel_net = json.loads(command("docker", "inspect", "-f",
                                 "{{json .NetworkSettings.Networks}}",
                                 "s3-voice-ai-tunnel"))
    front = "s3-voice-ai-edge_front"
    guard(front in gateway_net and front in new_net and front in tunnel_net,
          "existing Cloudflare front Docker network is incomplete")
    print_status("DOCKER", "OLD_AND_NEW_RUNNING; FRONT_NETWORK_SHARED; NO_RESTART")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request_status(base, secret):
    url = base + "/xiaozhi/ota/" + secret
    req = urllib.request.Request(
        url, data=NEGATIVE_BODY, headers=DUMMY_HEADERS, method="POST")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(req, timeout=9) as resp:
            return resp.status, "cf-ray" in resp.headers
    except urllib.error.HTTPError as exc:
        # Deliberately don't read the body, headers, Location or Cf-Ray values.
        return exc.code, "cf-ray" in exc.headers
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return 0, False


def local_gateway_health():
    # Never send an OTA POST to the ORIGINAL enrolled 4B route.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    try:
        with opener.open(PRIVATE_URL + "/", timeout=6):
            return False
    except urllib.error.HTTPError as exc:
        return exc.code == 403
    except (urllib.error.URLError, OSError):
        return False


def verdict(local, public):
    if local == 403:
        return "CADDY_403_LOCAL (route not loaded, matcher mismatch, or gateway deny)"
    if local in (502, 503, 504):
        return "A09_ORIGIN_UNAVAILABLE_LOCAL"
    if local != 400:
        return "A04_LOCAL_UNEXPECTED_STATUS (no Cloudflare attribution possible)"
    if public == 400:
        return "PUBLIC_AND_LOCAL_A09_ROUTE_PASS (does not prove iPhone used this OTA)"
    if public in (301, 302, 303, 307, 308):
        return "PUBLIC_REDIRECT_OR_ACCESS_AUTH (inspect Cloudflare Access/redirect rules)"
    if public in (401, 403, 429):
        return "PUBLIC_DENIED_OR_CHALLENGED (Cloudflare WAF/Access or a different edge path)"
    if public in (404, 502, 503, 504, 520, 521, 522, 523, 524, 530):
        return "PUBLIC_TUNNEL_OR_EDGE_ROUTE_ERROR (inspect Tunnel route and WAF)"
    if public == 0:
        return "PUBLIC_PROBE_UNREACHABLE_FROM_VPS (not proof of iPhone failure)"
    return "PUBLIC_UNEXPECTED_RESPONSE (possible different upstream or security layer)"


def main():
    parser = argparse.ArgumentParser(description="Non-mutating Cloudflare/Caddy A09 route audit")
    parser.add_argument("--local-only", action="store_true",
                        help="Only compare local A04; CI simulator never contacts Cloudflare")
    args = parser.parse_args()
    try:
        secret = load_private()
        inspect_caddy(secret)
        inspect_docker()
        guard(local_gateway_health(), "A04 default-deny probe not HTTP 403")
        local, _ = request_status(PRIVATE_URL, secret)
        print_status("LOCAL_HTTP", local)
        if args.local_only:
            print_status("LOCAL_VERDICT", "PASS" if local == 400 else "FAIL")
            return 0 if local == 400 else 1
        public, cf = request_status(PUBLIC_URL, secret)
        print_status("PUBLIC_HTTP", public)
        print_status("CLOUDFLARE_HEADERS", "PRESENT" if cf else "NOT_OBSERVED")
        print_status("VERDICT", verdict(local, public))
        print_status("READ_ONLY_PASS",
                     "no device/token/OTA secret logged; original 4B and A09 unchanged")
        return 0 if local == 400 and public == 400 else 2
    except (Stop, ValueError, UnicodeError, OSError, subprocess.TimeoutExpired,
            json.JSONDecodeError) as exc:
        print_status("BLOCKED", str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
