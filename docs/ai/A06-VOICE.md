# S3-Voice-AI P2/A06 — original XiaoZhi offline Mandarin ASR + existing Edge TTS

Date: 2026-11-22. A06 is **13% of total project weight**, 1 PR (#26). Prerequisites: P0/P1 complete, A05 #25 merged and actual Debian 13 VPS generic LLM live streaming accepted. Prior overall **62%** (P2 22/35 = 63%). **P3 real Waveshare Touch-LCD-4B is NOT in A06.**

## Verified upstream re-use and rationale

- Original `xinnan-tech/xiaozhi-esp32-server v0.9.8` already implements both `ASR.VoskASR` (`type: vosk`) and `TTS.EdgeTTS` (`type: edge`). We do **not** patch or fork the upstream Python providers.
- Prefer official Vosk Chinese **vosk-model-small-cn-0.22** (~42 MB compressed, ~300 MB typical RAM) over SenseVoice ONNX (~239 MB artifact, ~600 MB runtime estimate). This fits the shared VPS's existing A03 container cap of 1 GiB more comfortably; measured CI and VPS RAM must still confirm. Vosk small targets Mandarin, may have weaker recognition quality and omits punctuation. Better accuracy is a **later measured enhancement**, not a blocker.
- The default config loader recursively merges upstream config.yaml with A03 private data/.config.yaml; the existing selected-module TTS `EdgeTTS` inherits the official `zh-CN-XiaoxiaoNeural` config. We only add Vosk ASR entry and change `selected_module.ASR`, leaving A04 WSS, A05 LLM URL/model/API Key and all other modules unmodified.
- The archived Apache-2.0 Vosk model is from official https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip. No GitHub committed model blobs. It is extracted into the **already-mounted** A03 private volume `data/models/vosk/vosk-model-small-cn-0.22`.
- Edge TTS is a remote Microsoft speech service accessed via the official project's `edge_tts` integration; it requires outbound Internet connectivity, but not a separate API subscription in this implementation. It may change terms or become unavailable and should be probed before activation. Do not present it as offline voice synthesis.

Original upstream paths:
- https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/providers/asr/vosk.py
- https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/core/providers/tts/edge.py
- https://github.com/xinnan-tech/xiaozhi-esp32-server/blob/v0.9.8/main/xiaozhi-server/config/config_loader.py
- https://alphacephei.com/vosk/models

## Scope and acceptance

| Gate | What it proves |
|---|---|
| Upstream code verified | Existing VoskASR and EdgeTTS classes, no new speech provider |
| CI static | Only ASR selection and upstream Vosk block changed; A05 API Key and A04 URL preserved; rollback |
| CI actual official v0.9.8 container | Download actual Vosk 0.22 model; EdgeTTS generates real Mandarin MP3; ffmpeg produces 16-kHz PCM; original Vosk transcribes actual Chinese; <=1 GiB cgroup; A04 identity-gated OTA/WSS remains 200/101/403; scoped rollback |
| Debian 13 actual VPS test + switch | Identical actual components, copied live A05 config, A03 server restarted **only after** speech tests and backup |
| Waveshare 4B mic/speaker/audio round-trip | **P3 A07**, not claimed by A06 |

CI uses **dummy A05 LLM credentials only** and never invokes the user's commercial GPT endpoint. This proves speech modules independently without any model subscription. All CI containers are isolated to a GitHub runner. A06 no-op until user executes the script on actual VPS.

## Target VPS rollout after successful CI

On root shell of the existing Debian 13 VPS (HomeSphere/MiniProbe untouched):

```bash
cd /tmp/s3-voice-a03-src
git fetch --depth 1 origin ai/p2-a06-asr-tts-20261122
git checkout --detach FETCH_HEAD
# check exact reviewed SHA supplied by assistant before enabling
bash tools/ai/a06-voice.sh preflight
bash tools/ai/a06-voice.sh activate
bash tools/ai/a06-voice.sh status
```

`activate` first downloads the official small ASR model if absent, uses **native server `VoskASR` and `EdgeTTS` providers** for a real TTS MP3 -> ffmpeg PCM -> ASR Chinese round-trip while A05 config remains active; only after this passes does it back up A05, edit the private YAML, restart only `s3-voice-ai-server`, probe OTA health and run A04 synthetic OTA/WSS authorization tests. If any gate fails before change, original GPT/Tunnel stays unchanged. Post-edit errors restore original YAML automatically. No new API keys, DNS records, ports, firmware flashes, or changes to other Docker services.

Quick checks: `bash tools/ai/a06-voice.sh status`. Roll back ONLY A06 selection: `bash tools/ai/a06-voice.sh rollback`; original A05 GPT API still active and A04 Cloudflare gateway untouched. The downloaded Vosk model stays cached on disk so retries do not download again.

Do not upload the private A03 YAML, A05 API Key or A04 identity.json to GitHub/chat. Share only `A06_OK`, `A06_TEST_PASS`, `A06_RESOURCE` (no private secrets). Edge online access is subject to external availability. A06 passing is **not** proof the 4B's microphone, speaker, codecs, wakeword and user pairing work; these require P3 physical verification.

## Status discipline

A06 phase weight 13% credited **only after** CI and actual host voice integration + A04 regression, PR merged. Before that P0=100%, P1=100%, P2=63% (A05 completed), P3=0%, total=62%. After A06 acceptance total=75%, P2=100%. A07/A08 remain for the 4B real hardware and release.