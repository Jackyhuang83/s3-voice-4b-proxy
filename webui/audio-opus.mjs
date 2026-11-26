/**
 * P2-1 core only: 16 kHz / mono / 60 ms RAW Opus frames for XiaoZhi v0.9.8.
 * Opus implementation reused unchanged: libopus-wasm@0.4.1 (MIT/BSD).
 * No Ogg/WebM framing; no microphone access or external network in this file.
 * A later module owns AudioWorklet capture, WebSocket session and playback.
 */
import { createEncoder, createDecoder, Application } from "./vendor/libopus/dist/index.js";

export const AUDIO_RATE = 16000;
export const AUDIO_CHANNELS = 1;
export const AUDIO_FRAME_MS = 60;
export const AUDIO_SAMPLES = 960;

export class FrameAccumulator {
  constructor(frameSize = AUDIO_SAMPLES) {
    if (!Number.isInteger(frameSize) || frameSize <= 0) throw new RangeError("invalid frame size");
    this.frameSize = frameSize;
    this.samples = new Int16Array(frameSize);
    this.used = 0;
  }

  push(samples) {
    if (!(samples instanceof Int16Array)) throw new TypeError("Int16Array PCM required");
    const frames = [];
    let offset = 0;
    while (offset < samples.length) {
      const take = Math.min(this.frameSize - this.used, samples.length - offset);
      this.samples.set(samples.subarray(offset, offset + take), this.used);
      this.used += take;
      offset += take;
      if (this.used === this.frameSize) {
        frames.push(this.samples.slice());
        this.used = 0;
      }
    }
    return frames;
  }

  discard() {
    this.used = 0;
    this.samples.fill(0);
  }

  // Padding is appropriate only at a terminal audio frame; never fabricate
  // regular 60 ms frames from an incomplete stream.
  padTail() {
    if (!this.used) return null;
    this.samples.fill(0, this.used);
    const tail = this.samples.slice();
    this.used = 0;
    return tail;
  }
}

/**
 * Stateful, streaming linear interpolator to 16 kHz.
 * No assumption that Safari honours AudioContext({sampleRate:16000}).
 * Small low-complexity first cut; antialias/quality testing remains P2-2.
 */
export class StreamingResampler {
  constructor(inputRate, outputRate = AUDIO_RATE) {
    if (!Number.isFinite(inputRate) || inputRate < 8000 || inputRate > 192000 ||
        !Number.isFinite(outputRate) || outputRate <= 0 || outputRate > inputRate) {
      throw new RangeError("unsupported sample rate");
    }
    this.inputRate = inputRate;
    this.outputRate = outputRate;
    this.interval = inputRate / outputRate;
    this.lastSample = 0;
    this.inputIndex = 0;
    this.nextOutputAt = 0;
  }

  push(floatSamples) {
    if (!(floatSamples instanceof Float32Array)) throw new TypeError("Float32Array required");
    const estimated = Math.ceil(floatSamples.length * this.outputRate / this.inputRate) + 2;
    const out = new Int16Array(estimated);
    let count = 0;
    for (const current of floatSamples) {
      const t = this.inputIndex++;
      if (!Number.isFinite(current)) throw new RangeError("invalid PCM");
      while (this.nextOutputAt <= t) {
        const alpha = t === 0 ? 1 : Math.min(1, Math.max(0, this.nextOutputAt - (t - 1)));
        const value = t === 0 ? current : this.lastSample * (1 - alpha) + current * alpha;
        out[count++] = Math.max(-32768, Math.min(32767, Math.round(value * 32767)));
        this.nextOutputAt += this.interval;
      }
      this.lastSample = current;
    }
    return out.subarray(0, count);
  }
}

export async function createXiaozhiCodec() {
  const encoder = await createEncoder({
    sampleRate: AUDIO_RATE,
    channels: AUDIO_CHANNELS,
    frameSize: AUDIO_SAMPLES,
    application: Application.Voip,
    bitrate: 16000,
    complexity: 5,
  });
  let decoder;
  try {
    decoder = await createDecoder({
      sampleRate: AUDIO_RATE,
      channels: AUDIO_CHANNELS,
      maxFrameSize: AUDIO_SAMPLES * 2,
    });
  } catch (err) {
    encoder.free();
    throw err;
  }
  let released = false;
  const ensure = () => {
    if (released) throw new Error("codec already released");
  };
  return {
    encode(frame) {
      ensure();
      if (!(frame instanceof Int16Array) || frame.length !== AUDIO_SAMPLES) {
        throw new RangeError("exact 960-sample Int16 PCM frame required");
      }
      return encoder.encode(frame);
    },
    decode(packet) {
      ensure();
      if (!(packet instanceof Uint8Array) || !packet.length || packet.length > 4000) {
        throw new RangeError("invalid raw Opus packet");
      }
      return decoder.decode(packet);
    },
    decodeFloat(packet) {
      ensure();
      if (!(packet instanceof Uint8Array) || !packet.length || packet.length > 4000) {
        throw new RangeError("invalid raw Opus packet");
      }
      return decoder.decodeFloat(packet);
    },
    free() {
      if (released) return;
      released = true;
      encoder.free();
      decoder.free();
    }
  };
}
