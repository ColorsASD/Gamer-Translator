"""Elkülönített alkalmazáspróba; a normál profilhoz és vágólaphoz nem fér hozzá."""
from __future__ import annotations

import hashlib
import io
import json
import platform
import ssl
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QObject, QTimer, QUrl, Signal, qVersion
from PySide6.QtGui import QClipboard, QImage
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEngineUrlRequestInterceptor
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .settings_store import AppSettings, SettingsStore


FIXTURE = """<!doctype html><html lang="hu"><head><meta charset="utf-8">
<link rel="icon" href="data:,"><title>Offline staging – nem a ChatGPT szolgáltatás</title></head>
<body><h1>Gamer Translator offline önteszt</h1><main id="conversation"></main>
<form><div data-testid="composer"><textarea id="prompt-textarea"></textarea>
<input id="attachment" type="file" accept="image/*">
<button data-testid="send-button" type="submit" aria-label="Send message">Send</button>
</div></form><script>
const composer = document.querySelector('textarea'), send = document.querySelector('button');
const attachment = document.querySelector('#attachment');
document.body.dataset.submitCount = '0';
attachment.addEventListener('change', () => {
  const preview = document.createElement('img');
  preview.src = URL.createObjectURL(attachment.files[0]); document.querySelector('form').append(preview);
});
document.querySelector('form').addEventListener('submit', event => {
  event.preventDefault();
  document.body.dataset.submitCount = String(Number(document.body.dataset.submitCount) + 1);
  document.body.dataset.fileCount = String(attachment.files.length);
  const user = document.createElement('div'); user.dataset.messageAuthorRole = 'user';
  user.textContent = composer.value || '[kép]'; document.querySelector('main').append(user);
  composer.value = ''; attachment.value = '';
  for (const preview of document.querySelectorAll('form img')) { URL.revokeObjectURL(preview.src); preview.remove(); }
  send.setAttribute('aria-label', 'Stop'); send.dataset.testid = 'stop-button';
  const answer = document.createElement('div'); answer.dataset.messageAuthorRole = 'assistant';
  answer.setAttribute('aria-busy', 'true'); answer.textContent = 'Thinking...';
  document.querySelector('main').append(answer);
  setTimeout(() => {
    answer.textContent = 'Offline fordítás elkészült.'; answer.setAttribute('aria-busy', 'false');
    send.setAttribute('aria-label', 'Send message'); send.dataset.testid = 'send-button';
  }, 60);
});</script></body></html>"""


