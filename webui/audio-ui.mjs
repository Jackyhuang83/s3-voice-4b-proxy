/* P2-1 source prototype: browser WSS/XiaoZhi Hello, AudioWorklet mic,
 * official 16k mono Opus codec. P2-2 owns long-running jitter/tail tests.
 * Never stores secrets, never uses device identity or paid realtime API.
 */
import { createXiaozhiCodec } from "./audio-opus.mjs";
const button = document.getElementById("voiceButton");
const statusText = document.getElementById("voiceStatus");
const logout = document.getElementById("logoutBtn");
const voiceMetrics = (() => {
  const existing = document.getElementById("voiceMetrics");
  if (existing) return existing;
  const form = document.getElementById("chatForm");
  if (!form) return null;
  // Keep the live P1 HTML untouched. This is a separate, persistent display
  // inside the composer; voiceStatus remains reserved for state transitions.
  const node = document.createElement("div");
  node.id = "voiceMetrics";
  node.className = "voice-metrics";
  node.hidden = true;
  node.setAttribute("aria-live", "off");
  form.appendChild(node);
  return node;
})();
let current = null;

function showMetrics(state, phase) {
  if (!voiceMetrics || !state) return;
  voiceMetrics.hidden = false;
  voiceMetrics.textContent = phase + " · 已发送 " + state.sent +
    " 帧 · 输入峰值 " + state.inputPeak + "%" +
    (state.received ? " · 收到音频 " + state.received + " 帧" : "");
}

// Keep SVG microphone controls intact while updating accessible state.
function setVoiceButton(label, pressed) {
  button?.setAttribute("aria-label", label);
  button?.setAttribute("aria-pressed", String(pressed));
  if (button && !button.querySelector("svg")) button.textContent = label;
}

function status(message) { if (statusText) statusText.textContent = message; }
// "AI 思考中" is a user-facing waiting state after the server returns STT.
// It includes model inference, server queueing and TTS preparation; the
// browser cannot prove that an LLM is executing at every instant.
function stopThinking(state) {
  if (state.thinkingTimer !== null) clearInterval(state.thinkingTimer);
  state.thinkingTimer = null;
}
function startThinking(state) {
  stopThinking(state);
  state.thinkingStartedAt = performance.now();
  const refresh = () => {
    if (state.cancelled || current !== state || !state.ready) return;
    const elapsed = Math.floor(
      Math.max(0, performance.now() - state.thinkingStartedAt) / 1000
    );
    showMetrics(state, "AI 思考中 · 已等待 " + elapsed + " 秒");
    status("AI 思考中 · 已等待 " + elapsed + " 秒（含服务器处理与语音准备）");
  };
  refresh();
  state.thinkingTimer = setInterval(refresh, 1000);
}
// Local-only microphone diagnostic. No speech content, IDs or secrets are logged.
function inputLevel(frame) {
  if (!(frame instanceof Int16Array) || !frame.length) return 0;
  let power = 0;
  for (const sample of frame) power += (sample / 32768) ** 2;
  return Math.round(100 * Math.sqrt(power / frame.length));
}
function audioStartupError(error) {
  if (error?.message === "AUDIO_CONTEXT_SUSPENDED") return "音频上下文未启动";
  const name = error?.name || "UnknownError";
  if (name === "NotAllowedError") return "Safari 麦克风权限被拒绝";
  if (name === "NotFoundError") return "没有可用麦克风";
  if (name === "NotReadableError") return "麦克风被占用";
  if (name === "NotSupportedError") return "不支持当前音频配置";
  return "启动阶段 " + String(name).slice(0,36);
}
function send(ws, message) {
  if (ws.readyState !== WebSocket.OPEN) return false;
  ws.send(JSON.stringify(message));
  return true;
}

// AudioBufferSourceNode 'ended' is the browser's playback-completion signal.
// A tts.stop message only means the upstream finished streaming; it is NOT
// proof the speaker has played all queued samples.
function resumeAfterAudioTail(state) {
  if (!state.ttsStopped || state.sources.size !== 0 || state.cancelled ||
      current !== state || !state.ready) return;
  clearTimeout(state.resumeTimer);
  state.resumeTimer = setTimeout(() => {
    state.resumeTimer = null;
    if (state.cancelled || current !== state || !state.ready ||
        !state.ttsStopped || state.sources.size !== 0 ||
        state.ws?.readyState !== WebSocket.OPEN) return;
    state.speaking = false;
    state.ttsStopped = false;
    state.processor?.port.postMessage({type:"start"});
    showMetrics(state, "正在听");
    status("可继续说话｜上一轮TTS首帧 " +
           (state.firstAudioMs === null ? "未收到" :
            (state.firstAudioMs / 1000).toFixed(1) + "s") +
           "｜音频 " + state.audioPacketsInTurn + " 帧");
  }, 80);
}

