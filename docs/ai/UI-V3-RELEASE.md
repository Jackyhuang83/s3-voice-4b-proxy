# S3-Voice UI v3 — separate immutable release and rollback gate

## Scope and compatibility
UI v3 is an optional collapsed native dialog navigation overlay for all viewport widths. Tapping the visible 44px hamburger toggles the sidebar, clicking in-panel close or the outside backdrop / Esc closes it. On hardware keyboards K toggles only when focus is outside editable controls. The native modal uses the browser focus trap/return behavior; login, models, SSE request payload, XiaoZhi WS, and Opus files are unmodified.

Only `webui/index.html`, `webui/app.css` and `webui/app.js` may change on a VPS, after separate owner approval. Existing v2 production remains live until then.

## Immutable safety
- New standalone `tools/ai/webui_v3_publish.py`; v2 `tools/ai/webui_v2_publish.py` stays byte-identical.
- Source commit pin `35a3cf5464b495d5d941c8bf53a6d2e4188b34b4`; three immutable Git blob IDs independently verified on GitHub:
  - index.html: `d275e1192f59a65c15605f5c1cb266b2287f2158`
  - app.css: `54fe60556917a5f87f729dfe0270a39bf510e803`
  - app.js: `e2907dae0492cbfd6fa53346cb35c2aa2393163d`
- Publisher does read-only production preflight, verifies owner Gateway/Auth & A03/A04 container IDs and current HTTP routes, makes owner-only exact-byte backup (separate `webui-v3-*` backup namespace), publishes only those three frontend assets, verifies exact HTTP bytes, protected hashes, root and callback, auth and WS denial. On failure restores original bytes with no Docker restart. It can also be run repeatedly without replacing identical files.
- Existing v2 publisher must be tested with v2 frozen fixture, not v3 app assets; P2 CI validates v3 publisher separately.
- Never merge unrelated PR #39 or modify Cloudflare, Caddy, Auth, 4B firmware, language models, backend, routes, or vendor Opus. No new external JS/CSS dependencies.

## CI acceptance
- Python DOM/CSP and source-scope gates; JS syntax and mocked owner session/SSE/copy/reset;
- Headless real Chrome on 375, 430, 768, 1280px plus dark/light screenshot, collapsed/open states, mobile overflow, K / Esc / close / outside click, keyboard text entry, first and second SSE reply;
- V3 publisher mock success, no-op, forced failure rollback, blob OID validation.
- Original P1 private model/text / Caddy/Opus safety tests remain authoritative.
- **Do not claim actual iPhone Safari login / touch microphone / 4B voice acceptance from CI.**

## Release decision (NOT executed)
After all relevant UI v3 CI is green and code reviewed, owner can separately authorize a single vetted command to run new pinned publisher on existing VPS. Store stable v2 backup and SHA manifest. If deployment or Safari regressions, use rollback on the exact saved bytes, never change Cloudflare Access policies to debug UI. The UI project remains incomplete until owner Safari visual and real microphone checks pass; if not approved, leave v2 untouched.

## GDGS progress
P0 10/10 after source audit. P1 0/60 until source CI green. P2 0/30 until all independent source/CI gates green; live Safari acceptance remains a release gate. Planned 2 PR (#46 + its stacked P2 successor), each CI failure fixed within the same PR.
