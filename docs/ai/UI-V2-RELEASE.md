# S3-Voice UI v2 — P2-2 verification, release and rollback

Baseline: existing deployed WebUI stable and Safari-accessible, with Caddy callback query fix in PR #39. **This document authorizes NO production actions.**

## Code and independent verification

- UI only: `webui/index.html`, `webui/app.css`, `webui/app.js`.
- Added tests: `test_webui_v2.py` uses stdlib HTML parser to validate DOM IDs, scripts, CSP, mobile CSS and no third-party URLs. `test_webui_v2.mjs` uses an entirely mocked DOM, session/model and SSE stream to exercise reply copying, Enter mobile behavior, and current-tab reset.
- New GitHub workflow `ai-webui-v2.yml`: allowlist-only PR scope, Node syntax, isolated UI tests, inherited auth/text and voice-browser tests; no VPS network, secrets, Caddy restart or image build.
- Existing WebUI P0/P1/P2 CI workflow gates remain independently authoritative. A passing static test does **not** equal Safari UX or real 4B voice acceptance.
- Design draws on Open WebUI patterns without importing its licensed source or logos.

## Gated rollout — **not performed**

1. Review all six stacked UI PRs: #40 P0-1, #41 P0-2, #42 P1-1, #43 P1-2, #44 P2-1, #45 P2-2. Their bases descend from established #39. Do not merge #39 while stacked branch bases are uncoordinated; update/rebase carefully.
2. Require green UI v2 plus all relevant original WebUI workflows, code review and approved screenshot comparison at 375/430/768/1280 widths. Test iPhone Safari keyboard and focus, model list, text SSE, copy reply, mic start/stop, logout, owner-only redirects. No automatic merge.
3. User must explicitly approve a **separate, reversible UI-only pilot**. Before any deployment, take byte-exact backups and SHA256 of `webui/index.html`, `webui/app.css`, `webui/app.js`. Confirm VPS files correspond to a reviewed known baseline; avoid overwriting VPS customizations. The existing `/opt/s3-voice-webui/src` bind mount must be assessed before any file replacement. Never touch Caddyfile, Auth, A03/A04, Cloudflare Access, Opus or 4B.
4. Deploy only these three UI files if allowed by the existing static whitelist. Keep all existing IDs and endpoint paths; no new container or image. Use isolated preview before switching live source.
5. In owner-approved Safari test, confirm Cloudflare login `/webui/`, model catalog, a text response, copy response, new chat, voice mic + stop, and readable status. Record real test evidence separately; do not infer a voice PASS from UI tests.
6. On any failure, restore the three exact file backups, confirm original hashes, check baseline text/audio and leave original stable version available. No silent retries or forced downtime.

## UI acceptance status

- P0 audit + design: docs submitted, pending independent review.
- P1 HTML/CSS/JS: source submitted, no production rollout.
- P2 accessibility + CI: source submitted, GitHub checks pending.
- Safari visual/accessibility and new UI voice test: **not verified**.
- Program completion / release: **not yet accepted**.

Weights: P0-1 8%, P0-2 12%, P1-1 25%, P1-2 20%, P2-1 20%, P2-2 15%. **Do not credit a PR's weight until its gate passes**. Total 100%.