MODERN_IMAGE_FIXTURE = """<!doctype html><html lang="hu"><head><meta charset="utf-8">
<link rel="icon" href="data:,"><title>Offline képes szerepfejléc-próba</title>
<style>.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;
overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}</style></head>
<body><main id="conversation">
<div><h4 class="sr-only">You said:</h4>
<div data-chatgpt-search-unit-key="history-user-unit" data-chatgpt-search-message-ids='["history-user"]'>
<div data-user-message-bubble>Korábbi kérés.</div></div></div>
<div data-chatgpt-search-unit-key="history-assistant-unit" data-chatgpt-search-message-ids='["history-assistant"]'>
<h4 class="sr-only" data-conversation-role="assistant">ChatGPT said:</h4>
<div data-markdown-text-style>Korábbi kész válasz.</div></div>
</main><form><div data-testid="composer"><textarea id="prompt-textarea"></textarea>
<input id="attachment" type="file" accept="image/*">
<button data-testid="send-button" type="submit" aria-label="Send message">Send</button>
</div></form><script>
const composer=document.querySelector('textarea'), send=document.querySelector('button');
const attachment=document.querySelector('#attachment');
document.body.dataset.submitCount='0';
attachment.addEventListener('change',()=>{
  const preview=document.createElement('img');
  preview.src=URL.createObjectURL(attachment.files[0]); document.querySelector('form').append(preview);
});
document.querySelector('form').addEventListener('submit',event=>{
  event.preventDefault(); const count=Number(document.body.dataset.submitCount)+1;
  document.body.dataset.submitCount=String(count);
  document.body.dataset.fileCount=String(attachment.files.length);
  document.body.dataset.promptLength=String(composer.value.length);
  document.body.dataset.finished='false';
  const turn=document.createElement('div'), user=document.createElement('div');
  const heading=document.createElement('h4');
  heading.className='sr-only'; heading.textContent='You said:'; user.append(heading);
  const content=document.createElement('div');
  content.dataset.chatgptSearchUnitKey='modern-user-unit-'+count;
  content.dataset.chatgptSearchMessageIds=JSON.stringify(['modern-user-'+count]);
  if(attachment.files.length){
    const imageWrapper=document.createElement('div'), imageButton=document.createElement('div');
    imageButton.setAttribute('role','button'); imageButton.setAttribute('aria-label','Open image');
    const image=document.createElement('img'); image.dataset.state='closed';
    image.src=URL.createObjectURL(attachment.files[0]); image.width=32; image.height=32;
    imageButton.append(image); imageWrapper.append(imageButton); content.append(imageWrapper);
  }else{
    const bubble=document.createElement('div'); bubble.dataset.userMessageBubble='';
    bubble.textContent=composer.value; content.append(bubble);
  }
  user.append(content); turn.append(user);
  const answer=document.createElement('div');
  answer.dataset.chatgptSearchUnitKey='modern-assistant-unit-'+count;
  answer.dataset.chatgptSearchMessageIds=JSON.stringify(['modern-assistant-'+count]);
  answer.dataset.contentSearchUnitKey='modern-assistant-unit-'+count;
  answer.setAttribute('aria-busy','true');
  const answerHeading=document.createElement('h4'); answerHeading.dataset.conversationRole='assistant';
  answerHeading.className='sr-only'; answerHeading.textContent='ChatGPT said:';
  const markdown=document.createElement('div'); markdown.dataset.markdownTextStyle='';
  markdown.textContent='Folyamatban lévő részlet'; answer.append(answerHeading,markdown);
  turn.append(answer); document.querySelector('main').append(turn);
  composer.value=''; attachment.value='';
  for(const preview of document.querySelectorAll('form img')){URL.revokeObjectURL(preview.src);preview.remove();}
  send.setAttribute('aria-label','Stop'); send.dataset.testid='stop-button';
  setTimeout(()=>{markdown.textContent='Modern képfordítás elkészült.';},60);
  setTimeout(()=>{
    answer.setAttribute('aria-busy','false'); send.setAttribute('aria-label','Send message');
    send.dataset.testid='send-button'; document.body.dataset.finished='true';
  },220);
});</script></body></html>"""


class MemoryClipboard(QObject):
    """Csak az alkalmazáspéldány memóriájában létezik, nem a Windows vágólapján."""
    changed = Signal(object)
    Mode = QClipboard.Mode

    def __init__(self):
        super().__init__()
        self._image = QImage()
        self.text = ""

    def image(self):
        return self._image.copy()

    def setImage(self, value):
        self._image = value.copy()
        self.text = ""
        self.changed.emit(self.Mode.Clipboard)

    def setText(self, value):
        self._image = QImage()
        self.text = str(value)
        self.changed.emit(self.Mode.Clipboard)


class BlockNetwork(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent):
        super().__init__(parent)
        self.blocked = []

    def interceptRequest(self, request):
        if request.requestUrl().scheme() not in {"data", "blob", "about"}:
            self.blocked.append(request.requestUrl().toString())
            request.block(True)


class IsolatedWindow(MainWindow):
    """Valódi ablak és fordítási útvonalak, rendszerhatás nélküli illesztőkkel."""

    def __init__(self, store, *, offline):
        self.offline = offline
        self.test_clipboard = MemoryClipboard()
        super().__init__(store=store, clipboard=self.test_clipboard, private_browser=True, open_on_start=not offline)
        self.setWindowTitle("Gamer Translator – elkülönített teszt")
        self.system_keepawake_timer.stop()
        self.reset_defaults_button.setEnabled(False)
        for widget in (self.type_out_hotkey_enabled, self.screen_clip_hotkey_enabled,
                       self.quick_chat_hotkey_enabled, self.webview_gpu_acceleration_enabled):
            widget.setEnabled(False)
        self._set_live_status("Tesztmód: ideiglenes profil, nincs rendszervágólap vagy gyorsbillentyű.")

    def _build_browser(self):
        super()._build_browser()
        if self.offline:
            self.network_blocker = BlockNetwork(self.profile)
            self.profile.setUrlRequestInterceptor(self.network_blocker)

    def _register_hotkeys(self):
        pass

    def _build_tray_icon(self):
        pass

    def _refresh_system_keep_awake(self):
        pass

    def _restore_system_sleep_state(self):
        pass

    def _apply_native_window_theme(self):
        pass

    def _play_ready_sound(self):
        pass

    def _trigger_hotkey_action(self, action):
        raise RuntimeError("A tesztmódban a rendszer gyorsbillentyűi nem használhatók.")

    def _schedule_windows_restart(self, restart_command):
        raise RuntimeError("A tesztmódból nem indítható normál programpéldány.")


