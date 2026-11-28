# Repository agent instructions — GDGS mandatory

Read and comply with [GDGS.md](./GDGS.md) before any planning, editing, PR creation, CI or deployment.

**Mandatory mature-component reuse rule (2026-11-28, updated):** **「成熟功能直接复用，只编写现成组件之间确实缺少的适配代码。」** Use existing official/maintained mature complete solutions or components directly. If one does not fit, investigate others. **Permitted minimal adaptation:** source-proven interface wiring, configuration/data-format mapping or deployment glue strictly necessary to connect **two existing mature components**; document the upstream APIs, missing join, scope and acceptance tests before implementation. **Forbidden without explicit user authorization:** rewriting missing features, codecs, protocols, audio recording/playback/buffers/interrupt state machines, account systems, or using the word “adapter” to mask custom product development. If no mature solution exists, stop, report evidence, and ask the user for a decision.

All product work follows GDGS P0–Pn roadmap, PR limits, acceptance levels, rollback and production change safety requirements. In particular, **S3-Voice WebUI is separate from the 4B device project**. Preserve the live WebUI v3, text chat, WebAuth, WebGateway, VoiceCore and model secrets.

**STOP:** The self-developed browser voice work in GitHub PRs #39 and #50 and the accompanying `tools/ai/webui_voice_publish.py` have been frozen. Do not merge, deploy, restart, or extend these PRs, and do not run previously supplied one-click publishing scripts. First compare existing official/mature end-to-end web voice client distributions in isolated read-only evaluation.

If this AGENTS.md conflicts with older agent or project documents, the newest user GDGS reuse-only rule wins.
