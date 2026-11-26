/* Dedicated 16 kHz mono AudioWorklet processor, no dependencies/CDN.
 * Must be loaded only from HTTPS + user microphone permission.
 * Streams exact 960-sample/60-ms PCM frames; main thread encodes raw Opus.
 */
class S3VoiceMicProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.running = false;
    this.frame = new Int16Array(960);
    this.used = 0;
    this.last = 0;
    this.sourceCount = 0;
    this.nextOutput = 0;
    this.interval = sampleRate / 16000;
    this.port.onmessage = (event) => {
      if (event.data?.type === "start") this.running = true;
      if (event.data?.type === "stop") {
        this.running = false;
        if (this.used) {
          this.frame.fill(0, this.used);
          this.port.postMessage({type:"frame", data:this.frame.slice()});
          this.used = 0;
        }
      }
    };
  }
  process(inputs, outputs) {
    const channels = outputs[0] || [];
    for (const channel of channels) channel.fill(0);
    if (!this.running) return true;
    const input = inputs[0]?.[0];
    if (!input) return true;
    for (const current of input) {
      const t = this.sourceCount++;
      while (this.nextOutput <= t) {
        const alpha = t === 0 ? 1 : Math.max(0, Math.min(1, this.nextOutput-(t-1)));
        const value = t === 0 ? current : this.last*(1-alpha)+current*alpha;
        this.frame[this.used++] = Math.max(-32768,Math.min(32767,Math.round(value*32767)));
        this.nextOutput += this.interval;
        if (this.used === 960) {
          this.port.postMessage({type:"frame",data:this.frame.slice()});
          this.used = 0;
        }
      }
      this.last = current;
    }
    return true;
  }
}
registerProcessor("s3-voice-mic",S3VoiceMicProcessor);
