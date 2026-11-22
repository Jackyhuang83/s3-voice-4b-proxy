#!/usr/bin/env python3
"""A05: exercise the OFFICIAL XiaoZhi v0.9.8 OpenAI-compatible LLM adapter.

Run inside the pinned xiaozhi-server Docker container; do NOT vendor/rewrite
the official provider. Mock mode makes no outbound requests and costs nothing.
Live mode reads credentials only from a root-owned, temporary file in the
private A03 data mount. It sends exactly one tiny streamed Chat Completion.
"""
import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.providers.llm.openai.openai import LLMProvider


def run_response(cfg):
    provider = LLMProvider(cfg)
    chunks = provider.response("a05-provider-smoke", [
        {"role": "system", "content": "Reply with exactly one short word: OK."},
        {"role": "user", "content": "Connectivity test."},
    ])
    parts = []
    for part in chunks:
        if part:
            parts.append(part)
        if len("".join(parts)) > 600:
            break
    result = "".join(parts).strip()
    if not result:
        raise AssertionError("official adapter returned empty stream")
    return result


class FakeAPI(BaseHTTPRequestHandler):
    seen = []
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        try:
            request = json.loads(raw)
        except Exception:
            self.send_error(400)
            return
        good = (self.path == "/v1/chat/completions"
                and self.headers.get("Authorization") == "Bearer a05-ci-fake-key"
                and request.get("model") == "a05-ci-model"
                and request.get("stream") is True
                and isinstance(request.get("messages"), list)
                and len(request["messages"]) == 2)
        self.seen.append(good)
        if not good:
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        for s in ("O", "K"):
            chunk = {"id": "a05-ci", "object": "chat.completion.chunk",
                     "choices": [{"index": 0, "delta": {"content": s},
                                  "finish_reason": None}]}
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def log_message(self, *args):
        pass


def mock():
    with ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI) as httpd:
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        cfg = {
            "type": "openai",
            "base_url": "http://127.0.0.1:%d/v1" % httpd.server_port,
            "model_name": "a05-ci-model",
            "api_key": "a05-ci-fake-key",
            "max_tokens": 32,
            "timeout": 8,
        }
        try:
            result = run_response(cfg)
            if result != "OK" or FakeAPI.seen != [True]:
                raise AssertionError("official adapter did not stream expected output")
        finally:
            httpd.shutdown()
    print("A05_TEST_PASS: pinned upstream OpenAI-compatible provider, /v1/chat/completions, bearer auth, SSE streaming and model selection")
    print("A05_TEST_PASS: no real provider, no API billing, no device, no config changes")


def live(path):
    obj = json.loads(Path(path).read_text())
    cfg = {
        "type": "openai",
        "base_url": obj["base_url"],
        "model_name": obj["model_name"],
        "api_key": obj["api_key"],
        "max_tokens": 32,
        "timeout": 20,
    }
    # No request/response text, API Key, or provider URL in output.
    try:
        run_response(cfg)
    except Exception as err:
        raise SystemExit("A05_BLOCKED: provider's real streamed Chat Completion failed (%s); live config not changed" % type(err).__name__) from None
    print("A05_LIVE_PASS: upstream OpenAI-compatible provider returned a real streamed answer; one tiny API request was made")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["mock", "live"])
    p.add_argument("--credentials")
    a = p.parse_args()
    if a.mode == "mock":
        mock()
    else:
        if not a.credentials:
            p.error("live mode requires --credentials")
        live(a.credentials)
