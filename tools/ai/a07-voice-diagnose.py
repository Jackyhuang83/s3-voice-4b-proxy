#!/usr/bin/env python3
"""A07 4B audio latency snapshot: READ ONLY; never print raw server logs.

Checks original A03 CPU/memory and published XiaoZhi v0.9.8 log milestones.
Run while the owner is speaking to 4B. No model calls, config or restart.
"""
import argparse
import json
import re
import statistics
import subprocess
import time
from datetime import datetime

SERVER = "s3-voice-ai-server"
GATEWAY = "s3-voice-ai-gateway"
TUNNEL = "s3-voice-ai-tunnel"
MARKS = (
    ("ASR", "识别文本:"),
    ("ASR", "识别文本："),
    ("GPT", "大模型收到用户消息:"),
    ("FIRST_TTS", "发送第一段语音:"),
)
ALARMS = {
    "ASR_FAIL": ("VOSK语音识别失败", "识别失败", "合并后的PCM数据为空"),
    "TTS_FAIL": ("语音生成失败:", "语音生成失败：", "Failed to generate TTS file"),
    "AUDIO_SEND_FAIL": ("发送音频失败", "音频发送循环异常", "audio_play_priority_thread:"),
    "LLM_FAIL": ("LLM 处理出错", "LLM stream processing error"),
    "WS_CONN_FAIL": ("Connection error:", "WebSocket连接失败", "websocket connection closed"),
    "WS_DISCONNECT": ("客户端断开连接",),
}
TIMESTAMP = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d))")
PERCENT = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")


def run(args, seconds=20):
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=seconds, check=False)
        return p.stdout if p.returncode == 0 else ""
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""


def short_state(name):
    template = "{{.State.Status}}|{{.State.OOMKilled}}|{{.RestartCount}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.Memory}}"
    s = run(["docker", "inspect", "--format", template, name]).strip()
    if not s:
        return "not_available"
    try:
        status, oom, restarts, nano, memory = s.split("|")
        cpu = float(nano) / 1e9 if float(nano) else 0
        mem = int(memory) / 1024**2 if int(memory) else 0
        return f"status={status} oom={oom} restarts={restarts} cpu_limit={cpu:g} mem_limit_MiB={mem}"
    except (ValueError, IndexError):
        return "parse_unavailable"


def stats_snapshot(names):
    raw = run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *names], seconds=30)
    out = {}
    for line in raw.splitlines():
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            continue
        name = row.get("Name", "")
        cpu = PERCENT.search(str(row.get("CPUPerc", "")))
        if name in names and cpu:
            out[name] = {"cpu": float(cpu.group(1)),
                         "ram": re.sub(r"[^0-9A-Za-z. /]", "", str(row.get("MemUsage", "")))[:60]}
    return out


