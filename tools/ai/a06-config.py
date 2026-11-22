#!/usr/bin/env python3
"""A06: adapt only the selected ASR to upstream Vosk; EdgeTTS stays upstream-default.
No PyYAML dependency on the VPS host; official container validates resulting YAML.
"""
import argparse
import os
from pathlib import Path

MODEL_REL = "data/models/vosk/vosk-model-small-cn-0.22"
ASR_BEFORE = "  ASR: OpenaiASR\n"
ASR_AFTER = "  ASR: VoskASR\n"
ASR_BLOCK = "ASR:\n  OpenaiASR:\n    api_key: PENDING_A05_NOT_A_REAL_KEY\n"
VOSK = (
    "  VoskASR:\n"
    "    type: vosk\n"
    "    model_path: " + MODEL_REL + "\n"
    "    output_dir: tmp/\n"
)


def transform(original):
    if original.count("  LLM: GenericGPTLLM\n") != 1:
        raise ValueError("A05 upstream generic GPT not active")
    if original.count("  TTS: EdgeTTS\n") != 1:
        raise ValueError("official EdgeTTS not selected")
    if original.count(ASR_BEFORE) != 1 or original.count(ASR_BLOCK) != 1:
        raise ValueError("A03/A05 baseline changed, no automatic overwrite")
    if "  VoskASR:\n" in original:
        raise ValueError("VoskASR already present")
    return original.replace(ASR_BEFORE, ASR_AFTER, 1).replace(ASR_BLOCK, ASR_BLOCK + VOSK, 1)


def apply(path):
    p = Path(path)
    original = p.read_text()
    updated = transform(original)
    temp = p.with_name(".config.yaml.a06tmp")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(updated)
    os.replace(temp, p)
    os.chmod(p, 0o600)
    print("A06_OK: original VoskASR selected; original EdgeTTS and GenericGPTLLM preserved")


def status(path):
    contents = Path(path).read_text()
    print("A06_STATUS: VoskASR selected=" +
          ("yes" if contents.count(ASR_AFTER) == 1 else "no"))
    print("A06_STATUS: EdgeTTS selected=" +
          ("yes" if contents.count("  TTS: EdgeTTS\n") == 1 else "no"))
    print("A06_STATUS: generic GPT selected=" +
          ("yes" if contents.count("  LLM: GenericGPTLLM\n") == 1 else "no"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["apply", "status"])
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        (apply if args.mode == "apply" else status)(args.config)
    except (OSError, ValueError):
        raise SystemExit("A06_BLOCKED: A05/A04 stable config baseline differs or file cannot be written; no values printed") from None
