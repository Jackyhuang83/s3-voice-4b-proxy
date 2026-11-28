#!/usr/bin/env python3
"""Exercise the installed official XiaoZhi A03 Opus sender with synthetic packets.

Run **inside** the existing A03 server container in isolated GitHub CI.
No network, no microphone, no API calls, no server files/config changes.
"""
import asyncio
import time
from core.handle import sendAudioHandle as sender

assert sender.AUDIO_FRAME_DURATION == 60
assert sender.PRE_BUFFER_COUNT == 5

class QuietLogger:
    def bind(self, **_): return self
    def debug(self, *_): pass
    def info(self, *_): pass
    def error(self, *_): pass

class FakeWebSocket:
    def __init__(self):
        self.sent = []
    async def send(self, data):
        self.sent.append((time.monotonic(), data))

class FakeConnection:
    def __init__(self, delay):
        self.logger = QuietLogger()
        self.config = {"tts_audio_send_delay": delay}
        self.sentence_id = "CI_SYNTHETIC"
        self.client_abort = False
        self.conn_from_mqtt_gateway = False
        self.websocket = FakeWebSocket()
        self.last_activity_time = 0

async def check():
    packets = [bytes([n]) * 24 for n in range(1, 10)]

    # Old default bypasses the queue for the first five frames.
    baseline = FakeConnection(0)
    await sender.sendAudio(baseline, packets)
    immediate = len(baseline.websocket.sent)
    assert immediate == 5, f"v0.9.8 expected 5 immediate packets, got {immediate}"
    await asyncio.wait_for(baseline.audio_rate_controller.queue_empty_event.wait(), timeout=5)
    assert [payload for _,payload in baseline.websocket.sent] == packets
    baseline.audio_rate_controller.stop_sending()

    # Native 60ms mode queues ALL frames, eliminating the initial burst.
    paced = FakeConnection(60)
    await sender.sendAudio(paced, packets)
    assert len(paced.websocket.sent) == 0, "positive delay still burst-sends initial Opus packets"
    await asyncio.wait_for(paced.audio_rate_controller.queue_empty_event.wait(), timeout=5)
    sent = paced.websocket.sent
    assert [payload for _,payload in sent] == packets
    gaps = [sent[n+1][0] - sent[n][0] for n in range(len(sent)-1)]
    assert len(gaps) == 8
    assert all(0.025 <= gap <= 0.30 for gap in gaps), \
        "expected paced intervals (runner may have scheduling jitter)"
    paced.audio_rate_controller.stop_sending()
    print("A07_OPUS_FRAME_PACING_PASS: v0.9.8 default=5 burst; 60ms=0 burst; 9/9 ordered frames")

asyncio.run(check())
