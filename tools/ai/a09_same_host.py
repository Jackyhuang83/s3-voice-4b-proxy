#!/usr/bin/env python3
"""A09 P2 single-host owner pilot: preserve the original A04 gateway and Tunnel.

Root-only, explicit local application of extra Caddy routes; does NOT modify
Cloudflare, A03 configs, old 4B device secrets, firmware or original containers.
Requires already-installed, healthy A09-Lite. Fails closed with scoped rollback.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

A09 = Path("/opt/s3-voice-a09-lite")
A04 = Path("/opt/s3-voice-ai-edge")
CADDY = A04 / "Caddyfile"
ENV = A09 / ".env"
OLD_CADDY = A09 / ".pre-same-host-a04.Caddyfile"
OLD_ENV = A09 / ".pre-same-host-env"
MARKER = A09 / ".same-host-active"
HOST = "voice.cncloudx.com"
ORIGINAL = ("s3-voice-ai-server", "s3-voice-ai-gateway", "s3-voice-ai-tunnel")
NEW = ("s3-voice-a09-lite-adapter", "s3-voice-a09-lite-gateway")
# This deliberately matches ONLY the final A04 default-deny block.
FALLBACK = '  handle {\n    respond "Forbidden" 403\n  }\n}'
START = "  # A09-P2-SAME-HOST-BEGIN\n"
END = "  # A09-P2-SAME-HOST-END\n"
HEX64 = re.compile(r"[a-f0-9]{64}\Z")
ORIGINAL_OTA = re.compile(r"(?m)^    path /xiaozhi/ota/([a-f0-9]{64})$")
ORIGINAL_WS = re.compile(r"(?m)^    path /xiaozhi/v1/([a-f0-9]{64})$")


class Stop(Exception):
    pass


def note(status, message):
    print(f"A09_P2_SAME_HOST_{status}: {message}", flush=True)


def guard(condition, message):
    if not condition:
        raise Stop(message)


def run(*args, input_data=None, timeout=30):
    p = subprocess.run(args, input=input_data, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode:
        # Never dump stdout/stderr: they can contain secret URL paths.
        raise Stop(f"command failed ({args[0]} {args[1] if len(args) > 1 else ''}; code {p.returncode})")
    return p.stdout.decode("utf-8", "replace").strip()


def require_root():
    guard(os.geteuid() == 0, "root required")
    for path in (A09, A04):
        guard(path.is_dir() and not path.is_symlink(), "expected directory missing or unsafe")
    for p in (CADDY, ENV):
        guard(p.is_file() and not p.is_symlink(), "expected private file absent or unsafe")
    guard(stat.S_IMODE(A09.stat().st_mode) & 0o077 == 0, "A09 owner directory not private")


def container_ids(names):
    return {name: run("docker", "inspect", "-f", "{{.Id}}", name) for name in names}


def running(names):
    return all(run("docker", "inspect", "-f", "{{.State.Running}}", n) == "true" for n in names)


def assert_mount():
    import json
    mounts = json.loads(run("docker", "inspect", "-f", "{{json .Mounts}}", "s3-voice-ai-gateway"))
    guard(any(m.get("Destination") == "/etc/caddy/Caddyfile"
              and m.get("Source") == str(CADDY) and m.get("RW") is False for m in mounts),
          "original A04 Caddyfile mount unexpectedly changed")


def env_values(data):
    items = {}
    for line in data.splitlines():
        key, eq, value = line.partition("=")
        guard(eq == "=" and key not in items and re.fullmatch(r"[A-Z_]+", key) is not None,
              "unexpected A09 environment format")
        items[key] = value
    guard(items.get("IOS_HOSTNAME") in (HOST, "ios-voice.cncloudx.com"), "unknown A09 hostname")
    guard(HEX64.fullmatch(items.get("IOS_SECRET", "")) is not None, "A09 secret is invalid")
    return items


def original_secret(caddy):
    guard(caddy.startswith(":8080 {\n") and caddy.endswith("}\n"), "unrecognized original Caddyfile")
    guard(FALLBACK in caddy and caddy.count(FALLBACK) == 1, "unexpected default-deny structure")
    guard(caddy.count("  @ota {") == 1 and caddy.count("  @ws {") == 1,
          "original 4B matchers changed")
    ota, ws = ORIGINAL_OTA.findall(caddy), ORIGINAL_WS.findall(caddy)
    guard(len(ota) == len(ws) == 1 and ota[0] == ws[0], "original 4B secret mismatch")
    return ota[0]


def extend_caddy(existing, secret):
    old = original_secret(existing)
    guard(secret != old, "A09 and A04 secrets must differ")
    guard(START not in existing and END not in existing, "single-host extension already exists")
    added = f"""  # A09-P2-SAME-HOST-BEGIN
  @a09_ota {{
    method POST
    path /xiaozhi/ota/{secret}
    header Device-Id *
    header Client-Id *
  }}
  handle @a09_ota {{
    reverse_proxy s3-voice-a09-lite-gateway:8080
  }}

  @a09_ws {{
    method GET
    path /xiaozhi/v1/{secret}
    header Device-Id *
    header Client-Id *
    header Connection *Upgrade*
    header Upgrade websocket
  }}
  handle @a09_ws {{
    reverse_proxy s3-voice-a09-lite-gateway:8080
  }}

  @a09_activation {{
    method POST
    path /xiaozhi/ota/activate
    header Device-Id *
    header Client-Id *
  }}
  handle @a09_activation {{
    reverse_proxy s3-voice-a09-lite-gateway:8080
  }}
  # A09-P2-SAME-HOST-END

