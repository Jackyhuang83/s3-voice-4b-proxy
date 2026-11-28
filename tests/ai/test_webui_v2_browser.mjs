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
const server = createServer((req, res) => {
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
        sidebarVisible:getComputedStyle(document.querySelector(".sidebar")).display!=="none",
        options:document.querySelector("#modelSelect").options.length,
        bounds
      };
    });
    assert.ok(state.scrollWidth<=width+1,
      `horizontal overflow at ${width}: ${state.scrollWidth}`);
    assert.equal(state.sidebarVisible,width>=981,
      `sidebar visibility at ${width}`);
    assert.equal(state.options,2);
    for (const [id,b] of Object.entries(state.bounds)) {
      assert.ok(b.w>0&&b.h>0,`invisible ${id} at ${width}`);
      assert.ok(b.x>=-1&&b.x+b.w<=width+1,`clipped ${id} at ${width}`);
    }
    assert.ok(state.bounds.voiceButton.w>=42 &&
      state.bounds.voiceButton.h>=42,`voice touch target too small at ${width}`);
    await page.screenshot({path:`test-results/webui-v2-${width}.png`,fullPage:true});
    await page.locator("#messageInput").fill("你好");
    await page.locator("#sendBtn").click();
    await page.locator(".message.assistant .bubble").getByText("浏览器测试答复").waitFor();
    await page.locator(".copy-reply").click();
    assert.equal(await page.evaluate(()=>window.__copiedText),"浏览器测试答复");
    await page.locator("#newChatBtn").click();
    assert.equal(await page.locator(".message").count(),0);
    assert.deepEqual(errors,[],`page errors at ${width}`);
    snapshots.push(`${width}px: no overflow, ${state.sidebarVisible?"desktop nav":"mobile nav"}, SSE/copy/reset PASS`);
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
