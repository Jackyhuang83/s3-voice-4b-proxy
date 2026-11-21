#!/usr/bin/env python3
"""P2-3 exit policy: source checks are supplemental, never server proof."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
link = (root / "components/s3_ss2022/s3_ss2022_link.c").read_text()
wire = (root / "components/s3_ss2022/muse_ss2022.c").read_text()
workflow = (root / ".github/workflows/p2-ss2022-official.yml").read_text()
docs = (root / "docs/P2-SS2022-EXIT.md").read_text()

# Rust server premature close must not count as successful authenticated stream.
assert link.count("ok = s.rx->phase == 2 && !s.rx->failed;") == 2
assert "if (!ss2022_feed" in link or "|| !ss2022_feed(" in link
assert "ss2022_rx_free" in link and "ss2022_cipher_free" in link
assert "s3_ss2022_node_valid(node)" in link
assert "MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT" in link
assert "s3_ss2022_node_clear" in link
assert "ss2022_request" in link and "ss2022_payload" in link

# Do not replace rlog's pinned production cryptography for interoperability.
assert "shadowsocks 2022 session subkey" in wire
assert "psa_aead_decrypt" in wire and "psa_aead_encrypt" in wire

assert "ghcr.io/shadowsocks/ssserver-rust:v1.25.0@sha256:" in workflow
assert '--network host' in workflow
assert '"server": "127.0.0.1"' in workflow
assert '"mode": "tcp_only"' in workflow
assert "badkey" in workflow and "bad-dns" in workflow
assert "replay" in workflow and "stale" in workflow
assert "offline" in workflow
assert "unencrypted" in docs.lower() or "未加密" in docs
assert "4B" in docs and "NOT RUN" in docs
print("PASS P2-3 strict source guards, server pin, loopback scope, and release exclusions")
