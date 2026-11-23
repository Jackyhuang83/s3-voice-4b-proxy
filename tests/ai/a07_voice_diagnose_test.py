#!/usr/bin/env python3
"""A07 voice diagnostics parse only metrics; never print private log payloads."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = spec_from_file_location("voice_diag", root / "tools/ai/a07-voice-diagnose.py")
module = module_from_spec(spec)
spec.loader.exec_module(module)

raw = "\n".join([
    "2026-11-23T12:00:00.000000Z 识别文本: SECRET_PERSONAL_USER_SPEECH",
    "2026-11-23T12:00:00.500000Z 大模型收到用户消息: SECRET_USER_QUESTION",
    "2026-11-23T12:00:03.500000Z 语音生成成功: SECRET_TTS_AUDIO_FILE",
    "2026-11-23T12:00:04.000000Z 语音生成失败1次: SECRET_TTS_RETRY",
    "2026-11-23T12:00:06.500000Z 发送第一段语音: SECRET_PERSONAL_REPLY",
    "2026-11-23T12:00:07.000000Z 语音生成失败: KEY_SECRET_SHOULD_NEVER_SHOW",
    "2026-11-23T12:00:07.500000Z 发送音频失败: SECRET_PATH",
    "2026-11-23T12:00:08.000000Z Connection error: SECRET_ID",
    "2026-11-23T12:00:08.500000Z 客户端断开连接",
])
counts, gaps = module.classify(raw)
assert counts["ASR"] == 1
assert counts["GPT"] == 1
assert counts["FIRST_TTS"] == 1
assert counts["TTS_FAIL"] == 1
assert counts["AUDIO_SEND_FAIL"] == 1
assert counts["WS_CONN_FAIL"] == 1
assert counts["WS_DISCONNECT"] == 1
assert gaps == [6.5]
phase_counts, phases = module.pipeline_timings(raw)
assert phase_counts == {"TTS_READY": 1, "TTS_RETRY": 1, "MATCHED_TURNS": 1, "AMBIGUOUS_TURNS": 0, "UNMATCHED_FIRST_TTS": 0}
assert phases["ASR_TO_GPT"] == [0.5]
assert phases["GPT_TO_TTS_READY"] == [3.0]
assert phases["GPT_TO_FIRST_TTS"] == [6.0]
assert "SECRET_PERSONAL_USER_SPEECH" not in repr(phase_counts)
assert "SECRET_TTS_AUDIO_FILE" not in repr(phases)

# A pair must never be stitched across another utterance. Previously this
# could falsely yield 40s+ "GPT latency" despite a fast earlier round trip.
interleaved = "\n".join([
    "2026-11-23T12:00:00Z 识别文本: OLD_PRIVATE_QUESTION",
    "2026-11-23T12:00:00.100000Z 大模型收到用户消息: OLD_QUESTION",
    "2026-11-23T12:00:40Z 识别文本: NEW_PRIVATE_QUESTION",
    "2026-11-23T12:00:40.100000Z 大模型收到用户消息: NEW_QUESTION",
    "2026-11-23T12:00:42Z 语音生成成功: NEW_PRIVATE_ANSWER",
    "2026-11-23T12:00:43Z 发送第一段语音: NEW_PRIVATE_ANSWER",
])
new_counts, new_phases = module.pipeline_timings(interleaved)
assert new_counts["AMBIGUOUS_TURNS"] == 1
assert new_counts["MATCHED_TURNS"] == 1
assert len(new_phases["GPT_TO_FIRST_TTS"]) == 1
assert abs(new_phases["GPT_TO_FIRST_TTS"][0] - 2.9) < 0.01
assert len(new_phases["GPT_TO_TTS_READY"]) == 1
assert "OLD_PRIVATE" not in str(new_counts) + str(new_phases)

# Without ASR/GPT anchors, standalone TTS log must not produce invented durations.
lonely = "2026-11-23T12:00:00Z 发送第一段语音: STALE_SECRET"
lonely_counts, lonely_phases = module.pipeline_timings(lonely)
assert lonely_counts["UNMATCHED_FIRST_TTS"] == 1
assert not lonely_phases["GPT_TO_FIRST_TTS"]

assert module.timestamp("nonsense") is None
counts2, gaps2 = module.classify("2026-11-23T12:00:00Z unrelated private text\n")
assert counts2["ASR"] == 0 and not gaps2
print("A07_DIAG_PASS: XiaoZhi original log categories and 6.5s coarse gap parsed; private speech/text excluded")