def test_settings(*, offline):
    return AppSettings(monitoring_enabled=offline, type_out_hotkey_enabled=False,
                       screen_clip_hotkey_enabled=False, quick_chat_hotkey_enabled=False,
                       webview_gpu_acceleration_enabled=False, ocr_text_from_clipboard_image=False,
                       copy_response_to_clipboard=True, page_ready_timeout_ms=5000)


def dispose_window(window):
    window.exit_requested = True
    window.close()
    for timer in window.findChildren(QTimer):
        timer.stop()
    # A lapnak a profil előtt kell megszűnnie, a háttérablak tulajdonlásától függetlenül.
    window.browser.setParent(window)
    for obj in (window.browser, window.page):
        obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    for obj in (window.profile, window.translation_overlay, window.quick_chat_overlay,
                window.browser_background_host, window):
        obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def run_self_test(report_path: Path, duration: int, model_dir: Path | None = None) -> int:
    report = {"startedAt": datetime.now(timezone.utc).isoformat(), "frozen": bool(getattr(sys, "frozen", False)),
              "python": platform.python_version(), "openssl": ssl.OPENSSL_VERSION, "qt": qVersion(),
              "mode": "offline fixture; no live ChatGPT requests", "checks": {}, "cycles": 0}
    started = time.monotonic()
    result = 1
    app = QApplication([sys.argv[0]])
    app.setQuitOnLastWindowClosed(False)
    window = None
    with tempfile.TemporaryDirectory(prefix="gamer-translator-self-test-") as temporary:
        store = SettingsStore(Path(temporary))
        store.save_settings(test_settings(offline=True))
        try:
            if sys.flags.optimize:
                raise RuntimeError("Az önteszt optimalizált Python módban nem futhat: az ellenőrzések kimaradnának.")
            window = IsolatedWindow(store, offline=True)
            window.show()
            loaded = []
            window.page.loadFinished.connect(loaded.append)
            window.page.setHtml(FIXTURE, QUrl("https://chatgpt.com/"))
            deadline = time.monotonic() + 20
            while not loaded and time.monotonic() < deadline:
                window._wait_with_events(30)
            assert loaded == [True], "Az offline oldal nem töltődött be."
            window.page.loadFinished.disconnect(loaded.append)
            window._ensure_automation_ready()
            report["checks"]["window_and_webengine_start"] = True
            assert window.profile.isOffTheRecord()
            assert not window.page.settings().testAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard)
            report["checks"]["isolated_profile_and_clipboard"] = True

            while report["cycles"] < 3 or time.monotonic() - started < duration:
                window._process_quick_chat_translation(f"Offline teszt {report['cycles']}: Árvíztűrő /spawn <b>GG</b>")
                count = window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000)
                assert int(count) == report["cycles"] + 1, "Hiányzó vagy ismételt beküldés."
                assert window.last_translated_text == "Offline fordítás elkészült.", window.last_run_status
                assert window.test_clipboard.text == window.last_translated_text
                assert store.load_last_translated_text() == window.last_translated_text
                assert not window.browser_interaction_active and not window.clipboard_translation_in_progress
                report["cycles"] += 1
                window.toggle_drawer()
                window._wait_with_events(320)
                assert window.drawer_open
                window.close_drawer()
                window._hide_to_tray(show_message=False)
                window._wait_with_events(320)
                window._show_from_tray()
                window._wait_with_events(320)
            report["checks"]["repeated_quick_chat_response_storage_overlay_hide_show"] = True

            image = QImage(32, 32, QImage.Format.Format_ARGB32)
            image.fill(0xFF336699)
            # A memóriavágólap ugyanazt a jelzést adja, mint egy Windows-kivágás.
            # Engedély nélkül még bekapcsolt képfordításnál sem indul küldés.
            window.screen_clip_hotkey_enabled.setChecked(True)
            window.test_clipboard.setImage(image)
            window._wait_with_events(250)
            assert int(window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000)) == report["cycles"]
            assert window.pending_clipboard_payload is None
            # A saját gyorsgomb engedélyét közvetlenül élesítjük; natív
            # billentyűküldés, Windows-kivágó és rendszervágólap nélkül.
            window._arm_screen_clip_hotkey()
            window.test_clipboard.setImage(image)
            window._wait_with_events(250)
            assert window._run_javascript("document.body.dataset.fileCount", timeout_ms=5000) == "1"
            assert int(window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000)) == report["cycles"] + 1
            assert window.test_clipboard.text == "Offline fordítás elkészült."
            window.test_clipboard.setImage(image)
            window._wait_with_events(250)
            assert int(window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000)) == report["cycles"] + 1
            window.screen_clip_hotkey_enabled.setChecked(False)
            report["checks"]["clipboard_requires_screen_clip_hotkey"] = True
            report["checks"]["png_attachment_native_pipeline"] = True

            # Az élő oldalon a felhasználói szerep csak a saját h4.sr-only
            # fejlécből olvasható. A testvér képunit keresési azonosítót kap,
            # a külső wrappernek nincs szerep- vagy üzenetadat-attribútuma.
            # A kép role=button divben van, szöveges buborék nélkül.
            loaded = []
            window.page.loadFinished.connect(loaded.append)
            window.page.setHtml(MODERN_IMAGE_FIXTURE, QUrl("https://chatgpt.com/"))
            deadline = time.monotonic() + 20
            while not loaded and time.monotonic() < deadline:
                window._wait_with_events(30)
            window.page.loadFinished.disconnect(loaded.append)
            assert loaded == [True], "A modern képes offline oldal nem töltődött be."
            window._ensure_automation_ready()
            window.screen_clip_hotkey_enabled.setChecked(True)
            window.test_clipboard.setImage(image)
            window._wait_with_events(250)
            assert window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000) == "0"
            assert window.pending_clipboard_payload is None
            request_ids = []
            for expected_count in (1, 2, 3):
                window._arm_screen_clip_hotkey()
                window.test_clipboard.setImage(image)
                window._wait_with_events(250)
                assert int(window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000)) == expected_count
                assert window._run_javascript("document.body.dataset.fileCount", timeout_ms=5000) == "1"
                assert window._run_javascript("document.body.dataset.promptLength", timeout_ms=5000) == "0"
                assert window._run_javascript("document.body.dataset.finished", timeout_ms=5000) == "true"
                assert window.last_translated_text == "Modern képfordítás elkészült.", window.last_run_status
                assert window.test_clipboard.text == window.last_translated_text
                assert store.load_last_translated_text() == window.last_translated_text
                assert window.translation_result_complete
                assert window.translation_result_request_id == window.latest_translation_request_id
                request_ids.append(window.translation_result_request_id)
                assert not window.browser_interaction_active and not window.clipboard_translation_in_progress
            assert all(request_ids) and len(set(request_ids)) == 3
            modern_user_count = window._run_javascript(
                "document.querySelectorAll('[data-chatgpt-search-unit-key^=\"modern-user-unit-\"] img').length", timeout_ms=5000,
            )
            assert modern_user_count == 3, "Mindhárom szöveg nélküli képkérésnek saját kép kell."
            clickable_image_count = window._run_javascript(
                "document.querySelectorAll('[data-chatgpt-search-unit-key^=\"modern-user-unit-\"] div[role=\"button\"] > img[data-state]').length",
                timeout_ms=5000,
            )
            assert clickable_image_count == 3, "Mindhárom képkérésnek kattintható kép kell."
            assert window._run_javascript(
                "document.querySelectorAll('main [data-conversation-role=\"user\"], main [data-message-author-role=\"user\"]').length",
                timeout_ms=5000,
            ) == 0, "A próba nem támaszkodhat felhasználói szerep-attribútumra."
            window.test_clipboard.setImage(image)
            window._wait_with_events(250)
            assert window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000) == "3"
            window.screen_clip_hotkey_enabled.setChecked(False)
            report["checks"]["role_heading_image_response_binding"] = True
            report["checks"]["clickable_image_response_binding"] = True
            report["checks"]["unmarked_user_heading_image_response_binding"] = True
            report["modernImageRequests"] = 3
            # Az azonos kész szövegű gyors chatnek is új aktuális eredmény kell,
            # miután a szöveg nélküli képek eltérő unitazonosítóval elkészültek.
            window._process_quick_chat_translation("Modern szöveges önteszt: Árvíztűrő /spawn")
            assert window._run_javascript("document.body.dataset.submitCount", timeout_ms=5000) == "4"
            assert window._run_javascript("document.body.dataset.fileCount", timeout_ms=5000) == "0"
            assert int(window._run_javascript("document.body.dataset.promptLength", timeout_ms=5000)) > 0
            assert window._run_javascript("document.body.dataset.finished", timeout_ms=5000) == "true"
            assert window.last_translated_text == "Modern képfordítás elkészült.", window.last_run_status
            assert window.test_clipboard.text == window.last_translated_text
            assert store.load_last_translated_text() == window.last_translated_text
            assert window.translation_result_complete
            assert window.translation_result_request_id == window.latest_translation_request_id
            assert window.translation_result_request_id and window.translation_result_request_id not in request_ids
            assert not window.browser_interaction_active and not window.clipboard_translation_in_progress
            report["checks"]["modern_image_then_text_current_response_storage"] = True
            report["modernTextRequests"] = 1
            assert not window.network_blocker.blocked
            assert not window.registered_hotkeys and window.keyboard_hook_handle is None and window.mouse_hook_handle is None
            report["checks"]["no_network_requests_or_native_hotkeys"] = True

            if model_dir is not None:
                # Helyi, hash-ellenőrzött másolatok: a próba nem tölthet le modellt.
                from PIL import Image, ImageDraw, ImageFont

                service = window.ocr_service
                for asset in service._required_assets():
                    content = (model_dir / asset.filename).read_bytes()
                    if hashlib.sha256(content).hexdigest() != asset.sha256:
                        raise RuntimeError(f"Hibás tesztmodell: {asset.filename}")
                    (service.root_dir / asset.filename).write_bytes(content)
                sample = Image.new("RGB", (550, 120), "white")
                font = ImageFont.truetype("arial.ttf", 64)
                ImageDraw.Draw(sample).text((20, 15), "Hello gamer", font=font, fill="black")
                encoded = io.BytesIO()
                sample.save(encoded, format="PNG")
                rapid = service._extract_with_rapidocr("eredeti", encoded.getvalue())
                rapid_text = rapid[0].text if rapid else ""
                windows_text = service._run_windows_ocr(encoded.getvalue(), "en-US")
                report["ocr"] = {"expected": "Hello gamer", "rapidocr": rapid_text, "windows": windows_text}
                assert rapid_text.strip() == "Hello gamer", "A csomagolt RapidOCR próbája sikertelen."
                assert windows_text.strip() == "Hello gamer", "A csomagolt Windows OCR próbája sikertelen."
                report["checks"]["native_rapidocr_and_windows_inference"] = True
            else:
                report["ocr"] = {"tested": False, "reason": "A --self-test-model-dir nem lett megadva."}
            assert not window.network_blocker.blocked
            assert not window.registered_hotkeys and window.keyboard_hook_handle is None and window.mouse_hook_handle is None
            result = 0
        except Exception:
            report["error"] = traceback.format_exc()
        finally:
            if window is not None:
                try:
                    dispose_window(window)
                    report["checks"]["clean_window_shutdown"] = True
                except Exception:
                    report["shutdownError"] = traceback.format_exc()
                    result = 1
    report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    report["passed"] = result == 0
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    app.quit()
    return result


def run_staging() -> int:
    # A böngésző sütijei csak a memóriában élnek, a fájlok bezáráskor törlődnek.
    app = QApplication([sys.argv[0]])
    # A WebEngine háttérablaka mellett az implicit kilépés elmaradhat.
    app.lastWindowClosed.connect(app.quit)
    with tempfile.TemporaryDirectory(prefix="gamer-translator-live-staging-") as temporary:
        store = SettingsStore(Path(temporary))
        store.save_settings(test_settings(offline=False))
        window = IsolatedWindow(store, offline=False)
        window.show()
        result = app.exec()
        dispose_window(window)
    return result