"""
    return existing.replace(FALLBACK, added + FALLBACK)


def private_create(path, data):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def same_inode_write(path, data):
    # Important: Docker bind-mounted an inode, not a pathname. os.replace()
    # here would leave the running Caddy container reading the OLD inode.
    guard(path.is_file() and not path.is_symlink(), "Caddy bind-mount source changed")
    before = path.stat()
    with path.open("r+b", buffering=0) as stream:
        stream.seek(0)
        stream.truncate()
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    guard(path.stat().st_ino == before.st_ino, "Caddy inode changed during write")


def compose(*args):
    return run("docker", "compose", "-p", "s3-voice-a09-lite", "-f",
               str(A09 / "docker-compose.yml"), "--env-file", str(ENV), *args, timeout=80)


def caddy_reload():
    return run("docker", "exec", "s3-voice-ai-gateway", "caddy", "reload",
               "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile", timeout=15)


def caddy_adapt(config):
    return run("docker", "exec", "-i", "s3-voice-ai-gateway", "caddy",
               "adapt", "--config", "-", "--adapter", "caddyfile",
               input_data=config.encode(), timeout=15)


def probe(url, device="02:23:45:67:89:ab"):
    req = urllib.request.Request(url, data=b"{broken",
          headers={"Device-Id": device, "Client-Id": "a09-same-host-ci-probe",
                   "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=8) as response:
            return response.status
    except urllib.error.HTTPError as ex:
        return ex.code
    except Exception:
        return -1


def original_health():
    # Read-only checks; never POST against original enrolled 4B's OTA.
    def code(url):
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return -1
    guard(code("http://127.0.0.1:18003/xiaozhi/ota/") == 200, "original A03 OTA unhealthy")
    guard(code("http://127.0.0.1:18080/") == 403, "original A04 default deny unhealthy")


def resource_snapshot():
    stats = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        name, _, value = line.partition(":")
        if name in ("MemAvailable", "MemTotal", "SwapFree", "SwapTotal"):
            stats[name] = int(value.strip().split()[0])
    guard(stats["MemAvailable"] >= 1_400_000, "less than 1.34 GiB available; leave 4B untouched")
    return stats


def resource_post(before):
    after = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        if k in ("MemAvailable", "SwapFree", "SwapTotal"):
            after[k] = int(v.strip().split()[0])
    guard(after["MemAvailable"] >= 1_100_000, "available RAM below 1.05 GiB")
    old_swap = before["SwapTotal"] - before["SwapFree"]
    new_swap = after["SwapTotal"] - after["SwapFree"]
    guard(new_swap - old_swap <= 65536, "Swap rose >64 MiB during pilot")


def apply():
    require_root()
    guard(not OLD_CADDY.exists() and not OLD_ENV.exists() and not MARKER.exists(),
          "backup or active marker already exists; inspect rollback status")
    guard(running(ORIGINAL + NEW), "original or A09-Lite containers not running")
    assert_mount()
    old_ids = container_ids(ORIGINAL)
    old_health = resource_snapshot()
    original_health()
    a04 = CADDY.read_bytes()
    env = ENV.read_bytes()
    config = a04.decode("utf-8")
    variables = env_values(env.decode("utf-8"))
    secret = variables["IOS_SECRET"]
    candidate = extend_caddy(config, secret).encode()
    caddy_adapt(candidate.decode())
    # Backups must exist BEFORE changing either live config.
    private_create(OLD_CADDY, a04)
    private_create(OLD_ENV, env)
    switched_env = env.decode("utf-8").replace(
        "IOS_HOSTNAME=ios-voice.cncloudx.com", "IOS_HOSTNAME=" + HOST, 1).encode()
    try:
        # Change only the NEW adapter's OTA response URL; original 4B is not restarted.
        ENV.write_bytes(switched_env)
        compose("up", "-d", "--no-build", "--no-deps", "adapter")
        for _ in range(30):
            if running(NEW) and run("docker", "inspect", "-f",
                 "{{.State.Health.Status}}", "s3-voice-a09-lite-adapter") == "healthy":
                break
            time.sleep(1)
        guard(running(NEW) and run("docker", "inspect", "-f",
              "{{.State.Health.Status}}", "s3-voice-a09-lite-adapter") == "healthy",
              "A09 new adapter did not become healthy")
        same_inode_write(CADDY, candidate)
        caddy_reload()
        # A09 returns 400 for deliberately malformed JSON, while old A04
        # rejects it with 403. No real device or activation record is created.
        local = "http://127.0.0.1:18080/xiaozhi/ota/" + secret
        guard(probe(local) == 400, "local same-host OTA route did not reach A09")
        # The disposable CI has no production Cloudflare credentials or tunnel.
        simulator = (os.environ.get("GITHUB_ACTIONS") == "true"
                     and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
                     and os.environ.get("A09_SAME_HOST_SIMULATOR") == "1")
        if not simulator:
            guard(probe("https://" + HOST + "/xiaozhi/ota/" + secret) == 400,
                  "Cloudflare existing hostname did not reach A09")
        original_health()
        resource_post(old_health)
        guard(container_ids(ORIGINAL) == old_ids, "original 4B containers changed")
        private_create(MARKER, b"single-host-route-active\n")
        note("PILOT_PASS", "existing voice.cncloudx.com routes to A09, original 4B container IDs preserved")
        note("PHONE_PENDING", "Hi Xiaozhi on-device OTA/6-digit/voice not yet validated")
    except BaseException:
        try:
            same_inode_write(CADDY, a04)
            caddy_reload()
            ENV.write_bytes(env)
            compose("up", "-d", "--no-build", "--no-deps", "adapter")
            original_health()
            OLD_CADDY.unlink(missing_ok=True)
            OLD_ENV.unlink(missing_ok=True)
            note("ROLLED_BACK", "A04 original Caddy and A09 hostname restored")
        except BaseException:
            note("ROLLBACK_BLOCKED", "manual intervention required; do NOT restart original 4B")
        raise


def rollback():
    require_root()
    guard(OLD_CADDY.is_file() and OLD_ENV.is_file(), "private backup absent")
    # Do not clobber unexpected operator changes or replace any container.
    current = CADDY.read_text()
    guard(START in current and END in current, "current Caddy has unexpected changes")
    original = OLD_CADDY.read_bytes()
    old_env = OLD_ENV.read_bytes()
    guard(START not in original.decode(), "backup contains extension")
    caddy_adapt(original.decode())
    before = container_ids(ORIGINAL)
    same_inode_write(CADDY, original)
    caddy_reload()
    ENV.write_bytes(old_env)
    compose("up", "-d", "--no-build", "--no-deps", "adapter")
    original_health()
    guard(before == container_ids(ORIGINAL), "original containers changed during rollback")
    MARKER.unlink(missing_ok=True)
    OLD_CADDY.unlink()
    OLD_ENV.unlink()
    note("ROLLBACK_PASS", "original A04 Caddy and A09 hostname restored; no original service restart")


def status():
    require_root()
    current = CADDY.read_text()
    if MARKER.exists():
        guard(START in current and END in current, "marker exists but Caddy paths absent")
        original_health()
        guard(running(ORIGINAL + NEW), "expected container not running")
        note("STATUS", "same-host active and original 4B gateway healthy; iPhone not yet validated")
    else:
        note("STATUS", "same-host not yet active; original hostname is reserved for 4B")


def show_url():
    require_root()
    guard(MARKER.is_file(), "same-host routing not active")
    guard(sys.stdout.isatty(), "refuse to print private OTA credential outside interactive SSH")
    variables = env_values(ENV.read_text())
    guard(variables["IOS_HOSTNAME"] == HOST, "A09 still advertises another hostname")
    print("HI_XIAOZHI_OTA_URL=https://" + HOST + "/xiaozhi/ota/" + variables["IOS_SECRET"],
          flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["apply", "status", "rollback", "show-url"])
    args = parser.parse_args()
    try:
        {"apply": apply, "status": status, "rollback": rollback, "show-url": show_url}[args.command]()
    except (Stop, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        # Explicitly never print file contents, private path or signed token.
        note("BLOCKED", str(exc))
        sys.exit(1)
