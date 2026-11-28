# S3-Voice UI v2 — P0-1 read-only design and reuse audit

Date: 2026-11-28. Parent baseline: PR #39 at `e288bbe6d5d2faccc4325dbbf76c444bcb061757` (6/6 WebUI workflows PASS; owner's production Safari access restored). **No production changes.**

## Objective / hard constraints

Borrow **information architecture and interaction principles** from [Open WebUI](https://github.com/open-webui/open-webui), not its complete app, protected branding, or backend. Preserve the self-hosted S3-Voice application identity, credentials, existing routes and audio pipeline. The existing VPS is a protected stable baseline: no auto-deploy, no change to Cloudflare Access, Caddy, Auth, A03/A04 or ESP32-S3 4B without explicit owner authorization.

## Evidence (checked from upstream and exact repository source)

| Topic | Proven source | Decision |
| --- | --- | --- |
| Upstream reference | `open-webui/open-webui` official GitHub README and `docs.openwebui.com/features/chat-conversations/chat-features/` | Borrow sidebar/topbar/composer, mobile-first grouping and model selection as **design cues only** |
| Licensing | `docs.openwebui.com/license/` and project README: Open WebUI License contains brand-retention requirements | Do not copy Svelte components, code, logos, fonts or icons; original CSS/HTML/JS only |
| Voice features | `docs.openwebui.com/features/chat-conversations/chat-features/voice-mode/` | Upstream voice providers/realtime APIs are **not** drop-in replacements for XiaoZhi WebSocket + Opus |
| Existing UI | `webui/index.html`: `loginView`, `chatView`, `messages`, `modelSelect`, `chatForm`, `messageInput`, `voiceButton` | Preserve these IDs, forms and script tags; no endpoint changes |
| Text workflow | `webui/app.js`: owner session/login/logout, `/webui/api/models`, `/webui/api/chat` SSE, 20-message bounded history in memory | Keep API and request payload unchanged, do not claim persistent chat history |
| Voice workflow | `webui/audio-ui.mjs`, `audio-opus.mjs`, `audio-worklet.js`: 16k mono Opus, `/webui/ws` and AudioWorklet | **Freeze** audio modules; front-end shell must preserve `voiceButton`, `voiceStatus`, `chatForm`, metrics injection |
| Security | `webui/index.html` CSP + `tools/ai/webui_auth.py`, `tools/ai/webui_text.py`, `deploy/ai/webui/Caddyfile.isolated` | No third-party CDN, no unsafe-inline, no new endpoints, no relaxed owner checks |
| Browser | Apple Safari on iPhone and desktop browser | Responsive viewport, 44px touch targets, visible focus, light/dark without network dependencies |

### Reuse assessment

Current UI is already self-contained and has no framework dependency; importing Open WebUI/Svelte/Tailwind introduces a build pipeline, backend/route coupling and deployment risk larger than the desired visual benefit. Reuse **existing native browser layout, CSS custom properties, HTML semantic elements, app.js event bindings** and CI. New JavaScript should be restricted to presentation concerns; do not add localStorage persistence of personal chat content or credentials.

### Known limitations / intentionally deferred

- No server-persisted conversation/history API; sidebar may only offer navigation and **current-tab session** awareness, with explicit ephemeral description.
- No voice-provider substitution or audio latency tuning in UI project.
- No multi-user, uploads, RAG, agents, realtime paid APIs, service worker, or added Caddy routes.
- User's production URL and auth remain immutable.

## Complete UI project roadmap (6 PRs; 100 points)

| Phase | PR | Weight | Deliverable | Dependency / acceptance |
| --- | --- | ---: | --- | --- |
| P0 research and design | UI-P0-1 | 8 | Current/upstream source and licensing audit | PR #39 baseline; evidence mapped to exact files |
| P0 research and design | UI-P0-2 | 12 | Wireframe interaction contract and test gates | P0-1; no route/audio/JS changes |
| P1 core layout | UI-P1-1 | 25 | Responsive app shell, sidebar/topbar, mobile hierarchy | P0-2; login/auth/audio DOM IDs preserved; no JS regressions |
| P1 core layout | UI-P1-2 | 20 | Chat stream layout, model selector, input and user interactions | P1-1; SSE/model/voice/keyboard unchanged |
| P2 polish and acceptance | UI-P2-1 | 20 | Light/dark, touch, focus, contrast and Safari adaptivity | P1-2; keyboard and accessibility tests pass |
| P2 polish and acceptance | UI-P2-2 | 15 | Full CI, screenshot/browser pilot, reversible rollout instructions | P2-1; 6/6 original WebUI workflows + new UI tests, manual Safari required |

Phase weights: P0=20, P1=45, P2=35; total 100. Each phase has 2 PRs (max 5). PR weights track **accepted completion**, not commit count. UI development begins in a stacked branch from PR #39, with no merge to main or production rollout without owner authorization. Preserve green PR #39 and never change its source to accommodate UI.

## Development flow

Read-only scope → approved 6-PR plan → official-source reuse audit → tightly scoped UI code → GitHub automated regressions → review/merge separate UI PRs → optional owner-approved isolated preview → manual Safari verification → only then production acceptance. Production is not an automated CI target.
