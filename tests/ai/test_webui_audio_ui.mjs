// Headless browser API contract tests: real production audio-ui.mjs, mocked I/O.
// No microphone, network, API tokens, or codec vendor is used by this test.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

const elements = {};
const voiceMetricsChildren = [];
const chatForm = {
  appendChild(node) {voiceMetricsChildren.push(node);elements[node.id] = node;}
};
const voiceButton = {
  textContent: "SVG_ICON_PRESERVED", disabled: false,
  attributes: {}, listeners: {},
  querySelector(selector) { return selector === "svg" ? {} : null; },
  setAttribute(name, value) { this.attributes[name] = value; },
  addEventListener(name, handler) { this.listeners[name] = handler; }
};
const logout = {listeners: {}, addEventListener(name, cb) { this.listeners[name] = cb; }};
const status = {textContent: ""};
Object.assign(elements, {
  voiceButton, logoutBtn:logout, voiceStatus:status, chatView:{hidden:false}, chatForm
});
Object.defineProperty(globalThis, "document", {configurable:true, value:{
  hidden:false, getElementById(id) {return elements[id];},
  createElement(tag) {
    assert.equal(tag,"div");
    return {id:"",className:"",hidden:false,textContent:"",
      setAttribute(){ }};
  },
  addEventListener() {}
}});
Object.defineProperty(globalThis, "location", {configurable:true, value:{host:"test.local"}});
Object.defineProperty(globalThis, "window", {configurable:true, value:{isSecureContext:true}});

let stoppedTracks = 0;
const track = {stop(){stoppedTracks++;}, addEventListener(){}};
Object.defineProperty(globalThis, "navigator", {configurable:true, value:{
  mediaDevices: {async getUserMedia() {
    return {getTracks:()=>[track], getAudioTracks:()=>[track]};
  }}
}});

const processors = [];
class Worklet {
  constructor(ctx, name) {
    assert.equal(name, "s3-voice-mic");
    this.port = {
      messages:[], onmessage:null,
      postMessage(message) {this.messages.push(message);}
    };
    processors.push(this);
  }
  connect() {}
  disconnect() {}
}
globalThis.AudioWorkletNode = Worklet;
window.AudioWorkletNode = Worklet;

const sounds = [];
let resumeCalls = 0;
let blockNextModule = false;
let releasePendingModule = null;
class AudioContextMock {
  constructor(options) {
    assert.equal(options.sampleRate, undefined, "browser native sample rate required");

    this.currentTime = 0;
    this.destination = {};
    this.audioWorklet = {addModule:async path=>{
      assert.equal(path,"/webui/audio-worklet.js");
      if (blockNextModule) await new Promise(resolve=>{releasePendingModule = resolve;});
    }};
  }
  async resume() {resumeCalls++;}
  createMediaStreamSource() {return {connect(){},disconnect(){}};}
  createGain() {return {gain:{value:1},connect(){},disconnect(){}};}
  createBuffer(channels,length,rate) {
    assert.equal(channels,1);
    return {duration:length/rate,getChannelData:()=>new Float32Array(length)};
  }
  createBufferSource() {
    const sound={buffer:null,onended:null,stopped:false,
      connect(){},start(){},stop(){this.stopped=true; if(this.onended)this.onended();}
    };
    sounds.push(sound);
    return sound;
  }
  async close() {}
}
globalThis.AudioContext = AudioContextMock;

const sockets = [];
class WebSocketMock {
  static OPEN = 1;
  constructor(url) {
    assert.equal(url,"wss://test.local/webui/ws");
    this.readyState = WebSocketMock.OPEN;
    this.sent = [];
    sockets.push(this);
  }
  send(data) {this.sent.push(data);}
  close() {this.readyState = 3; this.closed = true;}
}
globalThis.WebSocket = WebSocketMock;

const source = readFileSync("webui/audio-ui.mjs","utf8");
const originalImport = 'import { createXiaozhiCodec } from "./audio-opus.mjs";';
assert.equal(source.split(originalImport).length,2);
const sandboxed = source.replace(originalImport,
  'const createXiaozhiCodec = async () => ({' +
  'encode(frame){if(frame.length !== 960) throw new Error("frame"); return new Uint8Array([1,2]);},' +
  'decodeFloat(){return new Float32Array(960);},free(){}' +
  '});');
await import("data:text/javascript;base64,"+Buffer.from(sandboxed).toString("base64"));

assert.equal(voiceMetricsChildren.length,1, "one persistent meter beside composer");
assert.equal(typeof voiceButton.listeners.click, "function");
await voiceButton.listeners.click();
assert.equal(voiceButton.disabled,false);
assert.ok(resumeCalls >= 1, "AudioContext resume was not requested");
assert.equal(voiceButton.attributes["aria-label"],"停止语音");
assert.equal(voiceButton.textContent,"SVG_ICON_PRESERVED");
const ws = sockets.at(-1);
const port = processors.at(-1).port;
port.onmessage({data:{type:"frame",data:new Int16Array(960)}});
assert.equal(ws.sent.length,0,"audio must not stream before server hello");

