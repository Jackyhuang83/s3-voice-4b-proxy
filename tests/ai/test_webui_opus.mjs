// Node 22+ test: ACTUAL libopus-wasm 0.4.1 WASM, no fake codec.
import assert from 'node:assert/strict';
import { createXiaozhiCodec, FrameAccumulator, StreamingResampler,
         AUDIO_RATE, AUDIO_SAMPLES, AUDIO_FRAME_MS } from '../../webui/audio-opus.mjs';
import { getPacketInfo } from '../../webui/vendor/libopus/dist/index.js';

assert.equal(AUDIO_RATE,16000);
assert.equal(AUDIO_SAMPLES,960);
assert.equal(AUDIO_FRAME_MS,60);

const sampleCount=48000;
const input=new Float32Array(sampleCount);
for(let i=0;i<sampleCount;i++) input[i]=Math.sin(i*2*Math.PI*220/48000)*0.2;
const mono=new StreamingResampler(48000);
const fromOne=mono.push(input);
assert.equal(fromOne.length,16000);
const fragmented=new StreamingResampler(48000);
const chunks=[];
for(let start=0;start<sampleCount;start+=127){
  chunks.push(fragmented.push(input.subarray(start,Math.min(start+127,sampleCount))));
}
const result=new Int16Array(chunks.reduce((n,a)=>n+a.length,0));
let offset=0;
for(const a of chunks){result.set(a,offset);offset+=a.length;}
assert.deepEqual(result,fromOne,"split callbacks must not change sample sequence");

for(const rate of [16000,44100,48000]){
  const resampler=new StreamingResampler(rate);
  const frame=new Float32Array(rate).fill(0.2);
  assert.equal(resampler.push(frame).length,16000);
}
assert.throws(()=>new StreamingResampler(4000),RangeError);
assert.throws(()=>new FrameAccumulator(0),RangeError);
const collector=new FrameAccumulator();
const frames=collector.push(fromOne);
assert.equal(frames.length,16);
assert.equal(collector.used,640);
const tail=collector.padTail();
assert.equal(tail.length,960);
assert.equal(collector.used,0);
assert.throws(()=>collector.push(new Float32Array(300)),TypeError);

const encoderDecoder=await createXiaozhiCodec();
let encodedCount=0;
try {
  const packetLengths=[];
  for(let i=0;i<30;i++){
    const pcm=new Int16Array(AUDIO_SAMPLES);
    for(let j=0;j<pcm.length;j++)
      pcm[j]=Math.round(Math.sin((i*AUDIO_SAMPLES+j)*2*Math.PI*220/AUDIO_RATE)*5000);
    const packet=encoderDecoder.encode(pcm);
    assert.ok(packet instanceof Uint8Array);
    assert.ok(packet.byteLength>0 && packet.byteLength<4000);
    const info=await getPacketInfo(packet,{sampleRate:AUDIO_RATE});
    assert.equal(info.durationMs,60,"XiaoZhi requires raw 60ms frames");
    assert.equal(info.channels,1);
    const decoded=encoderDecoder.decode(packet);
    const decodedFloat=encoderDecoder.decodeFloat(packet);
    assert.equal(decoded.length,AUDIO_SAMPLES);
    assert.equal(decodedFloat.length,AUDIO_SAMPLES);
    assert.ok(decoded.some(x=>x!==0));
    packetLengths.push(packet.length);
    encodedCount++;
  }
  assert.throws(()=>encoderDecoder.encode(new Int16Array(320)),RangeError);
  assert.throws(()=>encoderDecoder.decode(new Uint8Array()),RangeError);
}finally{
  encoderDecoder.free();
  encoderDecoder.free();
}
assert.throws(()=>encoderDecoder.encode(new Int16Array(AUDIO_SAMPLES)),/released/);
console.log('WEBUI_P2_OPUS_PASS: 30 real 16k mono 60ms Opus roundtrips; 44.1/48k resampling; stream chunk invariants; free');
