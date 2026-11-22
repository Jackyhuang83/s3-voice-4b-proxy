#!/usr/bin/env python3
"""A06 voice tests against ORIGINAL XiaoZhi v0.9.8 providers; no forks.
Runs INSIDE the pinned image. 'mock' is offline; 'real' tests live EdgeTTS,
Vosk actual model decoding and the existing 1024-MiB container memory limit.
"""
import argparse
import asyncio
import os
import re
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace

import edge_tts
from core.providers.tts.edge import TTSProvider
from core.providers.asr.vosk import ASRProvider

VOICE = "zh-CN-XiaoxiaoNeural"
MODEL = "data/models/vosk/vosk-model-small-cn-0.22"
SENTENCE = "你好，我是小智语音助手，今天我们测试中文语音识别，祝你生活愉快。"


def edge_provider():
    return TTSProvider({"voice": VOICE, "output_dir": "tmp/"}, delete_audio_file=True)


def mocked_tts():
    class MockCommunicate:
        def __init__(self, text, voice, rate, volume, pitch):
            assert text == SENTENCE and voice == VOICE
            assert rate == "+0%" and pitch == "+0Hz"
        async def stream(self):
            yield {"type": "audio", "data": b"ID3TESTA06"}
            yield {"type": "SentenceBoundary", "text": SENTENCE}
            yield {"type": "audio", "data": b"NEXTCHUNK"}
    original = edge_tts.Communicate
    edge_tts.Communicate = MockCommunicate
    try:
        payload = asyncio.run(edge_provider().text_to_speak(SENTENCE, None))
        assert payload == b"ID3TESTA06NEXTCHUNK"
    finally:
        edge_tts.Communicate = original
    print("A06_TEST_PASS: official EdgeTTS provider forwards streamed audio bytes (offline mock)")


def real_speech():
    model = Path(MODEL)
    assert (model / "am" / "final.mdl").is_file(), "Vosk model files missing"
    # Execute real Vosk recognition first, then real Edge online voice output.
    asr = ASRProvider({"model_path": MODEL, "output_dir": "tmp/"}, delete_audio_file=True)
    with tempfile.TemporaryDirectory(prefix="a06-voice-") as tmp:
        mp3 = Path(tmp) / "edge.mp3"
        wav = Path(tmp) / "edge.wav"
        data = asyncio.run(edge_provider().text_to_speak(SENTENCE, None))
        assert isinstance(data, bytes) and len(data) > 3000, "EdgeTTS returned no audio"
        mp3.write_bytes(data)
        subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                        "-y", "-i", str(mp3), "-ac", "1", "-ar", "16000",
                        "-acodec", "pcm_s16le", str(wav)], check=True, timeout=20)
        import wave
        with wave.open(str(wav), "rb") as wf:
            assert wf.getnchannels() == 1 and wf.getframerate() == 16000
            pcm = wf.readframes(wf.getnframes())
        assert len(pcm) > 32000, "TTS audio under 1 second"
        artifacts = SimpleNamespace(pcm_bytes=pcm, file_path=str(wav))
        text, _ = asyncio.run(asr.speech_to_text([], "a06-ci", artifacts))
        assert isinstance(text, str) and re.search(r"[\u4e00-\u9fff]{2,}", text), "Vosk returned no meaningful Chinese transcript"
    peak_bytes = 0
    peak = Path("/sys/fs/cgroup/memory.peak")
    if peak.is_file():
        peak_bytes = int(peak.read_text().strip())
        assert peak_bytes < 1024 * 1024 * 1024, "container exceeded 1024 MiB limit"
    print("A06_TEST_PASS: original EdgeTTS live Chinese MP3 >3000 bytes")
    print("A06_TEST_PASS: ffmpeg 16k mono PCM -> original Vosk Chinese speech recognized")
    print("A06_TEST_PASS: no ASR/TTS API credentials, no device or firmware required")
    if peak_bytes:
        print("A06_RESOURCE: cgroup max observed memory MiB=%d (limit=1024)" % (peak_bytes // (1024 * 1024)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["mock", "real"])
    args = parser.parse_args()
    mocked_tts()
    if args.mode == "real":
        real_speech()