async function openVoice() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia ||
      !window.AudioWorkletNode) throw new Error("需要 Safari 的 HTTPS 麦克风权限");
  if (document.getElementById("chatView").hidden) throw new Error("请先登录");
  const state = {
    ws: null, codec: null, ctx: null, stream: null, source: null,
    processor: null, quiet: null, playbackAt: 0, ready: false, cancelled: false,
    sent: 0, received: 0, underrun: 0, ttsStopped: false,
    speaking: false, sources: new Set(), helloTimer: null, resumeTimer: null,
    inputTimer: null, lastMeterMs: 0, inputPeak: 0, stage: "permission",
    lastVoiceAt: null, lastSttAt: null, asrWaitMs: null,
    ttsStartAt: null, firstAudioMs: null, audioPacketsInTurn: 0,
    thinkingTimer: null, thinkingStartedAt: null
  };
  current = state;
  showMetrics(state, "麦克风连接中");
  try {
    // A user click started this call; AudioContext and getUserMedia are never
    // initialized on page load or from a background timer.
    const stream = navigator.mediaDevices.getUserMedia({
      audio: {echoCancellation:true,noiseSuppression:true,channelCount:1}
    });
    // Worklet already converts the native browser rate to 16k.
    // Resume inside the user's original tap, before async WASM loading.
    state.ctx = new AudioContext({latencyHint:"interactive"});
    const resumePromise = state.ctx.resume();
    state.stream = await stream;
    if (state.cancelled) {
      state.stream.getTracks().forEach(track=>track.stop());
      return;
    }
    state.stage = "opus";
    status("麦克风授权成功，正在初始化 Opus…");
    state.codec = await createXiaozhiCodec();
    if (state.cancelled) {
      state.codec.free();
      state.stream.getTracks().forEach(track=>track.stop());
      return;
    }
    state.stream.getAudioTracks().forEach(track=>{
      track.addEventListener("ended",()=>{status("麦克风已关闭");stopVoice(state);},{once:true});
    });
    state.stage = "audio";
    await resumePromise;
    if (state.cancelled) return;
    if (state.ctx.state === "suspended") throw new Error("AUDIO_CONTEXT_SUSPENDED");
    status("正在启动录音处理器…");
    await state.ctx.audioWorklet.addModule("/webui/audio-worklet.js");
    // Safari tab backgrounding or logout during Worklet loading must not
    // create an orphan microphone processor or a new WebSocket afterwards.
    if (state.cancelled) return;
    state.processor = new AudioWorkletNode(state.ctx,"s3-voice-mic");
    state.processor.port.onmessage = (event) => {
      if (state.cancelled || !state.ready || state.speaking || event.data?.type !== "frame") return;
      if (state.ws?.readyState !== WebSocket.OPEN) return;
      const level = inputLevel(event.data.data);
      state.inputPeak = Math.max(state.inputPeak, level);
      // Last significant input is a coarse proxy for voice-end time.
      // Do not store audio samples or transcripts in diagnostics.
      if (level >= 1) state.lastVoiceAt = performance.now();
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
        const now = Date.now();
        if (now - state.lastMeterMs >= 1200) {
          state.lastMeterMs = now;
          if (state.thinkingTimer === null) showMetrics(state, "正在听");
        }
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

    state.stage = "websocket";
    status("麦克风就绪，正在连接语音服务器…");
    state.ws = new WebSocket("wss://" + location.host + "/webui/ws");
    state.ws.binaryType = "arraybuffer";
    state.ws.onopen = () => {
      send(state.ws, {
        type:"hello",version:1,transport:"websocket",
        features:{mcp:false},
        audio_params:{format:"opus",sample_rate:16000,channels:1,frame_duration:60}
      });
      state.helloTimer = setTimeout(() => {
        if (!state.cancelled && !state.ready) {
          status("WebSocket 已连接，但未收到小智 Hello");
          stopVoice(state);
        }
      },12000);
    };
    state.ws.onmessage = (event) => {
      if (state.cancelled) return;
      if (event.data instanceof ArrayBuffer) {
        try {
          if (state.ttsStartAt !== null && state.firstAudioMs === null) {
            state.firstAudioMs = performance.now() - state.ttsStartAt;
            showMetrics(state, "AI 语音播放中（麦克风暂停）");
            status("AI 语音已到达，正在播放");
          }
          state.audioPacketsInTurn++;
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
          node.onended = () => {
            state.sources.delete(node);
            resumeAfterAudioTail(state);
          };
          state.sources.add(node);
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
        clearTimeout(state.helloTimer);
        state.helloTimer = null;
        state.ready = true;
        send(state.ws,{type:"listen",state:"start",mode:"auto",session_id:message.session_id});
        state.processor.port.postMessage({type:"start"});
        state.stage = "streaming";
        state.inputTimer = setTimeout(() => {
          if (!state.cancelled && state.ready && state.sent === 0)
            status("已建立语音会话，但麦克风没有输出音频帧");
        },4500);
        showMetrics(state, "正在听");
        status("正在听，请说话（检测音量）");
      } else if (message.type === "stt" && typeof message.text === "string") {
        state.lastSttAt = performance.now();
        state.asrWaitMs = state.lastVoiceAt === null ? null :
          Math.max(0, state.lastSttAt - state.lastVoiceAt);
        startThinking(state);
      } else if (message.type === "tts") {
        if (message.state === "start") {
          stopThinking(state);
          state.ttsStopped = false;
          state.speaking = true;
          state.ttsStartAt = performance.now();
          state.firstAudioMs = null;
          state.audioPacketsInTurn = 0;
          clearTimeout(state.resumeTimer);
          state.resumeTimer = null;
          // XiaoZhi listening -> speaking: do not feed AI playback into ASR.
          state.processor?.port.postMessage({type:"stop"});
          const sttToTts = state.lastSttAt === null ? null :
            Math.max(0, state.ttsStartAt - state.lastSttAt);
          showMetrics(state, "AI 正在准备语音（麦克风暂停）");
          status("AI 正在准备语音｜识别→TTS启动 " +
                 (sttToTts === null ? "未知" : (sttToTts / 1000).toFixed(1) + "s"));
        }
        if (message.state === "stop") {
          state.ttsStopped = true;
          const ttsFirst = state.firstAudioMs === null ? "未收到音频帧" :
            (state.firstAudioMs / 1000).toFixed(1) + "s";
          showMetrics(state, "正在播放尾音");
          status("TTS首个音频帧 " + ttsFirst +
                 "｜收到 " + state.audioPacketsInTurn + " 帧｜播放尾音中");
          // Wait for the *actual* last browser audio source's onended.
          // Using AudioContext.currentTime alone can reopen the microphone
          // before Safari's queued output has finished rendering.
          resumeAfterAudioTail(state);
        }
      }
    };
    state.ws.onerror = () => { status("WebSocket 连接异常（请检查登录或路由）"); };
    state.ws.onclose = () => {
      if (state.cancelled) return;
      status("语音连接断开");
      stopVoice(state);
    };
  } catch (error) {
    const step = state.stage;
    stopVoice(state);
    throw new Error(step + ": " + audioStartupError(error));
  }
}

function stopVoice(state = current) {
  if (!state || state.cancelled) return;
  state.cancelled = true;
  state.ready = false;
  clearTimeout(state.helloTimer);
  clearTimeout(state.resumeTimer);
  clearTimeout(state.inputTimer);
  stopThinking(state);
  state.helloTimer = null;
  state.resumeTimer = null;
  try { state.processor?.port.postMessage({type:"stop"}); } catch {}
  // Stop pending TTS audio when user explicitly ends the voice session.
  for (const node of state.sources) {
    try { node.stop(); } catch {}
  }
  state.sources.clear();
  try { state.processor?.disconnect(); } catch {}
  try { state.source?.disconnect(); } catch {}
  try { state.quiet?.disconnect(); } catch {}
  try { state.stream?.getTracks().forEach(t=>t.stop()); } catch {}
  try { state.ws?.close(1000,"stop"); } catch {}
  try { state.codec?.free(); } catch {}
  if (state.ctx) state.ctx.close().catch(()=>{});
  if (current === state) {
    showMetrics(state, "语音已停止");
    current = null;
    setVoiceButton("开始语音", false);
  }
}

button?.addEventListener("click",async()=>{
  if(current) {
    stopVoice();
    status("已停止语音");
    return;
  }
  button.disabled = true;
  setVoiceButton("连接中…", false);
  status("初始化麦克风和 Opus…");
  try {
    await openVoice();
    if (current && !current.cancelled) {
      setVoiceButton("停止语音", true);
    } else {
      setVoiceButton("开始语音", false);
    }
  } catch (error) {
    status("语音启动失败：" + String(error?.message || "UnknownError").slice(0,96));
    stopVoice();
  } finally {
    button.disabled = false;
  }
});
logout?.addEventListener("click",()=>{ stopVoice();status("已退出语音"); });
document.addEventListener("visibilitychange",()=>{
  if(document.hidden && current){stopVoice();status("已在切换后台时停止麦克风");}
});
