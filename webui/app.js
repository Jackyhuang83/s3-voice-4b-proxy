"use strict";
(() => {
  const el = (id) => document.getElementById(id);
  const history = [];
  let busy = false;
  let noticeTimer;
  let currentAbort = null;
  const originAPI = "/webui/api/";

  function notify(message) {
    el("appNotice").textContent = message;
    el("appNotice").classList.add("visible");
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => el("appNotice").classList.remove("visible"), 4500);
  }

  function setLogin(authorized) {
    el("loginView").hidden = authorized;
    el("chatView").hidden = !authorized;
    el("logoutBtn").hidden = !authorized;
    el("connectionStatus").textContent = authorized ? "已安全连接" : "未连接";
    if (!authorized) {
      history.length = 0;
      el("messages").replaceChildren(el("welcome"));
      el("modelSelect").replaceChildren();
    }
  }

  async function jsonApi(path, options = {}) {
    const response = await fetch(originAPI + path, {
      credentials: "same-origin",
      cache: "no-store",
      ...options
    });
    let data;
    try { data = await response.json(); } catch { data = {}; }
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        if (path !== "login") setLogin(false);
      }
      throw new Error(data.error || ("HTTP " + response.status));
    }
    return data;
  }

  function addMessage(role, value) {
    el("welcome").remove();
    const wrapper = document.createElement("div");
    wrapper.className = "message " + role;
    const label = document.createElement("span");
    label.className = "role";
    label.textContent = role === "user" ? "你" : "S3-Voice";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = value;
    wrapper.append(label, bubble);
    el("messages").appendChild(wrapper);
    scrollToBottom();
    return bubble;
  }

  function scrollToBottom() {
    const view = el("messages");
    view.scrollTop = view.scrollHeight;
  }

  function resetChat() {
    if (currentAbort) currentAbort.abort();
    currentAbort = null;
    history.length = 0;
    el("messages").replaceChildren(el("welcome"));
    busy = false;
    el("sendBtn").disabled = el("modelSelect").options.length === 0;
    el("messageInput").disabled = false;
    el("messageInput").focus();
  }

  async function fetchModels() {
    const data = await jsonApi("models");
    const select = el("modelSelect");
    select.replaceChildren();
    for (const model of data.models || []) {
      if (!model || typeof model.id !== "string" || typeof model.label !== "string") continue;
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = model.label;
      select.appendChild(option);
    }
    el("sendBtn").disabled = select.options.length === 0;
    if (!select.options.length) notify("服务器尚未配置文字模型，请先设置 GPT / DeepSeek。");
  }

  async function readStream(response, bubble) {
    if (!response.body) throw new Error("当前浏览器不支持流式聊天");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let received = "";
    let answer = "";
    let completed = false;
    const process = (line) => {
      if (!line.startsWith("data: ")) return;
      const raw = line.slice(6);
      if (raw === "[DONE]") { completed = true; return; }
      let part;
      try { part = JSON.parse(raw); } catch { throw new Error("服务器返回了无效的响应数据"); }
      if (part.error) throw new Error("模型服务不可用，请稍后重试");
      if (typeof part.delta === "string") {
        answer += part.delta;
        bubble.textContent = answer;
        scrollToBottom();
      }
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        received += decoder.decode(value, {stream:true});
        let pos;
        while ((pos = received.indexOf("\n")) !== -1) {
          const line = received.slice(0, pos).trimEnd();
          received = received.slice(pos + 1);
          process(line);
        }
      }
      if (received) process(received.trimEnd());
      if (!completed || !answer.trim()) throw new Error("模型回复中断或为空");
      return answer;
    } finally {
      reader.releaseLock();
    }
  }

  async function submitChat(message) {
    if (busy || !message || !el("modelSelect").value) return;
    busy = true;
    el("sendBtn").disabled = true;
    el("messageInput").disabled = true;
    addMessage("user", message);
    const assistant = addMessage("assistant", "正在思考…");
    const turn = {role:"user", content:message};
    const toSend = [...history.slice(-18), turn];
    const controller = new AbortController();
    currentAbort = controller;

    try {
      const response = await fetch(originAPI + "chat", {
        method: "POST", credentials: "same-origin", cache: "no-store",
        headers: {"Content-Type":"application/json", "Accept":"text/event-stream"},
        body: JSON.stringify({ model: el("modelSelect").value, messages: toSend }),
        signal: controller.signal
      });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) setLogin(false);
        throw new Error("HTTP " + response.status);
      }
      const answer = await readStream(response, assistant);
      history.push(turn, {role:"assistant", content:answer});
      if (history.length > 20) history.splice(0, history.length - 20);
    } catch (err) {
      if (err.name === "AbortError") assistant.textContent = "本次回答已取消";
      else {
        assistant.textContent = "回复失败，请重试。";
        notify("文字聊天失败：" + (err.message || "网络错误"));
      }
    } finally {
      if (currentAbort === controller) currentAbort = null;
      busy = false;
      el("sendBtn").disabled = !el("modelSelect").value;
      el("messageInput").disabled = false;
      el("messageInput").focus();
    }
  }

  el("loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const password = el("ownerPassword").value;
    el("loginBtn").disabled = true;
    el("loginError").textContent = "";
    try {
      await jsonApi("login", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({secret:password})
      });
      el("ownerPassword").value = "";
      setLogin(true);
      await fetchModels();
    } catch {
      el("loginError").textContent = "登录失败，请核对密码或稍后重试。";
    } finally {
      el("loginBtn").disabled = false;
    }
  });

  el("logoutBtn").addEventListener("click", async () => {
    if (currentAbort) currentAbort.abort();
    try { await jsonApi("logout",{method:"POST"}); } catch {}
    setLogin(false);
  });

  el("newChatBtn").addEventListener("click", resetChat);
  el("modelSelect").addEventListener("change", () => {
    resetChat();
    notify("已切换模型，开始新对话。");
  });
  el("chatForm").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = el("messageInput");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.style.height = "";
    submitChat(text);
  });
  el("messageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      el("chatForm").requestSubmit();
    }
  });
  el("messageInput").addEventListener("input", () => {
    const input = el("messageInput");
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 145) + "px";
  });

  async function init() {
    try {
      const session = await jsonApi("session");
      setLogin(session.authenticated === true);
      if (session.authenticated) await fetchModels();
    } catch {
      setLogin(false);
      notify("无法连接 WebUI 服务，请检查网络。");
    }
  }
  init();
})();
