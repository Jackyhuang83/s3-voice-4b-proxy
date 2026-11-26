/* P2-1 source prototype: browser WSS/XiaoZhi Hello, AudioWorklet mic,
 * official 16k mono Opus codec. P2-2 owns long-running jitter/tail tests.
 * Never stores secrets, never uses device identity or paid realtime API.
 */
import { createXiaozhiCodec } from "./audio-opus.mjs";
const button = document.getElementById("voiceButton");
const statusText = document.getElementById("voiceStatus");
const logout = document.getElementById("logoutBtn");
let current = null;

function status(message) { statusText.textContent = message; }
function send(ws, message) {
  if (ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(message));
  return true;
}

async function openVoice() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia ||
      !window.AudioWorkletNode) throw new Error("需要 Safari 的 HTTPS 麦克风权限");
  if (document.getElementById("chatView").hidden) throw new Error("请先登录");
  const state = {
    ws: null, codec: null, ctx: null, stream: null, source: null,
    processor: null, quiet: null, playbackAt: 0, ready: false, cancelled: false,
    sent: 0, received: 0, underrun: 0, ttsStopped: false
  };
  current = state;
  try {
    // A user click started this call; AudioContext and getUserMedia are never
    // initialized on page load or from a background timer.
    const stream = navigator.mediaDevices.getUserMedia({
      audio: {echoCancellation:true,noiseSuppression:true,channelCount:1}
    });
    state.ctx = new AudioContext({sampleRate:16000,latencyHint:"interactive"});
    state.codec = await createXiaozhiCodec();
    state.stream = await stream;
    if (state.cancelled) return;
    await state.ctx.resume();
    await state.ctx.audioWorklet.addModule("/webui/audio-worklet.js");
    state.processor = new AudioWorkletNode(state.ctx,"s3-voice-mic");
    state.processor.port.onmessage = (event) => {
      if (!state.ready || event.data?.type !== "frame") return;
      if (state.ws?.readyState !== WebSocket.OPEN) return;
      // Back-pressure: never grow an unbounded outbound audio backlog.
      if (state.ws.bufferedAmount > 65536) {
        state.underrun++;
        status("网络发送阻塞，已停止麦克风");
        stopVoice(state);
        return;
      }
      try {
        const opus = state.codec.encode(event.data.data);
        state.ws.send(opus);
        state.sent++;
      } catch {
        status("音频编码异常，已断开");
        stopVoice(state);
      }
    };
    state.source = state.ctx.createMediaStreamSource(state.stream);
    state.quiet = state.ctx.createGain();
    state.quiet.gain.value = 0;
    state.source.connect(state.processor);
    state.processor.connect(state.quiet);
    state.quiet.connect(state.ctx.destination);

    state.ws = new WebSocket("wss://" + location.host + "/webui/ws");
    state.ws.binaryType = "arraybuffer";
    let helloTimer = null;
    state.ws.onopen = () => {
      send(state.ws, {
        type:"hello",version:1,transport:"websocket",
        features:{mcp:false},
        audio_params:{format:"opus",sample_rate:16000,channels:1,frame_duration:60}
      });
      helloTimer = setTimeout(() => {
        if (!state.ready) { status("语音握手超时"); stopVoice(state); }
      },6000);
    };
    state.ws.onmessage = (event) => {
      if (state.cancelled) return;
      if (event.data instanceof ArrayBuffer) {
        try {
          const floatSamples = state.codec.decodeFloat(new Uint8Array(event.data));
          const ctx = state.ctx;
          const audio = ctx.createBuffer(1,floatSamples.length,16000);
          audio.getChannelData(0).set(floatSamples);
          const node = ctx.createBufferSource();
          node.buffer = audio;
          node.connect(ctx.destination);
          // Schedule small jitter prebuffer. Larger queue/tail behaviour is
          // measured in P2-2; no unconditional clear on normal tts.stop.
          const next = Math.max(ctx.currentTime + 0.12,state.playbackAt);
          if (next-ctx.currentTime > 2) {
            status("音频队列过长，已停止");
            stopVoice(state);
            return;
          }
          node.start(next);
          state.playbackAt = next + audio.duration;
          state.received++;
        } catch {
          status("语音解码异常");
          stopVoice(state);
        }
        return;
      }
      if (typeof event.data !== "string") return;
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === "hello" && typeof message.session_id === "string") {
        clearTimeout(helloTimer);
        state.ready = true;
        send(state.ws,{type:"listen",state:"start",mode:"auto",session_id:message.session_id});
        state.processor.port.postMessage({type:"start"});
        status("正在听，请说话");
      } else if (message.type === "stt" && typeof message.text === "string") {
        status("识别：" + message.text.slice(0,90));
      } else if (message.type === "tts") {
        if (message.state === "start") status("AI 正在回答…");
        if (message.state === "stop") {
          state.ttsStopped = true;
          status("AI 已发送回答，正在播放剩余音频");
        }
      }
    };
    state.ws.onerror = () => { status("语音连接异常"); };
    state.ws.onclose = () => {
      if (state.cancelled) return;
      status("语音连接断开");
      stopVoice(state);
    };
  } catch (error) {
    stopVoice(state);
    throw error;
  }
}

function stopVoice(state = current) {
  if (!state || state.cancelled) return;
  state.cancelled = true;
  state.ready = false;
  try { state.processor?.port.postMessage({type:"stop"}); } catch {}
  try { state.processor?.disconnect(); } catch {}
  try { state.source?.disconnect(); } catch {}
  try { state.quiet?.disconnect(); } catch {}
  try { state.stream?.getTracks().forEach(t=>t.stop()); } catch {}
  try { state.ws?.close(1000,"stop"); } catch {}
  try { state.codec?.free(); } catch {}
  if (state.ctx) state.ctx.close().catch(()=>{});
  if (current === state) current = null;
  button.textContent = "开始语音";
  button.setAttribute("aria-pressed","false");
}

button?.addEventListener("click",async()=>{
  if(current) {
    stopVoice();
    status("已停止语音");
    return;
  }
  button.disabled = true;
  button.textContent = "连接中…";
  status("初始化麦克风和 Opus…");
  try {
    await openVoice();
    button.textContent = "停止语音";
    button.setAttribute("aria-pressed","true");
  } catch {
    status("语音启动失败：检查 HTTPS、麦克风权限和服务器");
    stopVoice();
  } finally {
    button.disabled = false;
  }
});
logout?.addEventListener("click",()=>{ stopVoice();status("已退出语音"); });
document.addEventListener("visibilitychange",()=>{
  if(document.hidden && current){stopVoice();status("已在切换后台时停止麦克风");}
});
