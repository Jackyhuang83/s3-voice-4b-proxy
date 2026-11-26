#!/usr/bin/env python3
"""P1 pilot gate carried within P2-1: isolated WebUI only, no A03/A04 edits.

modes:
  plan                        read-only; does not download or write
  stage --hostname FQDN --approve-isolated-stage
                              explicitly authorized, reversible NEW-only containers
  verify                      read-only; does not log any private identities
  rollback                    stop/remove only NEW WebUI sidecars, keep files

Run as a Python *script*, NEVER source in a login shell. This module cannot
execute an SSH exit command or mutate a legacy Docker Compose project.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = pathlib.Path("/opt/s3-voice-webui")
PROJECT = "s3-voice-webui"
SERVICES = ("auth", "gateway")
NAMES = ("s3-voice-webui-auth", "s3-voice-webui-gateway")
ORIGINAL = ("s3-voice-ai-server", "s3-voice-ai-gateway", "s3-voice-ai-tunnel")
COMPOSE_SOURCE = ROOT / "deploy/ai/webui/docker-compose.isolated.example.yml"
PRIVATE_FILES = ("auth.env", "gateway.env", "models.json")
SOURCE_FILES = (
    "tools/ai/webui_pilot.py",
    "tools/ai/webui_preflight.py",
    "tools/ai/webui_auth.py",
    "tools/ai/webui_text.py",
    "tools/ai/webui-vendor-opus.sh",
    "deploy/ai/webui/docker-compose.isolated.example.yml",
    "deploy/ai/webui/Caddyfile.isolated",
    "webui/index.html",
    "webui/app.css",
    "webui/app.js",
    "webui/audio-ui.mjs",
    "webui/audio-opus.mjs",
    "webui/audio-worklet.js",
)
IMAGE_TAGS = {"WEBUI_PYTHON_IMAGE": "python:3.13-alpine",
              "WEBUI_CADDY_IMAGE": "caddy:2.11.7-alpine"}
MAX_SWAP_DELTA_KIB = 64 * 1024


class PilotBlocked(RuntimeError):
    """Safe failure without printing command environment or Docker secrets."""


def run(args, *, env=None, input_text=None, check=True):
    p = subprocess.run(args, env=env, input=input_text, text=True,
                       capture_output=True, check=False, timeout=120)
    if check and p.returncode:
        # Deliberately hide stdout/stderr, which may contain ENV/secret paths.
        raise PilotBlocked("ISOLATED_COMMAND_FAILED")
    return p


def require_root():
    if os.geteuid() != 0:
        raise PilotBlocked("ROOT_REQUIRED_FOR_STAGE_VERIFY_ROLLBACK")


def validate_hostname(host):
    if not isinstance(host, str) or not re.fullmatch(
        r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cncloudx\.com", host
    ):
        raise PilotBlocked("WEBUI_HOSTNAME_MUST_BE_UNIQUE_CNCloudX_SUBDOMAIN")
    if host in ("voice.cncloudx.com", "tv.cncloudx.com"):
        raise PilotBlocked("EXISTING_HOSTNAME_RESERVED")
    return host


def preflight():
    p = ROOT / "tools/ai/webui_preflight.py"
    spec = importlib.util.spec_from_file_location("s3_readonly_preflight", p)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.evaluate(module.gather())
    if not result["ok"]:
        raise PilotBlocked("HOST_BASELINE_FAILED_" + ",".join(result["failures"]))
    return result


def docker_state(name):
    result = run(["docker", "inspect", "--format", "{{json .}}", name], check=False)
    if result.returncode or not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError):
        return None


def current_ids():
    result = {}
    for name in ORIGINAL:
        item = docker_state(name)
        if item and (item.get("State") or {}).get("Running"):
            result[name] = item["Id"]
    if "s3-voice-ai-server" not in result or "s3-voice-ai-gateway" not in result:
        raise PilotBlocked("A03_A04_NOT_RUNNING")
    return result


def current_mem():
    result = {}
    for line in pathlib.Path("/proc/meminfo").read_text().splitlines():
        if line.startswith(("MemAvailable:", "SwapTotal:", "SwapFree:")):
            key, payload = line.split(":", 1)
            result[key] = int(payload.split()[0])
    return result


def resolve_image(tag):
    run(["docker", "pull", tag])
    p = run(["docker", "image", "inspect", "--format", "{{json .RepoDigests}}", tag])
    try:
        digests = json.loads(p.stdout)
    except ValueError:
        raise PilotBlocked("IMAGE_DIGEST_UNAVAILABLE")
    name = tag.split(":", 1)[0]
    allowed_names = {name, "docker.io/library/" + name, "index.docker.io/library/" + name}
    found = [
        x for x in digests
        if x.split("@sha256:", 1)[0] in allowed_names and
        re.fullmatch(r"[0-9a-f]{64}", x.partition("@sha256:")[2])
    ]
    if not found:
        raise PilotBlocked("IMAGE_DIGEST_UNAVAILABLE")
    return found[0]


def safe_write(path, value, mode=0o600):
    if path.exists() or path.is_symlink():
        raise PilotBlocked("TARGET_ALREADY_EXISTS")
    # "x" avoids overwriting an existing file or following a symlink.
    with open(path, "x", encoding="utf-8") as fd:
        os.fchmod(fd.fileno(), mode)
        fd.write(value)
        fd.flush()


def generate_private(host, private):
    owner = secrets.token_hex(32)
    gate = secrets.token_hex(32)
    random_mac = "02:" + ":".join(f"{x:02x}" for x in secrets.token_bytes(5))
    client = str(uuid.uuid4())
    auth = (
        f"S3_WEBUI_ORIGIN=https://{host}\n"
        f"S3_WEBUI_OWNER_SECRET={owner}\n"
        f"S3_WEBUI_GATE_SECRET={gate}\n"
        f"S3_WEBUI_DEVICE_ID={random_mac}\n"
        f"S3_WEBUI_CLIENT_ID={client}\n"
    )
    safe_write(private / "auth.env", auth)
    safe_write(private / "gateway.env", f"S3_WEBUI_GATE_SECRET={gate}\n")
    safe_write(private / "models.json", "[]\n")
    # Credentials are NEVER echoed, even to CI logs.
    return True


def copy_source(root, target):
    target.mkdir(mode=0o755)
    for item in SOURCE_FILES:
        src = root / item
        if not src.is_file() or src.is_symlink():
            raise PilotBlocked("SOURCE_FILE_MISSING_OR_SYMLINK")
        dest = target / item
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
        shutil.copyfile(src, dest)
        dest.chmod(0o644)
    # Source inventory immutable after Docker start. Installer dependencies
    # cannot be fetched/updated by the sidecar itself.
    vendor = target / "tools/ai/webui-vendor-opus.sh"
    run(["bash", str(vendor)])
    for item in (
        "webui/vendor/libopus/dist/index.js",
        "webui/vendor/libopus/dist/generated/libopus.generated.mjs",
        "webui/vendor/libopus/LICENSE",
        "webui/vendor/libopus/THIRD_PARTY_NOTICES.md",
    ):
        if not (target / item).is_file():
            raise PilotBlocked("SIGNED_CODEC_INSTALL_INCOMPLETE")


def compose_args(base, *args):
    return ["docker", "compose", "-p", PROJECT,
            "-f", str(base / "docker-compose.yml"),
            "--env-file", str(base / ".env"), *args]


def owner_probe():
    # Executes INSIDE the new auth container on the private A03 network, so
    # no new host port or Cloudflare published route is required for local tests.
    code = r"""
