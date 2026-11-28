# S3-Voice UI v2 — P0-2 visual and interaction contract

Parent: UI-P0-1 #40 → validated WebUI P2-1 #39. Separate UI-only program, no change to the user VPS.

## Visual language (original implementation; Open WebUI for reference only)

- Quiet neutral surfaces, airy responsive spacing, subtle 1px borders, restrained accent used for primary actions, native system typography.
- Desktop (>= 900px): left navigation rail/sidebar 228–264px and flexible main region. The main conversation max-width 820px. Sidebar is **navigation only**, not a claim of server-stored history.
- Tablet (600–899px): condensed application chrome; keep model picker and composer visible without side scrolling.
- iPhone (< 600px): single-column view; no default obstructing side drawer; 16px text input (avoid Safari auto zoom), controls at least 44px where practical, `env(safe-area-inset-bottom)`, no horizontal scroll.
- Landing after login: a distinct welcome state, clear GPT/DeepSeek model selector, chat bubbles, compact voice control. Underlying app still owns session and textual SSE.
- Voice diagnostics remain legible, but not dominant; do not alter AudioWorklet/Opus or hide the stop affordance.

## Preserved DOM bindings and operational behavior

- All existing element IDs in `webui/index.html` are API-like contracts: `connectionStatus`, `logoutBtn`, `loginView`, `loginForm`, `ownerPassword`, `loginBtn`, `loginError`, `chatView`, `modelSelect`, `newChatBtn`, `messages`, `welcome`, `chatForm`, `messageInput`, `voiceButton`, `sendBtn`, `voiceStatus`, `appNotice`.
- Existing CSS/HTML metadata CSP and `/webui/app.css`, `/webui/app.js`, `/webui/audio-ui.mjs` imports stay exact.
- `app.js` remains responsible for login/logout, session, model SSE, new/reset, Enter/Shift+Enter; `audio-ui.mjs` owns voice capture and metrics. New UI markup must never register duplicate IDs or override audio event handlers.
- No persistent chat history: new navigation describes `本次会话` only. No localStorage of chat text. Do not show previous conversations unless an actual approved history API is built.
- The project uses Cloudflare Access + existing owner cookie; do not mimic or replace authentication UX with a new provider.
- Never expose model API secrets, user audio, chat content or cookies to the interface logs.

## Acceptance gates and rollback

1. P0 gate: exact official-source/license references; roadmap has 6 logical PRs, stages total 100, release freeze and rollback noted.
2. P1-1 source/CI gate: HTML tags well formed, all above IDs unique, the same script and CSS sources remain, no new backend endpoint/third-party CDN; old `test_webui_auth.py`, `test_webui_audio_ui.mjs` and raw Opus validations continue to pass; zero production changes.
3. P1-2 interaction gate: mobile nav can open/close without hijacking voiceButton and keyboard, new chat still clears *in-memory* messages, model switch keeps existing semantics, no API route modification.
4. P2-1 visual/a11y gate: test viewport widths 375, 430, 768, 1280, check no overflow; dark/light contrast, touch targets and prefers-reduced-motion; no external fonts/scripts.
5. P2-2 final gate: 6/6 inherited WebUI CI + new UI tests PASS, PR review, reversible file-only pilot (with backup) and separately owner-accepted Safari real use; production rollout is disabled by default.

## Screen outline

Desktop: [S3 Voice / session nav / status] | [topbar: model and new chat] / [messages] / [composer + send/voice].
Mobile: [brand • connection state] / [model and new chat] / [messages] / [sticky composer with safe area]. Keep login as standalone card and show a clear logout action.

### Explicit non-goals

Importing Open WebUI Svelte components, UI branding, RAG, tool catalog, file upload, paid realtime API, new history storage, new Docker container, CSS remote dependencies, modifying Caddy or touching original S3-Voice 4B firmware.
