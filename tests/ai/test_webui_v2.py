"""S3-Voice UI v2 static safety tests; no network, credential or VPS access."""
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXPECTED = (
    "connectionStatus", "logoutBtn", "loginView", "loginForm",
    "ownerPassword", "loginBtn", "loginError", "chatView",
    "modelSelect", "newChatBtn", "messages", "welcome", "chatForm",
    "messageInput", "voiceButton", "sendBtn", "voiceStatus", "appNotice"
)
REQUIRED_ASSETS = ("/webui/app.css", "/webui/app.js", "/webui/audio-ui.mjs")


class Document(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = Counter()
        self.scripts = []
        self.links = []
        self.tags = []
        self.meta = []
        self.external = []
        self.inline_events = []
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append(tag)
        if "id" in a:
            self.ids[a["id"]] += 1
        if tag == "script":
            self.scripts.append(a.get("src"))
        if tag == "link":
            self.links.append(a.get("href"))
        if tag == "meta":
            self.meta.append(a)
        for key, val in attrs:
            if key.startswith("on"):
                self.inline_events.append(key)
            if key in ("href", "src") and val and re.match(r"^(?:https?:)?//", val):
                self.external.append((key, val))


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "webui/index.html").read_text(encoding="utf-8")
        cls.css = (ROOT / "webui/app.css").read_text(encoding="utf-8")
        cls.js = (ROOT / "webui/app.js").read_text(encoding="utf-8")
        cls.voice = (ROOT / "webui/audio-ui.mjs").read_text(encoding="utf-8")
        cls.document = Document()
        cls.document.feed(cls.html)

    def test_unique_stable_dom_ids(self):
        for element in EXPECTED:
            self.assertEqual(1, self.document.ids[element], element)
        self.assertEqual([], [name for name, count in self.document.ids.items() if count > 1])
        self.assertEqual(1, self.document.ids["messages"])
        self.assertIn('class="layout"', self.html)
        self.assertIn('class="workspace"', self.html)
        self.assertIn('class="sidebar"', self.html)

    def test_no_new_external_runtime_or_csp_relaxation(self):
        self.assertEqual([], self.document.external)
        self.assertEqual([], self.document.inline_events)
        self.assertEqual(
            ["/webui/app.js", "/webui/audio-ui.mjs"],
            self.document.scripts
        )
        self.assertIn("/webui/app.css", self.document.links)
        csp = [m.get("content", "") for m in self.document.meta
               if m.get("http-equiv") == "Content-Security-Policy"]
        self.assertEqual(1, len(csp))
        self.assertIn("default-src 'none'", csp[0])
        self.assertIn("connect-src 'self'", csp[0])
        self.assertNotIn("'unsafe-inline'", csp[0])
        self.assertNotIn("https:", csp[0])

    def test_voice_and_text_routes_unmodified_in_ui(self):
        self.assertIn('id="voiceButton"', self.html)
        self.assertIn('id="voiceStatus"', self.html)
        self.assertIn('class="s3-mic-icon"', self.html)
        self.assertIn('const originAPI = "/webui/api/"', self.js)
        self.assertIn('originAPI + "chat"', self.js)
        self.assertIn('model: el("modelSelect").value', self.js)
        self.assertIn('"/webui/ws"', self.voice)
        self.assertIn('audio-worklet.js', self.voice)
        self.assertIn('createXiaozhiCodec', self.voice)

    def test_responsive_theme_and_accessibility(self):
        for required in (
            "grid-template-columns: 252px minmax(0, 1fr)",
            "@media (max-width: 980px)",
            "@media (max-width: 600px)",
            "env(safe-area-inset-bottom)",
            "@media (prefers-color-scheme: light)",
            "@media (prefers-reduced-motion: reduce)",
            ":focus-visible", "#voiceButton", "#modelSelect", ".copy-reply"
        ):
            self.assertIn(required, self.css, required)
        self.assertIn('aria-label="选择 AI 模型"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('aria-label="开始语音"', self.html)

    def test_ephemeral_history_and_copy_are_ui_only(self):
        self.assertIn("当前会话", self.html)
        self.assertIn("本次文字内容", self.html)
        self.assertNotIn("localStorage", self.js)
        self.assertNotIn("sessionStorage", self.js)
        self.assertIn("navigator.clipboard?.writeText", self.js)
        self.assertIn("window.matchMedia?.", self.js)


if __name__ == "__main__":
    unittest.main()