import json, os, urllib.error, urllib.request
url = "http://s3-voice-webui-gateway:8080"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
def fetch(path, method="GET", payload=None, headers=None):
    req=urllib.request.Request(url+path, data=payload, method=method, headers=headers or {})
    try:
        with opener.open(req,timeout=5) as res:
            return res.status,res.headers, res.read(6000)
    except urllib.error.HTTPError as error:
        return error.code,error.headers,error.read(6000)
assert fetch("/webui/api/session")[0] == 200
assert json.loads(fetch("/webui/api/session")[2]) == {"authenticated":False}
assert fetch("/webui/")[0] == 200
assert fetch("/webui/api/models")[0] == 401
assert fetch("/")[0] == 403
assert fetch("/xiaozhi/ota/no-public-path")[0] == 403
h={"Origin":os.environ["S3_WEBUI_ORIGIN"],"Content-Type":"application/json"}
bad=fetch("/webui/api/login","POST",b'{"secret":"invalid"}',h)
assert bad[0] == 401
secret=os.environ["S3_WEBUI_OWNER_SECRET"]
body=json.dumps({"secret":secret}).encode()
code,headers,_=fetch("/webui/api/login","POST",body,h)
assert code==200
cookie=headers.get("Set-Cookie","").split(";",1)[0]
code,_,models=fetch("/webui/api/models",headers={"Cookie":cookie})
assert code==200 and json.loads(models)=={"models":[]}
print("WEBUI_PILOT_PRIVATE_HTTP_PASS: login, 401, 403, static files; zero paid model calls")
"""
    run(["docker", "exec", "-i", NAMES[0], "python3", "-B", "-c", code])


def private_network_check():
    auth = docker_state(NAMES[0])
    gateway = docker_state(NAMES[1])
    if not auth or not gateway:
        raise PilotBlocked("NEW_CONTAINERS_NOT_FOUND")
    expected = (
        {"s3-voice-ai_default"},
        {"s3-voice-ai_default", "s3-voice-ai-edge_front"},
    )
    for item, nets in ((auth, expected[0]), (gateway, expected[1])):
        if not item["State"]["Running"]:
            raise PilotBlocked("NEW_CONTAINER_UNHEALTHY")
        has = set((item.get("NetworkSettings") or {}).get("Networks") or ())
        if has != nets:
            raise PilotBlocked("NEW_CONTAINER_NETWORK_MISMATCH")
        if (item.get("HostConfig") or {}).get("PortBindings"):
            raise PilotBlocked("UNEXPECTED_PUBLISHED_HOST_PORTS")


def verify(base=BASE):
    require_root()
    state_path = base / "state.json"
    if not state_path.is_file():
        raise PilotBlocked("NO_STAGED_PILOT_MARKER")
    state = json.loads(state_path.read_text())
    if state.get("project") != PROJECT or state.get("base") != str(base):
        raise PilotBlocked("UNTRUSTED_PILOT_MARKER")
    private_network_check()
    old = current_ids()
    if any(old.get(n) != ident for n, ident in state["original_ids"].items()):
        raise PilotBlocked("ORIGINAL_A03_A04_TUNNEL_CHANGED")
    before = state["mem"]
    after = current_mem()
    swap_before = before["SwapTotal"] - before["SwapFree"]
    swap_after = after["SwapTotal"] - after["SwapFree"]
    if swap_after - swap_before > MAX_SWAP_DELTA_KIB:
        raise PilotBlocked("SWAP_DELTA_OVER_64MIB")
    if after["MemAvailable"] < 1101005:
        raise PilotBlocked("MEM_AVAILABLE_BELOW_1_05GIB")
    # Docker reports Started before Caddy has bound to 8080.
    # Retry ONLY local new-sidecar probes; do not touch an old A04 listener.
    for attempt in range(12):
        try:
            owner_probe()
            break
        except PilotBlocked:
            if attempt == 11:
                raise PilotBlocked("NEW_WEBUI_GATEWAY_NOT_READY")
            time.sleep(0.75)
    # Same baseline tests, including A03 OTA and old A04 default deny.
    preflight()
    print("WEBUI_PILOT_VERIFY_PASS: new-sidecar-only, old A03/A04 container IDs unchanged")
    print("WEBUI_PILOT_NOT_PUBLISHED: Cloudflare, real API models and Safari NOT verified")


def stage(hostname, approved, *, base=BASE, root=ROOT):
    require_root()
    host = validate_hostname(hostname)
    if not approved:
        raise PilotBlocked("EXPLICIT_STAGE_APPROVAL_REQUIRED")
    if base.exists() or base.is_symlink():
        raise PilotBlocked("PILOT_DIRECTORY_ALREADY_PRESENT")
    for name in NAMES:
        if docker_state(name):
            raise PilotBlocked("PILOT_CONTAINER_NAME_ALREADY_EXISTS")
    preflight()
    original_ids = current_ids()
    mem = current_mem()
    # Stage impacts only this new absolute directory and the new Docker project.
    os.umask(0o022)
    base.mkdir(mode=0o755)
    private = base / "private"
    private.mkdir(mode=0o700)
    try:
        copy_source(root, base / "src")
        generate_private(host, private)
        with open(base / "docker-compose.yml", "x", encoding="utf-8") as f:
            f.write(COMPOSE_SOURCE.read_text())
        (base / "docker-compose.yml").chmod(0o644)
        locked = {k: resolve_image(v) for k, v in IMAGE_TAGS.items()}
        safe_write(base / ".env", "".join(k + "=" + v + "\n" for k,v in locked.items()))
        safe_write(base / "state.json", json.dumps({
            "project": PROJECT, "base": str(base), "hostname": host,
            "original_ids": original_ids, "mem": mem, "status": "PREPARED"
        }))
        run(compose_args(base,"config","-q"))
        run(compose_args(base,"up","-d","--no-deps",*SERVICES))
        verify(base)
        print("WEBUI_PILOT_STAGE_PASS: two NEW sidecars; no existing A03/A04 restart")
    except Exception as e:
        # This project did not exist before stage; rollback never touches
        # original A03/A04, cloudflared or any other Docker project.
        if (base / "docker-compose.yml").is_file() and (base / ".env").is_file():
            run(compose_args(base, "down"), check=False)
        print("WEBUI_PILOT_AUTO_ROLLBACK: stopped only new WebUI project")
        if isinstance(e, PilotBlocked):
            raise
        raise PilotBlocked("PILOT_STAGE_FAILED_NO_LEGACY_CHANGES") from None


def rollback(base=BASE):
    require_root()
    state = base / "state.json"
    if not state.is_file():
        raise PilotBlocked("NO_STAGED_PILOT_MARKER")
    data = json.loads(state.read_text())
    if data.get("project") != PROJECT or data.get("base") != str(base):
        raise PilotBlocked("UNTRUSTED_PILOT_MARKER")
    run(compose_args(base, "down"))
    print("WEBUI_PILOT_ROLLBACK_PASS: removed only two WebUI sidecars; private files retained")
    print("WEBUI_PILOT_CLOUDFLARE_UNCHANGED: separately remove any future added hostname route")


def main(argv=None):
    parser = argparse.ArgumentParser(description="S3 Voice isolated WebUI pilot, no SSH exit")
    parser.add_argument("action", choices=("plan","stage","verify","rollback"))
    parser.add_argument("--hostname")
    parser.add_argument("--approve-isolated-stage", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            # The user already supplied an actual PASS; this is automatic
            # revalidation for staging, not a request for more manual tests.
            result = preflight()
            if BASE.exists() or any(docker_state(name) for name in NAMES):
                raise PilotBlocked("PILOT_ALREADY_EXISTS_OR_CONFLICT")
            print("WEBUI_PILOT_PLAN_PASS: no installation, old voice stack untouched")
            print("WEBUI_PILOT_MODEL_CATALOG_EMPTY: no paid API calls during local stage")
            return 0
        if args.action == "stage":
            stage(args.hostname, args.approve_isolated_stage)
        elif args.action == "verify":
            verify()
        else:
            rollback()
        return 0
    except PilotBlocked as error:
        print("WEBUI_PILOT_BLOCKED: " + str(error))
        return 1
    except (OSError, ValueError, subprocess.TimeoutExpired):
        print("WEBUI_PILOT_BLOCKED: LOCAL_IO_OR_DOCKER_ERROR")
        return 1


if __name__ == "__main__":
    sys.exit(main())
