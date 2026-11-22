# S3-Voice-AI P2-A05 — Generic GPT / OpenAI-compatible API

**Date:** 2026-11-22. **Depends on:** A03 #23 and A04 #24 merged, public WSS/OTA tested. Project overall 40% before A05. A05 weight 22%, A06 weight 13%. **No real provider key has been supplied or configured.**

## Decision — one provider, not three subscriptions

Reuse pinned xinnan-tech/xiaozhi-esp32-server **v0.9.8** original OpenAI LLM implementation. Its `core/providers/llm/openai/openai.py` already accepts `base_url`, `model_name`, `api_key` and streams `chat.completions.create(stream=True)`. No custom SDK, model router or gateway is needed. Any genuine OpenAI-compatible streamed Chat Completions provider can be configured.

Config selection uses standard upstream fields:

```yaml
selected_module:
  LLM: GenericGPTLLM
LLM:
  GenericGPTLLM:
    type: openai
    base_url: https://api.provider.example/v1
    model_name: example-model
    api_key: REPLACE_PRIVATELY_NOT_A_REAL_KEY
    max_tokens: 256
    timeout: 30
```

This is illustrative, NOT a valid account. Provider may be a compatible aggregator or a provider offering free quotas. Even free-tier models generally require API enrollment and a Key. **ChatGPT Plus is separate from the paid OpenAI Platform API** and cannot serve as an API Key. No separate DeepSeek/OpenAI/Gemini subscriptions are required to DEVELOP A05. To activate a real model, however, one legitimate API credential or self-hosted API endpoint is needed.

Official source: https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/providers/llm/openai/openai.py
Official config: https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/config.yaml

## Deliverables — single PR

- `tools/ai/a05-config.py`: stdlib-only input validation and one upstream config selection; HTTPS public provider URL only, supports arbitrary compatible model IDs.
- `tools/ai/a05-generic.sh`: `preflight|activate|status|rollback`; preflight runs A04 local synthetic tests, no container changes; live activation requires explicit YES for a possibly billable tiny stream.
- `tests/ai/a05_provider_contract.py`: runs **original upstream** Python LLMProvider with a local mock SSE server inside the official v0.9.8 container; no vendor call or spend in CI.
- `tests/ai/a05_config_test.py`: guard private key file 0600, preserve A04 WSS and ASR, refusal of insecure/private base URLs, restore original config.
- `.github/workflows/ai-a05-generic.yml`: official server image integration + offline fake streaming completion + YAML parsing and restore.

## VPS workflow and security boundaries

No API Key yet: **run no activation**. The CI mock is not proof that any real provider is reachable or authorized. Do not claim P2 completion.

When one provider is available and exact reviewed branch/commit is green, in target Debian 13 root Shell:

```bash
cd /tmp/s3-voice-a03-src
git fetch --depth 1 origin ai/p2-a05-generic-openai-20261122
git checkout --detach FETCH_HEAD
# Require reviewed SHA match before using these commands on production
bash tools/ai/a05-generic.sh preflight
bash tools/ai/a05-generic.sh activate
```

Activation prompts for provider base URL, model ID and masked API key. It uses one short STREAMING request through the original official provider after the user types YES; the provider SDK may retry temporary errors, so the provider account may incur charges. If this fails, the live configuration is untouched. After a successful test, the script backs up only the A03 YAML, selects GenericGPTLLM, restarts only A03 and runs A04 synthetic OTA+WSS smoke. No changes to HomeSphere, MiniProbe, DNS, Cloudflare Tunnel or public VPS firewall.

API Key is not accepted via CLI arguments or chat. A transient key file is kept inside the private root-owned A03 data mount and cleaned up when the command exits; the active official XiaoZhi YAML necessarily keeps the real API key (chmod 0600). Do not publish this file or a backup. Model response cap 256 tokens is a light guardrail; configure cost limits and alerts with the actual provider before connecting a real device.

`bash tools/ai/a05-generic.sh status` reports whether GenericGPTLLM is selected, never prints Key. `bash tools/ai/a05-generic.sh rollback` restores original A03/A04 YAML from a private backup, restarts only A03 and validates the existing A04 gate.

**Scope:** A05 only covers TEXT LLM streaming. A03's ASR key is still a dummy. A06 handles real ASR/TTS; P3 handles actual Waveshare 4B enrollment/voice/dialogue. A04 public identity tests still use synthetic IDs.

## Acceptance

| Gate | Result |
|---|---|
| Official openai-compatible provider source audited | SOURCE PASS |
| Safe configuration + rollback + mock tests | CI pending |
| Actual vendor stream from real API Key | BLOCKED (no key) |
| Actual target VPS GenericGPTLLM activation + A04 preserved | NOT RUN |
| 4B voice dialogue | P3 NOT RUN |

**GDGS:** A05 weight 22% is credited only after actual vendor/host gates and PR merge. Until then overall progress remains 40%, P2 0%.
