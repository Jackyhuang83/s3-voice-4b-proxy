# Repository agent instructions — GDGS mandatory

Read and comply with [GDGS.md](./GDGS.md) before any planning, editing, PR creation, CI or deployment.

**Mandatory reuse-only rule (2026-11-28):** Use existing official/maintained complete solutions directly. If a candidate cannot be used, evaluate other mature solutions; **never independently write or reimplement missing functionality, a compatibility layer, an adapter, a codec, a protocol, a WebVoice recording/playback/buffering/interrupt mechanism, or a replacement client** without the user's **explicit approval for that named exception**. If none fit, stop, report evidence, and request a decision. No autonomous fallback to custom development.

All product work follows GDGS P0–Pn roadmap, PR limits, acceptance levels, rollback and production change safety requirements. In particular, **S3-Voice WebUI is separate from the 4B device project**. Preserve the live WebUI v3, text chat, WebAuth, WebGateway, VoiceCore and model secrets.

**STOP:** The self-developed browser voice work in GitHub PRs #39 and #50 and the accompanying `tools/ai/webui_voice_publish.py` have been frozen. Do not merge, deploy, restart, or extend these PRs, and do not run previously supplied one-click publishing scripts. First compare existing official/mature end-to-end web voice client distributions in isolated read-only evaluation.

If this AGENTS.md conflicts with older agent or project documents, the newest user GDGS reuse-only rule wins.