def timestamp(line):
    m = TIMESTAMP.match(line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m.group(1).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def classify(raw):
    counts = {key: 0 for key in ["ASR", "GPT", "FIRST_TTS", *ALARMS]}
    milestones = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        for category, key in MARKS:
            if key in line:
                counts[category] += 1
                ts = timestamp(line)
                if ts is not None:
                    milestones.append((ts, category))
                break
        for category, keywords in ALARMS.items():
            if any(keyword in line for keyword in keywords):
                counts[category] += 1
    # Approximate gap ASR result -> first TTS segment log within an interaction.
    # If sessions overlap, this is a screening heuristic, not an end-to-end SLA.
    gaps = []
    current_asr = None
    for ts, kind in sorted(milestones):
        if kind == "ASR":
            current_asr = ts
        elif kind == "FIRST_TTS" and current_asr is not None:
            diff = ts - current_asr
            if 0 <= diff <= 120:
                gaps.append(diff)
            current_asr = None
    return counts, gaps


def pipeline_timings(raw):
    """Conservative single-turn screening from unchanged XiaoZhi log milestones.

    A valid candidate needs ASR -> GPT -> first-audio log with no intervening
    new ASR/GPT. A separate TTS-ready timestamp is optional. Logs do not carry
    a reliable session ID, so even these candidates are estimates, NOT proof
    when multiple clients concurrently talk. Never retain/print speech text.
    """
    phases = {
        "ASR_TO_GPT": [],
        "GPT_TO_FIRST_TTS": [],
        "GPT_TO_TTS_READY": [],
        "TTS_READY_TO_FIRST": [],
    }
    counts = {"TTS_READY": 0, "TTS_RETRY": 0,
              "MATCHED_TURNS": 0, "AMBIGUOUS_TURNS": 0,
              "UNMATCHED_FIRST_TTS": 0}
    state = None

    def elapsed(first, second):
        if first is None or second is None:
            return None
        delay = second - first
        return delay if 0 <= delay <= 120 else None

    for line in raw.splitlines():
        when = timestamp(line)
        # Only original INFO milestones; different threads can interleave.
        if re.search(r"语音生成失败[0-9]+次", line):
            counts["TTS_RETRY"] += 1
        if "语音生成成功:" in line or "语音生成成功：" in line:
            counts["TTS_READY"] += 1
            if state and state["gpt"] is not None and state["ready"] is None:
                state["ready"] = when
            continue
        if "识别文本:" in line or "识别文本：" in line:
            if state is not None:
                counts["AMBIGUOUS_TURNS"] += 1
            state = {"asr": when, "gpt": None, "ready": None}
            continue
        if "大模型收到用户消息:" in line:
            if state is None or state["gpt"] is not None:
                counts["AMBIGUOUS_TURNS"] += 1
                state = None
            else:
                state["gpt"] = when
            continue
        if "发送第一段语音:" in line:
            if state is None or state["gpt"] is None:
                counts["UNMATCHED_FIRST_TTS"] += 1
                state = None
                continue
            ag = elapsed(state["asr"], state["gpt"])
            gf = elapsed(state["gpt"], when)
            if ag is None or gf is None:
                counts["AMBIGUOUS_TURNS"] += 1
            else:
                phases["ASR_TO_GPT"].append(ag)
                phases["GPT_TO_FIRST_TTS"].append(gf)
                counts["MATCHED_TURNS"] += 1
                gr = elapsed(state["gpt"], state["ready"])
                rf = elapsed(state["ready"], when)
                if gr is not None and rf is not None:
                    phases["GPT_TO_TTS_READY"].append(gr)
                    phases["TTS_READY_TO_FIRST"].append(rf)
            state = None
    return counts, phases

def sample(seconds, window_seconds):
    print("A07_DIAG: read-only 4B speech latency snapshot; no API request or configuration change", flush=True)
    for name in (SERVER, GATEWAY, TUNNEL):
        print("A07_CONTAINER: " + name + " " + short_state(name), flush=True)
    data = {name: [] for name in (SERVER, GATEWAY, TUNNEL)}
    for idx in range(3):
        for name, row in stats_snapshot(list(data)).items():
            data[name].append(row)
        if idx != 2:
            time.sleep(seconds / 2)
    for name, rows in data.items():
        if rows:
            cpus = [row["cpu"] for row in rows]
            print(f"A07_RESOURCE: {name} CPU_percent_min={min(cpus):.1f} "
                  f"max={max(cpus):.1f} RAM_last={rows[-1]['ram']}", flush=True)
        else:
            print(f"A07_RESOURCE: {name} unavailable", flush=True)
    raw = run(["docker", "logs", "--timestamps", "--since", f"{window_seconds}s",
               "--tail", "1500", SERVER], seconds=20)
    counts, gaps = classify(raw)
    phase_counts, phases = pipeline_timings(raw)
    print("A07_EVENTS_15M: " + " ".join(f"{key}={value}" for key, value in counts.items()), flush=True)
    print(f"A07_TTS_WINDOW_{window_seconds}S: " + " ".join(f"{key}={value}" for key, value in phase_counts.items()), flush=True)
    for kind, values in phases.items():
        if values:
            print(f"A07_TIMING_{kind}: n={len(values)} median_s={statistics.median(values):.1f} "
                  f"max_s={max(values):.1f} (approx, concurrent sessions can overlap)", flush=True)
        else:
            print(f"A07_TIMING_{kind}: unavailable", flush=True)
    if gaps:
        print(f"A07_GAP_ASR_TO_FIRST_TTS_LOG: n={len(gaps)} "
              f"median_s={statistics.median(gaps):.1f} max_s={max(gaps):.1f} "
              "(approx, not full round-trip latency)", flush=True)
    else:
        print("A07_GAP_ASR_TO_FIRST_TTS_LOG: unavailable (no matching INFO milestones)", flush=True)
    tunnel_raw = run(["docker", "logs", "--since", "15m", "--tail", "500", TUNNEL], seconds=20).lower()
    if tunnel_raw:
        patterns = {
            "reconnect": "reconnect", "failed_connection": "failed to",
            "websocket_reset": "connection reset", "timeout": "timeout",
        }
        print("A07_TUNNEL_15M: " + " ".join(
            key + "=" + str(tunnel_raw.count(value)) for key, value in patterns.items()), flush=True)
    else:
        print("A07_TUNNEL_15M: unavailable", flush=True)
    print("A07_DIAG_END: only counts and resource readings printed; no conversations or secrets", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=12, help="interval between first and last CPU sample (4..60)")
    ap.add_argument("--window", type=int, default=180, help="log lookback seconds (60..900); use one quiet short 4B voice turn")
    args = ap.parse_args()
    if not 4 <= args.seconds <= 60:
        ap.error("--seconds must be between 4 and 60")
    if not 60 <= args.window <= 900:
        ap.error("--window must be between 60 and 900")
    sample(args.seconds, args.window)
