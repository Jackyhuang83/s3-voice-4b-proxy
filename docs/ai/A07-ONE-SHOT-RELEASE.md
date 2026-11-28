# A07 native Opus pacing: one-shot release

2026-11-28. **Source / CI work, real Waveshare 4B playback not yet accepted.**

## Reuse and root-cause hypothesis

- XiaoZhi official server **v0.9.8** uses PRE_BUFFER_COUNT=5 and AUDIO_FRAME_DURATION=60; the existing top-level tts_audio_send_delay=60 activates **queue all frames**, bypassing the initial unpaced 5 frames.
- Source helper: tools/ai/a07-audio-pacing.py in existing **PR #27**. It checks the actual running sender module before touching any YAML, preserves the original config in private exact-byte backup, modifies only the official delay setting, and supports automatic or explicit rollback.
- Tests: tests/ai/a07_opus_frame_pacing_test.py runs inside the **real official v0.9.8 container** in CI using nine synthetic packets (no network/API charge), checks immediate default=5 and paced=0 and exact frame order. That is stronger than merely checking a parsed YAML setting.
- New guarded wrapper: tools/ai/a07-voice-once.py obtains its two helper files from exact immutable source commit **2ed2cd2c7f543140e60b182f41080899b4a9bc6e**, verifies Git blob hashes and uses a private temporary directory. It refuses unexpected preflight state or an old uncompleted trial, and is safe to re-run if pacing is already active.

## Production safety

- Target: existing Debian 13 VPS, A03 XiaoZhi v0.9.8 and existing A04 **real hardware-mode** authorization. If baseline or implementation differs, refuse to apply; never weaken security to force a successful run.
- Preserve user-selected generic API endpoint, credentials and all selected model / ASR / TTS adapters. No vendor is a hardcoded product dependency.
- Restarts **only A03 server once**, temporarily interrupting 4B voice. Gateway, Tunnel, WebUI, Cloudflare Access, Caddy, HomeSphere, MiniProbe and device firmware untouched.
- Reads four protected containers' IDs and start timestamps before/after, and verifies A03 OTA and A04 OTA/WSS authorization after restart. If post-apply verification fails, request exact-byte A03 rollback. No secrets, request URLs, private device identities or raw speech in output.
- The publisher is a source-only GitHub PR until CI and human-reviewed pinned command are ready. Do not run unpinned branch code against production.

## Operator one-shot release / acceptance

The assistant will supply a single pinned root VPS command / uploadable launcher using a reviewed Git commit and the wrapper's blob hash. It performs the source hash check, A03/A04 preflight, backup, native 60ms configuration, A03-only restart, gateway/WS safety checks and fail-closed rollback on errors, without intermediate prompts.

Expected success signals:

    A07_VOICE_PINNED_SOURCE_PASS
    A07_VOICE_RUNTIME_PREFLIGHT_PASS
    A07_VOICE_PRODUCTION_BASELINE_PASS
    A07_VOICE_PACING_60MS_ACTIVE_PASS
    A07_VOICE_A04_OTA_WSS_AND_WEBUI_UNCHANGED_PASS
    A07_VOICE_REAL_4B_PLAYBACK_UNVERIFIED

Already active: A07_VOICE_PACING_ALREADY_ACTIVE_PASS; no restart.
Unrecognized baseline: A07_VOICE_BLOCKED; no blind retry.
An explicit 'rollback' mode uses the exact A03 backup and confirms OTA/WSS; never deletes backup evidence.

**One** real 4B long-sentence spoken answer and one subsequent wake are the physical acceptance gate: no middle-word stutter, no truncated ending, no premature standby and stable WS. The helper cannot assert these from server logs. On any listening failure, stop and use the pinned rollback; do not loop manual changes, reflash or install rolling Docker latest.

## Existing roadmap

A03–A06 accepted 75% (recorded previously); A07 is +15%, A08 +10%. A07 source, CI build, official container test, actual VPS deployment and real 4B device must be separately reported. **A07 remains open / Draft until hardware accepted**, and A08 remains downstream. Family accounts Issue #48 and OpenCode import Issue #49 follow voice stabilization.
