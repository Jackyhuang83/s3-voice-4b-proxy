#!/usr/bin/env python3
"""A05 private configuration helper; stdlib only; never print API secrets."""
import argparse
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit


def require_endpoint(base_url, model, key):
    try:
        p = urlsplit(base_url)
    except ValueError:
        raise ValueError("invalid URL") from None
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("provider base_url must use HTTPS and have a valid hostname")
    if p.query or p.fragment or p.path.endswith("/chat/completions"):
        raise ValueError("use the API base URL, not the final completion endpoint")
    if p.hostname.lower() == "localhost" or p.hostname.lower().endswith(".local"):
        raise ValueError("local/insecure provider hosts are unsupported")
    try:
        addr = ipaddress.ip_address(p.hostname)
    except ValueError:
        pass
    else:
        if not addr.is_global:
            raise ValueError("private or reserved provider address refused")
    try:
        port = p.port
    except ValueError:
        raise ValueError("invalid port") from None
    if port is not None and port != 443:
        raise ValueError("only HTTPS default port 443 supported")
    if len(base_url) > 400 or any(ord(c) < 33 for c in base_url):
        raise ValueError("invalid base URL characters")
    if not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,128}", model):
        raise ValueError("unsupported model identifier")
    if not (8 <= len(key) <= 2048) or any(ord(c) < 33 for c in key):
        raise ValueError("invalid API key")


def create_credential_file(dest, base_url, model):
    key = sys.stdin.read()
    require_endpoint(base_url, model, key)
    out = Path(dest)
    fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fp:
        json.dump({"base_url": base_url.rstrip("/"),
                   "model_name": model, "api_key": key}, fp)
    print("A05_OK: private provider parameters validated (HTTPS, model, nonempty API key)")


def apply(path, credentials):
    p = Path(path)
    obj = json.loads(Path(credentials).read_text())
    require_endpoint(obj["base_url"], obj["model_name"], obj["api_key"])
    original = p.read_text()
    selected = "  LLM: DeepSeekLLM"
    block = ("LLM:\n  DeepSeekLLM:\n"
             "    api_key: PENDING_A05_NOT_A_REAL_KEY")
    if original.count(selected) != 1 or original.count(block) != 1:
        raise ValueError("A03/A04 LLM baseline differs; refuse to overwrite")
    if "GenericGPTLLM" in original:
        raise ValueError("GenericGPTLLM already configured")
    fmt = json.dumps
    appended = (
        block + "\n"
        "  GenericGPTLLM:\n"
        "    type: openai\n"
        "    base_url: " + fmt(obj["base_url"]) + "\n"
        "    model_name: " + fmt(obj["model_name"]) + "\n"
        "    api_key: " + fmt(obj["api_key"]) + "\n"
        "    max_tokens: 256\n"
        "    timeout: 30"
    )
    updated = original.replace(selected, "  LLM: GenericGPTLLM", 1)
    updated = updated.replace(block, appended, 1)
    assert updated != original
    temp = p.with_name(".config.yaml.a05tmp")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as fp:
        fp.write(updated)
    os.replace(temp, p)
    os.chmod(p, 0o600)
    print("A05_OK: official GenericGPTLLM selected (type=openai); A04 HTTPS/WSS settings retained")


def audit(path):
    data = Path(path).read_text()
    active = "  LLM: GenericGPTLLM" in data
    if active:
        assert data.count("  GenericGPTLLM:\n") == 1
        assert "    type: openai\n" in data
    print("A05_STATUS: compatible provider configured=" + ("yes" if active else "no"))
    print("A05_STATUS: API key value not displayed")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="mode", required=True)
    cred = sub.add_parser("credentials")
    cred.add_argument("--output", required=True)
    cred.add_argument("--base-url", required=True)
    cred.add_argument("--model", required=True)
    apl = sub.add_parser("apply")
    apl.add_argument("--config", required=True)
    apl.add_argument("--credentials", required=True)
    status = sub.add_parser("audit")
    status.add_argument("--config", required=True)
    args = p.parse_args()
    try:
        if args.mode == "credentials":
            create_credential_file(args.output, args.base_url, args.model)
        elif args.mode == "apply":
            apply(args.config, args.credentials)
        else:
            audit(args.config)
    except (ValueError, KeyError, OSError) as exc:
        # Error cause may contain user strings only if emitted by Python; avoid them.
        raise SystemExit("A05_BLOCKED: input/config validation failed; no keys printed") from None
