// S3-Voice UI v2 behavioral contract. No browser/network/audio device/credentials.
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {runInNewContext} from "node:vm";

function element(tag = "div", id = "") {
  const node = {
    id, tag, value:"", textContent:"", hidden:false, disabled:false,
    children:[], listeners:{}, scrollTop:0, scrollHeight:100,
    clientHeight:100, style:{}, parentElement:null, isConnected:true,
    classList:{add(){},remove(){}},
    addEventListener(type, cb) { this.listeners[type] = cb; },
    showModal() { this.open = true; },
    close() { this.open = false; this.listeners.close?.(); },
    getBoundingClientRect() { return {left:0,right:304,top:0,bottom:800}; },
    setAttribute(name, value) { (this.attributes ??= {})[name] = value; },
    append(...children) { for (const child of children) this.appendChild(child); },
    appendChild(child) {
      this.children.push(child);
      child.parentElement = this;
      if (this.tag === "select" && !this.value) this.value = child.value;
    },
    replaceChildren(...children) {
      this.children = [];
      if (this.tag === "select") this.value = "";
      this.append(...children);
    },
    remove() {
      this.isConnected = false;
      if (this.parentElement) {
        this.parentElement.children =
          this.parentElement.children.filter(child => child !== this);
      }
    },
    focus() { this.focused = true; },
    requestSubmit() {
      this.submitCount = (this.submitCount || 0) + 1;
      this.listeners.submit?.({preventDefault(){}});
    }
  };
  Object.defineProperty(node, "options", {get() {
    return this.tag === "select" ? this.children : [];
  }});
  return node;
}

const ids = [
  "connectionStatus","logoutBtn","loginView","loginForm",
  "ownerPassword","loginBtn","loginError","chatView",
  "modelSelect","newChatBtn","messages","welcome","chatForm",
  "messageInput","voiceButton","sendBtn","voiceStatus","appNotice",
  "sidebarDialog","sidebarToggle","sidebarClose"
];
const elements = Object.fromEntries(ids.map(id => [id, element("div", id)]));
elements.modelSelect.tag = "select";
elements.chatForm.tag = "form";
elements.messages.appendChild(elements.welcome);

let coarse = false;
let copied = "";
const calls = [];
const answer = new TextEncoder().encode('data: {"delta":"测试回复"}\n\ndata: [DONE]\n\n');

async function fakeFetch(path, options = {}) {
  const method = options.method || "GET";
  calls.push({path, method, options});
  if (path === "/webui/api/session") {
    return {ok:true,status:200,json:async()=>({authenticated:true})};
  }
  if (path === "/webui/api/models") {
    return {ok:true,status:200,json:async()=>({
      models:[{id:"GPT",label:"GPT"}]
    })};
  }
  if (path === "/webui/api/chat") {
    let count = 0;
    return {ok:true,status:200,body:{getReader() {
      return {
        async read() {
          count++;
          return count === 1
            ? {done:false,value:answer}
            : {done:true,value:undefined};
        },
        releaseLock(){}
      };
    }}};
  }
  if (path === "/webui/api/logout") {
    return {ok:true,status:200,json:async()=>({})};
  }
  throw new Error("Unexpected API " + path);
}

const windowMock = {
  matchMedia:() => ({matches:coarse})
};
const documentListeners = {};
const context = {
  document: {
    addEventListener(type, cb) { documentListeners[type] = cb; },
    getElementById(id) {
      assert.ok(elements[id], "known DOM ID " + id);
      return elements[id];
    },
    createElement(tag) { return element(tag); }
  },
  window:windowMock,
  navigator:{
    clipboard:{async writeText(text) {copied = text;}}
  },
  fetch:fakeFetch,
  AbortController,
  TextDecoder,
  setTimeout:()=>1,
  clearTimeout:()=>{},
  console
};

runInNewContext(readFileSync("webui/app.js","utf8"),context);
async function flush() {
  for (let i=0;i<8;i++) await new Promise(resolve=>setImmediate(resolve));
}
await flush();

assert.equal(elements.loginView.hidden,true);
assert.equal(elements.chatView.hidden,false);
assert.equal(elements.modelSelect.options.length,1);
assert.equal(elements.modelSelect.value,"GPT");
assert.equal(elements.connectionStatus.textContent,"已安全连接");
assert.equal(elements.sendBtn.disabled,false);

// Native dialog: button, close, K shortcut and editable-field guard.
assert.equal(elements.sidebarDialog.open,undefined);
elements.sidebarToggle.listeners.click();
assert.equal(elements.sidebarDialog.open,true);
assert.equal(elements.sidebarToggle.attributes["aria-expanded"],"true");
elements.sidebarClose.listeners.click();
assert.equal(elements.sidebarDialog.open,false);
assert.equal(elements.sidebarToggle.attributes["aria-expanded"],"false");
let keyPrevented = 0;
const drawerKey = documentListeners.keydown;
drawerKey({key:"k",ctrlKey:false,altKey:false,metaKey:false,
  shiftKey:false,isComposing:false,repeat:false,
  target:{closest:()=>null},preventDefault(){keyPrevented++;}});
assert.equal(elements.sidebarDialog.open,true);
assert.equal(keyPrevented,1);
drawerKey({key:"k",ctrlKey:false,altKey:false,metaKey:false,
  shiftKey:false,isComposing:false,repeat:false,
  target:{closest:()=>true},preventDefault(){keyPrevented++;}});
assert.equal(elements.sidebarDialog.open,true,"typing K must not close drawer");
assert.equal(keyPrevented,1);
elements.sidebarDialog.close();

// Desktop Enter submits; mobile keyboard Enter creates a newline.
const key = elements.messageInput.listeners.keydown;
let prevented = 0;
elements.messageInput.value = "";
key({key:"Enter",shiftKey:false,isComposing:false,
  preventDefault(){prevented++;}});
assert.equal(prevented,1);
assert.equal(elements.chatForm.submitCount,1);

coarse = true;
key({key:"Enter",shiftKey:false,isComposing:false,
  preventDefault(){prevented++;}});
assert.equal(prevented,1,"iPhone Enter must not force submit");
assert.equal(elements.chatForm.submitCount,1);
coarse = false;

// User sends one message to existing SSE endpoint, without API contract changes.
elements.messageInput.value = "你好";
elements.chatForm.listeners.submit({preventDefault(){}});
await flush();
const chat = calls.find(c => c.path === "/webui/api/chat");
assert.ok(chat,"existing SSE chat route");
const payload = JSON.parse(chat.options.body);
assert.equal(payload.model,"GPT");
assert.equal(payload.messages.at(-1).content,"你好");
assert.equal(elements.messages.children.length,2);
const assistant = elements.messages.children.at(-1);
assert.equal(assistant.className,"message assistant");
const bubble = assistant.children.find(node => node.className === "bubble");
assert.equal(bubble.textContent,"测试回复");
const copy = assistant.children.find(node => node.className === "copy-reply");
assert.ok(copy,"response copy action");
await copy.listeners.click();
assert.equal(copied,"测试回复");
assert.equal(copy.textContent,"已复制");

// Reset is per-tab-only. No server persistence or secret submission.
elements.newChatBtn.listeners.click();
assert.equal(elements.messages.children.length,1);
assert.equal(elements.messages.children[0],elements.welcome);
assert.equal(elements.sendBtn.disabled,false);
assert.equal(calls.some(c => /history|upload/.test(c.path)),false);

console.log("WEBUI_V2_INTERACTION_PASS: auth, GPT model, SSE, copy, mobile Enter, reset; no real network");
