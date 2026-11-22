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
        raise ValueError("base_url: malformed URL") from None
    if p.scheme != "https" or not p.hostname or p.username or p.password:
        raise ValueError("base_url: must start with https:// and include a valid host (copy only the URL)")
    if p.query or p.fragment or p.path.endswith("/chat/completions"):
        raise ValueError("base_url: remove query/fragment or /chat/completions; use the API base URL")
    if p.hostname.lower() == "localhost" or p.hostname.lower().endswith(".local"):
        raise ValueError("base_url: localhost/local network host is unsupported")
    try:
        addr = ipaddress.ip_address(p.hostname)
    except ValueError:
        pass
    else:
        if not addr.is_global:
            raise ValueError("base_url: private or reserved IP is unsupported")
    try:
        port = p.port
    except ValueError:
        raise ValueError("base_url: invalid port") from None
    if port is not None and port != 443:
        raise ValueError("base_url: only HTTPS port 443 is supported")
    if len(base_url) > 400 or any(ord(c) < 33 for c in base_url):
        raise ValueError("base_url: invalid length, whitespace, or quotation marks; paste the value only")
    if not re.fullmatch(r"[A-Za-z0-9._:/@+-]{1,128}", model):
        raise ValueError("model_name: copy one models object key (model ID), not a display name, quotes or JSON object")
    if not (8 <= len(key) <= 2048) or any(ord(c) < 33 for c in key):
        raise ValueError("api_key: must be 8–2048 printable characters with no spaces or line breaks; paste the raw key without JSON quotes")


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
    except ValueError as exc:
        # Credentials validation errors are all fixed, pre-authored diagnostics.
        # Never echo or interpolate the user-provided URL, model ID or API key.
        reason = str(exc)
        if args.mode == "credentials" and reason.startswith(("base_url:", "model_name:", "api_key:")):
            raise SystemExit("A05_INPUT_ERROR: " + reason + "; no input values printed") from None
        raise SystemExit("A05_BLOCKED: configuration baseline or input format invalid; no keys printed") from None
    except (KeyError, OSError):
        raise SystemExit("A05_BLOCKED: input/config validation failed; no keys printed") from None
