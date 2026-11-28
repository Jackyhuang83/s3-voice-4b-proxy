# S3-Voice UI v3 — collapsible navigation (2026-11-28)

## User request / baseline
- Existing UI v2 is LIVE on VPS and must remain untouched until separately approved and verified.
- Owner wants left navigation collapsed by default, a visible button to expand/collapse, and keyboard **K** as an optional shortcut.
- On iPhone, never permanently hide the navigation entry. Preserve the existing Cloudflare Access owner login, WebUI owner session, SSE model chat, XiaoZhi WS and raw Opus mic.

## Mature reuse decision (P0)
- Official Open WebUI Sidebar/keyboard UX is the interaction reference, **not an imported component**: its Svelte state/component tree is incompatible with this three-file vanilla JS/HTML/CSS project, and upstream branding/license obligations remain.
- Reuse the standard browser `<dialog>` / `showModal()` API (MDN & WHATWG HTML), which provides focus containment, Esc and modal backdrop on modern iPhone Safari; avoid a new component framework or an ad-hoc focus trap.
- Use actual `<button>` click semantics, not touch/pointerup-only handlers. No CDN, new routes, persistence, cookie changes or custom audio logic.
- Design: collapsed by default on every viewport, opener always in topbar (44×44 px), overlay drawer on both phone and desktop, in-panel close button, Esc, click outside, K shortcut only when focus is not editable; prevent unintended shortcuts during composition/modifier shortcuts.

## Two-PR GDGS roadmap (100 pts)
| Phase | PR | Weight | Prerequisite | Deliverable / acceptance gate |
| --- | --- | ---: | --- | --- |
| P0 official/source audit | In P1 PR | 10 | pinned UI v2 #45 | documented compatibility, owner UX and rollback constraints |
| P1 interaction | 1 PR | 60 | P0 | HTML/CSS/JS only + adapted static/mock/browser test; collapsed and open by button, keyboard K, outside click/Esc, mobile and desktop; original routes and mic unchanged |
| P2 independent gate | 1 PR | 30 | P1 | strengthened CI/visual assertions and release-only checklist; browser 375/430/768/1280 dark/light; original Auth/SSE/audio regressions; no production change |

Both PRs are stacked on the existing UI v2 tip, **not main**, because #39-#45 are not merged; do not merge unrelated #39, change VPS files or run a publisher during this UI work. A failed CI run is repaired in the same PR. No live Safari or real 4B voice claims from synthetic tests. A separate immutable, verified publisher is mandatory before any future rollout.

## Evidence
- https://github.com/open-webui/open-webui/blob/main/src/lib/components/common/Sidebar.svelte
- https://github.com/open-webui/docs/blob/main/docs/features/chat-conversations/chat-features/keyboard-shortcuts.mdx
- https://developer.mozilla.org/en-US/docs/Web/API/HTMLDialogElement/showModal
- https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/dialog
