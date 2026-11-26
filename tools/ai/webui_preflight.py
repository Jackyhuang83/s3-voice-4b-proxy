#!/usr/bin/env python3
"""S3-Voice P1-3: strictly READ-ONLY Debian host readiness probe.

No SSH, no Docker writes, no file writes, no firmware/Cloudflare modifications.
Run on the existing VPS with read access to A03/A04 paths and Docker metadata.
Never prints device identity, shared secrets, passwords or API keys.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

A03 = pathlib.Path("/opt/s3-voice-ai")
A04 = pathlib.Path("/opt/s3-voice-ai-edge")
MIN_AVAILABLE_KIB = 1101005  # 1.05 GiB
MIN_DISK_BYTES = 1 * 1024 ** 3
REQUIRED_CONTAINERS = ("s3-voice-ai-server", "s3-voice-ai-gateway")
A03_NETWORK = "s3-voice-ai_default"


def proc_meminfo(source):
    result = {}
    for line in source.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            parts = value.strip().split()
            if parts and parts[0].isdigit():
                result[key] = int(parts[0])
    return result


def docker_inspect(name):
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{json .}}", name],
            capture_output=True, text=True, check=False, timeout=8
        )
        if result.returncode or not result.stdout.strip():
            return None
        # Metadata deliberately not logged; may contain environment secrets.
        return json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return None


def http_probe(path):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(path, timeout=4) as response:
            response.read(256)
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (OSError, ValueError, urllib.error.URLError):
        return 0


def safe_file(path, mode=0o077):
    try:
        info = path.stat()
        return path.is_file() and not (info.st_mode & mode)
    except OSError:
        return False


def config_evidence(path):
    try:
        if not path.is_file():
            return None
        data = path.read_bytes()
        if len(data) > 4 * 1024 * 1024:
            return None
        # Compute fingerprint only. Never print config or private URL.
        return hashlib.sha256(data).hexdigest()[:12], data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def selected_info(container):
    if not isinstance(container, dict):
        return None
    state = container.get("State") or {}
    networks = (container.get("NetworkSettings") or {}).get("Networks") or {}
    binds = (container.get("HostConfig") or {}).get("PortBindings") or {}
    image = ((container.get("Config") or {}).get("Image") or "")
    return {
        "running": state.get("Running") is True,
        "networks": list(networks),
        "port_bindings": binds,
        "image_is_digest": "@sha256:" in image,
    }


def bound_loopback(inspected, container_port, host_port):
    if not inspected:
        return False
    bindings = inspected["port_bindings"].get(container_port + "/tcp", [])
    return any(
        entry.get("HostIp") == "127.0.0.1" and
        str(entry.get("HostPort")) == str(host_port)
        for entry in bindings
    )


def evaluate(info):
    """Pure checker. A failing critical gate means STOP, not an auto-fix."""
    failures = []
    def need(ok, label):
        if not ok:
            failures.append(label)
    memory = info.get("mem", {})
    available = memory.get("MemAvailable", 0)
    swap_total = memory.get("SwapTotal", 0)
    swap_free = memory.get("SwapFree", 0)
    need(available >= MIN_AVAILABLE_KIB, "RAM_AVAILABLE_BELOW_1_05GIB")
    need(info.get("disk_free_bytes", 0) >= MIN_DISK_BYTES, "DISK_FREE_BELOW_1GIB")
    need(info.get("a03_lock", False), "A03_IMAGE_LOCK_MISSING")
    need(info.get("a03_private_config", False), "A03_PRIVATE_CONFIG_UNSAFE")
    need(info.get("a04_identity_private", False), "A04_IDENTITY_UNSAFE")
    need(info.get("a04_env_private", False), "A04_ENV_UNSAFE")
    need(info.get("a04_log_discard", False), "A04_PATH_LOGGING_NOT_PROVEN_DISABLED")
    need(info.get("a04_reject_default", False), "A04_DEFAULT_DENY_NOT_PROVEN")
    need(info.get("a03_health_code") == 200, "A03_OTA_HEALTH_NOT_200")
    need(info.get("a04_health_code") == 403, "A04_DEFAULT_DENY_NOT_403")
    a03 = selected_info(info.get("a03"))
    a04 = selected_info(info.get("a04"))
    need(bool(a03 and a03["running"]), "A03_CONTAINER_UNHEALTHY")
    need(bool(a04 and a04["running"]), "A04_GATEWAY_UNHEALTHY")
    need(bool(a03 and a03["image_is_digest"]), "A03_IMAGE_NOT_DIGEST_PINNED")
    need(bool(a04 and a04["image_is_digest"]), "A04_CADDY_NOT_DIGEST_PINNED")
    need(bool(a03 and A03_NETWORK in a03["networks"]), "A03_NETWORK_MISMATCH")
    need(bool(a04 and A03_NETWORK in a04["networks"]), "A04_BACKEND_NETWORK_MISMATCH")
    front = [n for n in (a04 or {}).get("networks", []) if n != A03_NETWORK]
    need(len(front) == 1, "A04_FRONT_BRIDGE_NOT_UNIQUE")
    need(bound_loopback(a03, "8000", "18000"), "A03_WS_NOT_LOOPBACK_ONLY")
    need(bound_loopback(a03, "8003", "18003"), "A03_OTA_NOT_LOOPBACK_ONLY")
    need(bound_loopback(a04, "8080", "18080"), "A04_GATE_NOT_LOOPBACK_ONLY")
    need(info.get("manager_active") is False, "A09_MANAGER_RESOURCE_ISOLATION_UNKNOWN")
    # No production secrets should be emitted, not even if inspection fails.
    return {
        "ok": not failures,
        "failures": failures,
        "facts": {
            "available_mib": available // 1024,
            "swap_used_mib": max(0, swap_total - swap_free) // 1024,
            "disk_free_gib": info.get("disk_free_bytes", 0) // (1024 ** 3),
            "a03_a04_network_shared": bool(a03 and a04 and A03_NETWORK in a03["networks"] and A03_NETWORK in a04["networks"]),
            "a04_front_network_count": len(front),
            "a04_config_fingerprint": info.get("a04_fingerprint", "unavailable"),
        }
    }


def gather():
    try:
        mem = proc_meminfo(pathlib.Path("/proc/meminfo").read_text())
    except OSError:
        mem = {}
    try:
        disk = os.statvfs("/opt")
        free_bytes = disk.f_bavail * disk.f_frsize
    except OSError:
        free_bytes = 0
    config = config_evidence(A04 / "Caddyfile")
    caddy_data = config[1] if config else ""
    # Only check for route shape; do not disclose secret path components.
    return {
        "mem": mem,
        "disk_free_bytes": free_bytes,
        "a03_lock": safe_file(A03 / ".env"),
        "a03_private_config": safe_file(A03 / "data/.config.yaml"),
        "a04_identity_private": safe_file(A04 / "identity.json"),
        "a04_env_private": safe_file(A04 / ".env"),
        "a04_log_discard": "output discard" in caddy_data and "\n  log {" in caddy_data,
        "a04_reject_default": 'respond "Forbidden" 403' in caddy_data,
        "a03_health_code": http_probe("http://127.0.0.1:18003/xiaozhi/ota/"),
        "a04_health_code": http_probe("http://127.0.0.1:18080/"),
        "a03": docker_inspect(REQUIRED_CONTAINERS[0]),
        "a04": docker_inspect(REQUIRED_CONTAINERS[1]),
        "a04_fingerprint": config[0] if config else "unavailable",
        "manager_active": all(
            not (docker_inspect(name) or {}).get("State", {}).get("Running", False)
            for name in ("xiaozhi-esp32-server-manager", "s3-voice-ai-manager")
        )
    }


def main():
    if len(sys.argv) != 1:
        print("Usage: python3 tools/ai/webui_preflight.py", file=sys.stderr)
        return 2
    result = evaluate(gather())
    facts = result["facts"]
    print(
        "WEBUI_P1_FACTS: available_mib={available_mib} swap_used_mib={swap_used_mib} "
        "disk_free_gib={disk_free_gib} shared_a03_net={a03_a04_network_shared} "
        "front_network_count={a04_front_network_count} a04_sha12={a04_config_fingerprint}".format(**facts)
    )
    if result["ok"]:
        print("WEBUI_P1_PREFLIGHT_PASS: READ_ONLY only; NO production deployment, no iPhone/4B acceptance")
        print("WEBUI_P1_NEXT_GATES: Caddy route merge/backup + pilot swap delta + Cloudflare + Safari + 4B")
        return 0
    print("WEBUI_P1_PREFLIGHT_BLOCKED: " + ",".join(result["failures"]))
    print("WEBUI_P1_NO_CHANGES: protect existing A03/A04 and 4B")
    return 1


if __name__ == "__main__":
    sys.exit(main())
