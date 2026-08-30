"""Valódi, offline Qt WebEngine integrációs staging a helyi DOM-fixture ellen.

Nincs ChatGPT-fiók, felhasználói böngészőprofil, vágólap vagy éles kérés.
A https://chatgpt.com csak a memóriába töltött fixture eredetének szimulációja.
"""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWidgets import QApplication

from gamer_translator.main_window import MainWindow


FIXTURE = """<!doctype html><html lang="hu"><head><meta charset="utf-8">
<link rel="icon" href="data:,">
<title>Gamer Translator offline staging</title></head><body>
<main id="conversation"></main>
<form id="form"><div data-testid="composer">
COMPOSER
<input id="attachment" type="file" accept="image/*">
<button data-testid="send-button" type="submit" aria-label="Send message">Send</button>
</div></form>
<script>
const composer = document.querySelector('#prompt-textarea');
const send = document.querySelector('button');
const attachment = document.querySelector('#attachment');
document.body.dataset.submitCount = '0';
attachment.addEventListener('change', () => {
  const preview = document.createElement('img');
  preview.src = URL.createObjectURL(attachment.files[0]);
  document.querySelector('[data-testid="composer"]').appendChild(preview);
});
document.querySelector('#form').addEventListener('submit', (event) => {
  event.preventDefault();
  const text = composer.tagName === 'TEXTAREA' ? composer.value : composer.innerText;
  document.body.dataset.submitCount = String(Number(document.body.dataset.submitCount) + 1);
  document.body.dataset.submittedText = text;
  document.body.dataset.fileCount = String(attachment.files.length);
  const user = document.createElement('div');
  user.dataset.messageAuthorRole = 'user'; user.textContent = text || '[kép]';
  document.querySelector('#conversation').appendChild(user);
  if (composer.tagName === 'TEXTAREA') composer.value = ''; else composer.replaceChildren();
  attachment.value = '';
  for (const preview of document.querySelectorAll('form img')) preview.remove();
  send.setAttribute('aria-label', 'Stop'); send.dataset.testid = 'stop-button'; send.textContent = 'Stop';
  const answer = document.createElement('div');
  answer.dataset.messageAuthorRole = 'assistant'; answer.setAttribute('aria-busy', 'true');
  answer.textContent = 'Thinking...';
  document.querySelector('#conversation').appendChild(answer);
  setTimeout(() => {
    answer.textContent = 'Offline fordítás elkészült.';
    answer.setAttribute('aria-busy', 'false');
    send.setAttribute('aria-label', 'Send message'); send.dataset.testid = 'send-button'; send.textContent = 'Send';
  }, 60);
});
</script></body></html>"""


class BlockNetwork(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent):
        super().__init__(parent)
        self.blocked: list[str] = []

    def interceptRequest(self, request):
        if request.requestUrl().scheme() not in {"data", "blob", "about"}:
            self.blocked.append(request.requestUrl().toString())
            request.block(True)


class OfflinePage(QWebEnginePage):
    def __init__(self, profile):
        super().__init__(profile)
        self.errors: list[str] = []

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            self.errors.append(f"{source_id}:{line_number}: {message}")


class DeliveryHarness:
    _is_chatgpt_url = MainWindow._is_chatgpt_url
    _run_javascript = MainWindow._run_javascript
    _ensure_automation_ready = MainWindow._ensure_automation_ready
    _execute_delivery = MainWindow._execute_delivery
    _wait_with_events = MainWindow._wait_with_events

    def __init__(self, page):
        self.browser = SimpleNamespace(url=page.url, page=lambda: page)
        self.settings = SimpleNamespace(page_ready_timeout_ms=1000)
        self.automation_script = (Path(__file__).resolve().parents[1] / "gamer_translator" / "automation.js").read_text(encoding="utf-8")
        self.page_loading = False
        self.automation_ready = False
        self.browser_interaction_active = False
        self.clipboard_translation_in_progress = False

    def _sync_browser_host_mode(self):
        pass

    def _sync_browser_runtime_state(self):
        pass

    def _stop_response_followup_polling(self):
        pass

    def _touch_browser_interaction_heartbeat(self):
        pass


class WebEngineStagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        # A név nélküli profil off-the-record; nem olvassa az alkalmazás mentett sütijeit.
        self.profile = QWebEngineProfile(self.app)
        self.assertTrue(self.profile.isOffTheRecord())
        self.blocker = BlockNetwork(self.profile)
        self.profile.setUrlRequestInterceptor(self.blocker)
        self.page = OfflinePage(self.profile)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, False)
        self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste, False)
        self.harness = DeliveryHarness(self.page)

    def tearDown(self):
        self.harness = None
        self.page.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.profile.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def load_fixture(self, *, contenteditable=False, origin="https://chatgpt.com/"):
        composer = '<div id="prompt-textarea" contenteditable="true" role="textbox"></div>' if contenteditable else '<textarea id="prompt-textarea"></textarea>'
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        loaded = []

        def finished(ok):
            loaded.append(ok)
            loop.quit()

        self.page.loadFinished.connect(finished)
        timer.timeout.connect(loop.quit)
        self.page.setHtml(FIXTURE.replace("COMPOSER", composer), QUrl(origin))
        timer.start(10000)
        loop.exec()
        timer.stop()
        self.page.loadFinished.disconnect(finished)
        self.assertEqual(loaded, [True], "A memória-fixture nem töltődött be.")
        self.assertEqual(self.page.url().toString(), origin)

    def raw_javascript(self, script, *, world=QWebEngineScript.ScriptWorldId.MainWorld):
        loop = QEventLoop()
        result = []
        timer = QTimer()
        timer.setSingleShot(True)

        def finished(value):
            result.append(value)
            loop.quit()

        timer.timeout.connect(loop.quit)
        self.page.runJavaScript(script, world, finished)
        timer.start(5000)
        if not result:
            loop.exec()
        timer.stop()
        self.assertTrue(result, "Az offline JavaScript nem tért vissza.")
        return result[0]

    def deliver(self, **values):
        return self.harness._execute_delivery({
            "prompt": "", "autoSubmit": True, "copyResponseToClipboard": True,
            "pageReadyTimeoutMs": 1000, "responseTimeoutMs": 3000, **values,
        })

    def test_isolated_automation_survives_main_world_name_collision(self):
        self.load_fixture()
        self.raw_javascript("window.__gamerTranslatorDeliver = () => { throw new Error('page override'); }; window.__gamerTranslatorDeliverVersion = 'page';")
        self.harness._ensure_automation_ready()
        self.assertTrue(self.harness.automation_ready)
        result = self.deliver(prompt="Árvíztűrő tükörfúrógép.")
        self.assertEqual(result["assistantResponseText"], "Offline fordítás elkészült.")
        self.assertFalse(result["assistantResponseCopied"])
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "1")
        self.assertEqual(self.raw_javascript("window.__gamerTranslatorDeliverVersion"), "page")
        self.assertEqual(self.raw_javascript("document.body.dataset.submittedText"), "Árvíztűrő tükörfúrógép.")
        self.assertEqual(self.page.errors, [])
        self.assertEqual(self.blocker.blocked, [])

    def test_contenteditable_multiline_prompt_is_plain_text(self):
        self.load_fixture(contenteditable=True)
        prompt = '<img src=x onerror="window.injected=true">\n\nMásodik bekezdés: /spawn\n\n\nUtolsó sor'
        result = self.deliver(prompt=prompt, autoSubmit=False)
        self.assertTrue(result["ok"])
        self.assertEqual(self.raw_javascript("Array.from(document.querySelector('#prompt-textarea').children, (paragraph) => paragraph.textContent).join('\\n')"), prompt)
        self.assertEqual(self.raw_javascript("document.querySelectorAll('#prompt-textarea img').length"), 0)
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "0")
        self.assertEqual(self.page.errors, [])

    def test_image_attachment_and_response_without_clipboard_access(self):
        self.load_fixture()
        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII="
        result = self.deliver(imageDataUrl=f"data:image/png;base64,{png}", imageMimeType="image/png", imageFilename="offline.png")
        self.assertEqual(result["assistantResponseText"], "Offline fordítás elkészült.")
        self.assertEqual(self.raw_javascript("document.body.dataset.fileCount"), "1")
        self.assertEqual(self.raw_javascript("document.body.dataset.submitCount"), "1")
        self.assertFalse(self.page.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard))
        self.assertFalse(self.page.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanPaste))
        self.assertEqual(self.blocker.blocked, [])

    def test_fixture_network_is_blocked_before_request(self):
        self.load_fixture()
        self.raw_javascript("fetch('https://offline-probe.invalid/blocked').catch(() => {});")
        for _ in range(50):
            if self.blocker.blocked:
                break
            self.harness._wait_with_events(20)
        self.assertEqual(self.blocker.blocked, ["https://offline-probe.invalid/blocked"])

    def test_untrusted_fixture_cannot_run_native_automation(self):
        self.load_fixture(origin="https://example.invalid/")
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            self.harness._ensure_automation_ready()
        self.assertEqual(self.raw_javascript("typeof window.__gamerTranslatorDeliver", world=QWebEngineScript.ScriptWorldId.ApplicationWorld), "undefined")


if __name__ == "__main__":
    unittest.main()
