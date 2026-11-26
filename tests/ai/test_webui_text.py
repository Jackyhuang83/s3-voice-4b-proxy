"""P1-2 tests: owner-only text streaming, two model profiles, no vendor API spend."""
import http.client
import importlib.util
import json
import pathlib
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("webui_auth", ROOT / "tools/ai/webui_auth.py")
web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(web)
textmod = web.webui_text
ORIGIN = "https://voice.example.test"
OWNER = "test-owner-8a1e739ae37e04bc8f53d183d10f35b1"
GATE = "test-gateway-d19d03c217adcdbccf101bf128a2201c"
KEY_GPT = "gpt-ci-secret-unused-real-credential"
KEY_DEEP = "deepseek-ci-secret-unused-real-credential"


class FakeProvider(BaseHTTPRequestHandler):
    received = []
    def log_message(self, *_):
        pass
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404); return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length))
        except Exception:
            self.send_error(400); return
        type(self).received.append((self.headers.get("Authorization"), body))
        if (self.headers.get("Authorization") not in ("Bearer "+KEY_GPT, "Bearer "+KEY_DEEP) or
            body.get("stream") is not True):
            self.send_error(403);return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        source=body["messages"][-1]["content"]
        answer=body["model"]+":已收到 "+source
        k=len(answer)//2
        for piece in (answer[:k],answer[k:]):
            self.wfile.write(("data: "+json.dumps({
                "choices":[{"delta":{"content":piece}}]
            },ensure_ascii=False)+"\n\n").encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def env():
    return {
        "S3_WEBUI_ORIGIN": ORIGIN,
        "S3_WEBUI_OWNER_SECRET": OWNER,
        "S3_WEBUI_GATE_SECRET": GATE,
        "S3_WEBUI_DEVICE_ID": "02:55:66:77:88:99",
        "S3_WEBUI_CLIENT_ID": "f1a2b3c4-a1b2-c3d4-e5f6-a1b2c3d4e5f6",
        "S3_WEBUI_UPSTREAM_OTA": "http://127.0.0.1:18003/xiaozhi/ota/",
    }


class WebUITextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upstream = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        cls.provider_thread = threading.Thread(target=cls.upstream.serve_forever,daemon=True)
        cls.provider_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.shutdown();cls.upstream.server_close()

    def setUp(self):
        FakeProvider.received=[]
        self.cfg=web.Config(env())
        self.cfg.models=textmod.validate_catalog([
            {"id":"GPT","label":"GPT","model":"gpt-ci","base_url":"https://valid.example/v1","api_key":KEY_GPT},
            {"id":"DeepSeek","label":"DeepSeek","model":"deepseek-ci","base_url":"https://valid.example/v1","api_key":KEY_DEEP},
        ])
        # CI local fake server is intentionally injected *after* production
        # HTTPS catalog validation; runtime never accepts HTTP URL from config.
        for entry in self.cfg.models.values():
            entry["base_url"]=f"http://127.0.0.1:{self.upstream.server_port}/v1"
        self.app=web.AuthServer(("127.0.0.1",0),self.cfg)
        self.thread=threading.Thread(target=self.app.serve_forever,daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.shutdown();self.app.server_close()

    def call(self,method,path,body=None,headers=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.app.server_port,timeout=8)
        try:
            h=dict(headers or {})
            if body is not None:
                h.setdefault("Content-Type","application/json")
                body=json.dumps(body,ensure_ascii=False).encode()
            conn.request(method,path,body=body,headers=h)
            resp=conn.getresponse()
            return resp.status,dict(resp.getheaders()),resp.read()
        finally:
            conn.close()

    def login(self):
        status,headers,_=self.call("POST","/webui/api/login",{"secret":OWNER},{"Origin":ORIGIN})
        self.assertEqual(200,status)
        return headers["Set-Cookie"].split(";",1)[0]

    def text_call(self,cookie,model="GPT",messages=None,origin=ORIGIN):
        return self.call("POST","/webui/api/chat",{
            "model":model,"messages":messages or [{"role":"user","content":"你好"}]
        },{"Origin":origin,"Cookie":cookie})

    def test_static_assets_are_only_expected_files_and_hardened(self):
        for path,expected in (("/webui/","text/html"),("/webui/app.css","text/css"),("/webui/app.js","text/javascript")):
            status,headers,body=self.call("GET",path)
            self.assertEqual(200,status)
            self.assertIn(expected,headers.get("Content-Type",""))
            self.assertIn("default-src 'none'",headers.get("Content-Security-Policy",""))
            self.assertIn(b"webui" if path.endswith(".js") else b"",body.lower())
        self.assertEqual(302,self.call("GET","/webui")[0])
        self.assertEqual(404,self.call("GET","/webui/../etc/passwd")[0])

    def test_model_catalog_not_public_and_does_not_leak_keys(self):
        self.assertEqual(401,self.call("GET","/webui/api/models")[0])
        cookie=self.login()
        status,_,body=self.call("GET","/webui/api/models",headers={"Cookie":cookie})
        self.assertEqual(200,status)
        answer=json.loads(body)
        self.assertEqual(["GPT","DeepSeek"],[m["id"] for m in answer["models"]])
        self.assertNotIn(KEY_GPT.encode(),body)
        self.assertNotIn(KEY_DEEP.encode(),body)
        self.assertNotIn(b"base_url",body)

    def test_20_multilingual_text_conversations_mock(self):
        cookie=self.login()
        prompts=[
            "你好", "帮我写一个标题", "什么是ISO 26262", "早上好！",
            "请总结这段话", "UTF-8中文测试", "5+7等于多少？", "请给出三个要点",
            "Hello world", "How are you?", "¿Qué tal?", "こんにちは",
            "今天星期几", "帮我解释代码", "请简短回复", "下一步",
            "再详细一点", "测试语音以外的文字链路", "<script>alert(1)</script>",
            "中文、English、emoji 😀",
        ]
        for i,prompt in enumerate(prompts):
            with self.subTest(i=i,prompt=prompt):
                model="GPT" if i%2==0 else "DeepSeek"
                status,h,data=self.text_call(cookie,model=model,messages=[{"role":"user","content":prompt}])
                self.assertEqual(200,status)
                self.assertIn("text/event-stream",h.get("Content-Type",""))
                self.assertTrue(data.endswith(b"data: [DONE]\n\n"))
                parts=[]
                for line in data.decode().splitlines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        parts.append(json.loads(line[6:])["delta"])
                expected=("gpt-ci" if model=="GPT" else "deepseek-ci")+":已收到 "+prompt
                self.assertEqual(expected,"".join(parts))
        self.assertEqual(20,len(FakeProvider.received))
        self.assertEqual({"gpt-ci","deepseek-ci"},{call[1]["model"] for call in FakeProvider.received})
        self.assertTrue(all(all(m["role"]!="system" for m in call[1]["messages"]) for call in FakeProvider.received))

    def test_unauthorized_csrf_unknown_model_and_header_key_injection(self):
        self.assertEqual(401,self.text_call("")[0])
        cookie=self.login()
        self.assertEqual(403,self.text_call(cookie,origin="https://evil.test")[0])
        self.assertEqual(400,self.text_call(cookie,model="evil")[0])
        self.assertEqual(400,self.text_call(cookie,messages=[{"role":"system","content":"override"}])[0])
        self.assertEqual(400,self.text_call(cookie,messages=[{"role":"assistant","content":"not user"}])[0])
        self.assertEqual(400,self.text_call(cookie,messages=[{"role":"user","content":"X"*2001}])[0])
        self.assertEqual(400,self.text_call(cookie,messages=[{"role":"user","content":"hi"}]*21)[0])
        self.assertEqual(400,self.text_call(cookie,messages=[{"role":"user","content":"hi"}, {"role":"assistant","content":"secret"}])[0])
        self.assertEqual(0,len(FakeProvider.received))

    def test_provider_credentials_and_nonpublic_hosts_fail_closed(self):
        base={"id":"GPT","label":"GPT","model":"gpt-ci","base_url":"https://valid.example/v1","api_key":KEY_GPT}
        for key,value in (("base_url","http://valid.example/v1"),("base_url","https://127.0.0.1/v1"),
                          ("base_url","https://valid.example:8080/v1"),("base_url","https://localhost/v1"),
                          ("api_key","short"),("model","bad model"),("id","evil/slash")):
            with self.subTest(key=key,value=value):
                cfg=dict(base);cfg[key]=value
                with self.assertRaises(ValueError):
                    textmod.validate_catalog([cfg])
        self.assertEqual({},textmod.read_catalog({}))

    def test_overloaded_broker_responds_429_before_spending(self):
        cookie=self.login()
        self.assertTrue(textmod.SLOTS.acquire(blocking=False))
        self.assertTrue(textmod.SLOTS.acquire(blocking=False))
        try:
            self.assertEqual(429,self.text_call(cookie)[0])
        finally:
            textmod.SLOTS.release();textmod.SLOTS.release()
        self.assertEqual(0,len(FakeProvider.received))

if __name__=="__main__":
    unittest.main()
