// UI v2 layout-level browser acceptance. Runs locally on GitHub Actions Chrome.
// API data and audio codec vendor are local synthetic fixtures; NO real service used.
import assert from "node:assert/strict";
import {createServer} from "node:http";
import {readFileSync, mkdirSync} from "node:fs";
import {join, extname, normalize} from "node:path";
import {chromium} from "playwright-core";

const ROOT = process.cwd();
const CONTENT_TYPES = {
  ".html":"text/html; charset=utf-8",
  ".css":"text/css; charset=utf-8",
  ".js":"text/javascript; charset=utf-8",
  ".mjs":"text/javascript; charset=utf-8"
};

function reply(res, status, body, type="application/json; charset=utf-8") {
  res.writeHead(status,{
    "Content-Type":type,
    "Cache-Control":"no-store",
    "Access-Control-Allow-Origin":"*"
  });
  res.end(body);
}
const requestEvents = [];
const server = createServer((req, res) => {
  requestEvents.push([req.method, req.url]);
  const url = new URL(req.url, "http://127.0.0.1");
  const pathname = url.pathname;
  if (pathname === "/webui/api/session") {
    return reply(res,200,JSON.stringify({authenticated:true}));
  }
  if (pathname === "/webui/api/models") {
    return reply(res,200,JSON.stringify({models:[
      {id:"GPT",label:"GPT"},{id:"DeepSeek",label:"DeepSeek"}
    ]}));
  }
  if (pathname === "/webui/api/chat" && req.method === "POST") {
    res.writeHead(200,{"Content-Type":"text/event-stream; charset=utf-8",
      "Cache-Control":"no-store"});
    return res.end('data: {"delta":"浏览器测试答复"}\n\ndata: [DONE]\n\n');
  }
  if (pathname === "/webui/vendor/libopus/dist/index.js") {
    // Codec has its own real Opus CI. Layout test does not use microphone.
    return reply(res,200,
      "export const Application={Voip:2048}; export async function createEncoder(){throw Error('fixture only')} export async function createDecoder(){throw Error('fixture only')}",
      CONTENT_TYPES[".js"]);
  }
  const relative = pathname === "/webui/" ? "index.html" :
    pathname.startsWith("/webui/") ? pathname.slice("/webui/".length) : null;
  if (!relative || relative.includes("..") || relative.startsWith("/")) {
    return reply(res,404,"Not Found","text/plain");
  }
  try {
    const file = join(ROOT,"webui", normalize(relative));
    return reply(res,200,readFileSync(file),CONTENT_TYPES[extname(file)]||"application/octet-stream");
  } catch {
    return reply(res,404,"Not Found","text/plain");
  }
});