ws.onopen();
assert.equal(JSON.parse(ws.sent[0]).type,"hello");
ws.onmessage({data:JSON.stringify({type:"hello",session_id:"mock-session"})});
assert.equal(JSON.parse(ws.sent[1]).type,"listen");
assert.equal(port.messages.at(-1).type,"start");
port.onmessage({data:{type:"frame",data:new Int16Array(960)}});
const initialCount = ws.sent.length;
assert.equal(initialCount,3);
assert.ok(ws.sent.at(-1) instanceof Uint8Array);
assert.equal(elements.voiceMetrics.hidden,false);
assert.match(elements.voiceMetrics.textContent,/正在听.*已发送 1 帧/);
assert.match(status.textContent,/已发送|已采集|正在听/, "local mic frame telemetry must be available");
ws.onmessage({data:JSON.stringify({type:"stt",text:"synthetic words never logged"})});
assert.match(status.textContent,/AI 思考中.*已等待 0 秒/, "explicit thinking indicator appears after STT");
assert.match(elements.voiceMetrics.textContent,/AI 思考中.*已等待 0 秒/, "thinking indicator is visible near mic");
await new Promise(resolve=>setTimeout(resolve,1100));
assert.match(status.textContent,/AI 思考中.*已等待 [1-9] 秒/,
  "thinking elapsed seconds update while server prepares a reply");
assert.ok(!status.textContent.includes("synthetic words"),
  "diagnostics must not display speech transcript");

ws.onmessage({data:JSON.stringify({type:"tts",state:"start"})});
assert.equal(port.messages.at(-1).type,"stop");
port.onmessage({data:{type:"frame",data:new Int16Array(960)}});
assert.equal(ws.sent.length,initialCount,"TTS must mute microphone to prevent echo");
assert.match(elements.voiceMetrics.textContent,/AI 正在准备语音.*麦克风暂停/,
  "TTS start clears thinking state and shows voice preparation");
ws.onmessage({data:new Uint8Array([1,2]).buffer});
assert.equal(sounds.length,1);
assert.match(status.textContent,/AI 语音已到达，正在播放/,
  "first Opus packet transitions from preparing to playback");
assert.equal(ws.sent.length,initialCount, "TTS audio must not enable microphone");
ws.onmessage({data:JSON.stringify({type:"tts",state:"stop"})});
// The WebSocket 'stop' is upstream completion, not speaker output completion.
// Microphone must remain muted until the real AudioBufferSourceNode ended.
await new Promise(resolve=>setTimeout(resolve,190));
assert.equal(port.messages.at(-1).type,"stop",
  "must not resume while any browser audio source still playing");
assert.equal(sounds[0].stopped,false);
sounds[0].onended();
await new Promise(resolve=>setTimeout(resolve,130));
assert.equal(port.messages.at(-1).type,"start",
  "mic resumes only after onended and 80ms gap");
assert.match(status.textContent,/可继续说话.*上一轮TTS首帧.*音频 1 帧/,
  "TTS first audio and packet count must remain visible after playback");
port.onmessage({data:{type:"frame",data:new Int16Array(960)}});
assert.equal(ws.sent.length,initialCount+1,"mic must resume on the same session");

await voiceButton.listeners.click();
assert.match(elements.voiceMetrics.textContent,/语音已停止.*已发送/);
assert.equal(ws.closed,true);
assert.equal(sounds[0].stopped,false,
  "already finished audio must not be stopped again after onended");
assert.equal(voiceButton.attributes["aria-pressed"],"false");
assert.equal(voiceButton.textContent,"SVG_ICON_PRESERVED");
assert.ok(stoppedTracks>0);
const countAfterStop = ws.sent.length;
port.onmessage({data:{type:"frame",data:new Int16Array(960)}});
assert.equal(ws.sent.length,countAfterStop,"no audio after stop");

// Close while a TTS tail timer is pending: never resume an expired session.
await voiceButton.listeners.click();
const ws2=sockets.at(-1), port2=processors.at(-1).port;
ws2.onopen();
ws2.onmessage({data:JSON.stringify({type:"hello",session_id:"second"})});
ws2.onmessage({data:JSON.stringify({type:"tts",state:"start"})});
ws2.onmessage({data:new Uint8Array([1,2]).buffer});
ws2.onmessage({data:JSON.stringify({type:"tts",state:"stop"})});
const pendingSound=sounds.at(-1);
await voiceButton.listeners.click();
assert.equal(pendingSound.stopped,true,
  "manual stop must stop browser playback even when TTS tail is pending");
const countStop=port2.messages.length;
await new Promise(resolve=>setTimeout(resolve,360));
assert.equal(port2.messages.length,countStop,"old TTS tail must not restart mic");

// Logging out while Safari is loading an AudioWorklet must not open a
// new WebSocket after session cancellation (no orphan mic/session).
blockNextModule = true;
const connectionsBefore = sockets.length;
const pendingStart = voiceButton.listeners.click();
for (let i=0; !releasePendingModule && i<50; i++) {
  await new Promise(resolve=>setTimeout(resolve,2));
}
assert.equal(typeof releasePendingModule,"function");
logout.listeners.click();
releasePendingModule();
await pendingStart;
assert.equal(sockets.length,connectionsBefore,
  "cancellation during AudioWorklet load must not create a WebSocket");
assert.equal(voiceButton.textContent,"SVG_ICON_PRESERVED");

console.log("WEBUI_P2_AUDIO_UI_PASS: SVG retained, Hello and Opus mic flow, TTS mute/tail resume, stop, timers and async logout");