await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const chromePath = process.env.CHROME_BIN || "/usr/bin/google-chrome";
let browser;
try {
  browser = await chromium.launch({executablePath:chromePath,headless:true,
    args:["--no-sandbox","--disable-dev-shm-usage"]});
  mkdirSync("test-results",{recursive:true});
  const snapshots=[];
  for (const [width,height] of [[375,812],[430,932],[768,1024],[1280,800]]) {
    const context=await browser.newContext({
      viewport:{width,height},deviceScaleFactor:1,
      hasTouch:width<600,isMobile:width<600,
      colorScheme:"dark"
    });
    await context.addInitScript(() => {
      Object.defineProperty(navigator,"clipboard",{configurable:true,value:{
        async writeText(value) {window.__copiedText=value;}
      }});
    });
    const page=await context.newPage();
    const errors=[];
    page.on("pageerror",e=>errors.push(e.message));
    await page.goto(origin+"/webui/",{waitUntil:"networkidle"});
    await page.locator("#chatView").waitFor({state:"visible"});
    const state=await page.evaluate(() => {
      const ids=["modelSelect","voiceButton","sendBtn","messageInput","newChatBtn"];
      const bounds=Object.fromEntries(ids.map(id=>{
        const el=document.getElementById(id);
        const rect=el.getBoundingClientRect();
        return [id,{x:rect.x,y:rect.y,w:rect.width,h:rect.height}];
      }));
      return {
        scrollWidth:document.documentElement.scrollWidth,
        clientWidth:document.documentElement.clientWidth,
        sidebarOpen:document.querySelector("#sidebarDialog").open,
        openerVisible:getComputedStyle(document.querySelector("#sidebarToggle")).display!=="none",
        options:document.querySelector("#modelSelect").options.length,
        bounds
      };
    });
    assert.ok(state.scrollWidth<=width+1,
      `horizontal overflow at ${width}: ${state.scrollWidth}`);
    assert.equal(state.sidebarOpen,false,`drawer must start collapsed at ${width}`);
    assert.equal(state.openerVisible,true,`opener must be visible at ${width}`);
    assert.equal(state.options,2);
    for (const [id,b] of Object.entries(state.bounds)) {
      assert.ok(b.w>0&&b.h>0,`invisible ${id} at ${width}`);
      assert.ok(b.x>=-1&&b.x+b.w<=width+1,`clipped ${id} at ${width}`);
    }
    assert.ok(state.bounds.voiceButton.w>=42 &&
      state.bounds.voiceButton.h>=42,`voice touch target too small at ${width}`);
    await page.screenshot({path:`test-results/webui-v2-${width}.png`,fullPage:true});
    await page.locator("#sidebarToggle").click();
    assert.equal(await page.locator("#sidebarDialog").evaluate(e=>e.open),true);
    assert.equal(await page.locator("#sidebarToggle").getAttribute("aria-expanded"),"true");
    await page.locator("#sidebarClose").waitFor({state:"visible"});
    await page.screenshot({path:`test-results/webui-v3-${width}-drawer.png`,fullPage:true});
    await page.keyboard.press("Escape");
    assert.equal(await page.locator("#sidebarDialog").evaluate(e=>e.open),false);
    await page.keyboard.press("k");
    assert.equal(await page.locator("#sidebarDialog").evaluate(e=>e.open),true);
    await page.mouse.click(width-3, Math.round(height/2));
    assert.equal(await page.locator("#sidebarDialog").evaluate(e=>e.open),false,
      "backdrop click must close the drawer");
    await page.locator("#messageInput").fill("k");
    await page.keyboard.press("k");
    assert.equal(await page.locator("#sidebarDialog").evaluate(e=>e.open),false,
      "typing in message box must not activate shortcut");
    await page.locator("#messageInput").fill("");
    await page.locator("#messageInput").fill("你好");
    await page.locator("#sendBtn").click();
    try {
      await page.waitForFunction(
        () => document.querySelector(".message.assistant .bubble")?.textContent === "浏览器测试答复",
        null, {timeout:10000}
      );
    } catch (error) {
      const dom = await page.evaluate(() => ({
        messages:[...document.querySelectorAll(".message")].map(e=>e.textContent),
        notice:document.getElementById("appNotice")?.textContent,
        model:document.getElementById("modelSelect")?.value,
        sendDisabled:document.getElementById("sendBtn")?.disabled,
        inputDisabled:document.getElementById("messageInput")?.disabled,
        chatHidden:document.getElementById("chatView")?.hidden
      }));
      throw Error("BROWSER_SSE_DIAG: " + JSON.stringify({
        viewport:width,dom,requests:requestEvents.slice(-20),pageErrors:errors
      }),{cause:error});
    }
    await page.locator(".copy-reply").click();
    assert.equal(await page.evaluate(()=>window.__copiedText),"浏览器测试答复");
    await page.screenshot({path:`test-results/webui-v2-${width}-chat.png`,fullPage:true});
    await page.locator("#newChatBtn").click();
    assert.equal(await page.locator(".message").count(),0);
    await page.locator("#welcome").waitFor({state:"visible"});
    await page.locator("#messageInput").fill("再次提问");
    await page.locator("#sendBtn").click();
    await page.waitForFunction(
      () => document.querySelector(".message.assistant .bubble")?.textContent === "浏览器测试答复",
      null, {timeout:10000}
    );
    assert.equal(await page.locator(".message.assistant").count(),1,
      "second question must render a fresh assistant turn after welcome removal");
    assert.deepEqual(errors,[],`page errors at ${width}`);
    snapshots.push(`${width}px: no overflow, collapsed accessible drawer + K/Escape/backdrop, SSE/copy/reset PASS`);
    await context.close();
  }
  // Light scheme must use visibly different surface colors at desktop.
  const c=await browser.newContext({viewport:{width:1280,height:800},colorScheme:"light"});
  const page=await c.newPage();
  await page.goto(origin+"/webui/",{waitUntil:"networkidle"});
  const background=await page.locator("body").evaluate(el=>getComputedStyle(el).backgroundColor);
  assert.equal(background,"rgb(250, 251, 252)");
  await page.screenshot({path:"test-results/webui-v2-1280-light.png",fullPage:true});
  await c.close();
  console.log("WEBUI_V2_CHROME_LAYOUT_PASS:",snapshots.join("; "),"; light theme PASS");
} finally {
  if (browser) await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
