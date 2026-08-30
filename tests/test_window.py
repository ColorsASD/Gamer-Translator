"""A natív ablak biztonsági regressziói; nincs éles profil vagy billentyűküldés."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QUrl
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript, QWebEngineSettings

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow, TranslationOverlay
from gamer_translator.settings_store import SettingsStore


class NativeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_only_trusted_https_origins_are_accepted(self):
        for url in ("https://chatgpt.com/", "https://chat.openai.com/c/123", "https://CHATGPT.com:443/"):
            with self.subTest(url=url):
                self.assertTrue(MainWindow._is_chatgpt_url(None, url))
        for url in (
            "", "http://chatgpt.com/", "ftp://chatgpt.com/", "https://chatgpt.com:444/",
            "https://chatgpt.com.evil.invalid/", "https://evil.invalid/chatgpt.com",
            "https://user:pass@chatgpt.com/", "https://chatgpt.com@evil.invalid/",
            "https://[broken", "https://chatgpt.com:invalid/", "file:///tmp/chatgpt.com",
        ):
            with self.subTest(url=url):
                self.assertFalse(MainWindow._is_chatgpt_url(None, url))

    def test_javascript_rejects_external_page_before_execution(self):
        browser = Mock()
        browser.url.return_value = QUrl("https://example.invalid/")
        window = SimpleNamespace(browser=browser, _is_chatgpt_url=lambda u: MainWindow._is_chatgpt_url(None, u))
        with self.assertRaisesRegex(RuntimeError, "HTTPS"):
            MainWindow._run_javascript(window, "42", timeout_ms=1000)
        browser.page.assert_not_called()

    def test_javascript_uses_isolated_world_and_handles_immediate_callback(self):
        browser = Mock()
        browser.url.return_value = QUrl("https://chatgpt.com/")
        browser.page.return_value.runJavaScript.side_effect = lambda code, world, callback: callback(42)
        window = SimpleNamespace(browser=browser, _is_chatgpt_url=lambda u: MainWindow._is_chatgpt_url(None, u))
        self.assertEqual(MainWindow._run_javascript(window, "42", timeout_ms=1000), 42)
        code, world, _ = browser.page.return_value.runJavaScript.call_args.args
        self.assertEqual(world, QWebEngineScript.ScriptWorldId.ApplicationWorld)
        self.assertIn("location.protocol === 'https:'", code)
        self.assertIn("window.top === window", code)

    def test_origin_display_omits_credentials_and_tokens(self):
        label = QLabel()
        window = SimpleNamespace(current_url_label=label, _is_chatgpt_url=lambda u: MainWindow._is_chatgpt_url(None, u))
        MainWindow._update_browser_origin_label(window, QUrl("https://user:secret@example.invalid/path?token=secret#secret"))
        self.assertIn("https://example.invalid", label.text())
        self.assertNotIn("secret", label.text())
        self.assertIn("automatizálás kikapcsolva", label.text())

    def test_translation_overlay_treats_markup_as_text(self):
        overlay = TranslationOverlay()
        self.assertEqual(overlay.label.textFormat(), Qt.TextFormat.PlainText)
        overlay.deleteLater()

    def test_browser_does_not_grant_global_clipboard_or_local_file_access(self):
        with tempfile.TemporaryDirectory() as directory:
            class Window(QMainWindow):
                _set_web_attribute = MainWindow._set_web_attribute
                def _handle_load_started(self):
                    pass
                def _handle_load_finished(self, ok):
                    pass
            window = Window()
            window.store = SimpleNamespace(browser_dir=Path(directory))
            # A valódi beállítási kód memóriaalapú profilt kap, lemezes munkamenet nélkül.
            with patch.object(module, "QWebEngineProfile", wraps=QWebEngineProfile) as profile_type:
                profile_type.side_effect = lambda name, parent: QWebEngineProfile(parent)
                profile_type.HttpCacheType = QWebEngineProfile.HttpCacheType
                profile_type.PersistentCookiesPolicy = QWebEngineProfile.PersistentCookiesPolicy
                MainWindow._build_browser(window)
            for name in ("JavascriptCanPaste", "JavascriptCanAccessClipboard", "LocalContentCanAccessFileUrls", "LocalContentCanAccessRemoteUrls"):
                with self.subTest(name=name):
                    self.assertFalse(window.browser.settings().testAttribute(getattr(QWebEngineSettings.WebAttribute, name)))
            window.browser.deleteLater()
            window.page.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            window.profile.deleteLater()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_full_window_constructs_with_isolated_data_and_no_external_actions(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory, patch.dict(os.environ, {"LOCALAPPDATA": directory}), patch.object(MainWindow, "open_chatgpt"), patch.object(MainWindow, "_register_hotkeys"), patch.object(MainWindow, "_build_tray_icon"), patch.object(MainWindow, "_refresh_system_keep_awake"), patch.object(MainWindow, "_restore_system_sleep_state"), patch.object(MainWindow, "_current_clipboard_signature", return_value=""):
            store = SettingsStore()
            settings = store.load_settings()
            settings.monitoring_enabled = False
            store.save_settings(settings)
            window = MainWindow()
            self.app.processEvents()
            window._update_browser_origin_label(QUrl("https://chatgpt.com/"))
            self.assertEqual(window.current_url_label.text(), "ChatGPT: https://chatgpt.com")
            self.assertGreaterEqual(window.page_ready_timeout_ms.minimum(), 1000)
            self.assertGreaterEqual(window.centralWidget().layout().indexOf(window.current_url_label), 0)
            window.exit_requested = True
            window.close()
            for widget in (window.browser, window.page, window.browser_background_host, window.translation_overlay, window.quick_chat_overlay):
                widget.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            window.profile.deleteLater()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_modifier_timeout_does_not_type(self):
        with patch.object(module.time, "monotonic", side_effect=[0, 0.1, 2]), patch.object(module.time, "sleep"), patch.object(module.user32, "GetAsyncKeyState", return_value=0x8000):
            self.assertFalse(MainWindow._wait_for_modifier_release(None))

    def test_typing_stops_when_foreground_changes(self):
        window = SimpleNamespace(last_translated_text="ab", _set_live_status=Mock())
        with patch.object(module.user32, "GetForegroundWindow", side_effect=[1, 1, 2]), patch.object(module.user32, "SendInput", return_value=2) as send, patch.object(module.time, "sleep"):
            self.assertFalse(MainWindow._type_cached_text_via_hotkey(window))
        self.assertEqual(send.call_count, 1)
        self.assertIn("aktív ablak", window._set_live_status.call_args.args[0])

    def test_typing_rejects_window_switch_during_modifier_wait(self):
        window = SimpleNamespace(hotkey_errors={}, last_translated_text="a", _set_live_status=Mock(),
                                 settings=SimpleNamespace(type_out_hotkey="Alt+V"), _wait_for_modifier_release=Mock(return_value=True))
        window._type_cached_text_via_hotkey = lambda **kwargs: MainWindow._type_cached_text_via_hotkey(window, **kwargs)
        with patch.object(module.user32, "GetForegroundWindow", side_effect=[111, 222]), patch.object(module.user32, "SendInput") as send:
            MainWindow._trigger_type_out_hotkey(window)
        send.assert_not_called()
        self.assertIn("aktív ablak", window._set_live_status.call_args.args[0])

    def test_typing_keeps_activation_window_after_modifier_release(self):
        window = SimpleNamespace(hotkey_errors={}, last_translated_text="a", _set_live_status=Mock(),
                                 settings=SimpleNamespace(type_out_hotkey="Alt+V"), _wait_for_modifier_release=Mock(return_value=True))
        window._type_cached_text_via_hotkey = lambda **kwargs: MainWindow._type_cached_text_via_hotkey(window, **kwargs)
        with patch.object(module.user32, "GetForegroundWindow", return_value=111), patch.object(module.user32, "SendInput", return_value=2) as send, patch.object(module.time, "sleep"):
            MainWindow._trigger_type_out_hotkey(window)
        send.assert_called_once()
        self.assertIn("begépelve", window._set_live_status.call_args.args[0])

    def test_typing_never_retargets_when_activation_has_no_foreground(self):
        window = SimpleNamespace(hotkey_errors={}, last_translated_text="a", _set_live_status=Mock(),
                                 _wait_for_modifier_release=Mock(), _type_cached_text_via_hotkey=Mock())
        with patch.object(module.user32, "GetForegroundWindow", return_value=None):
            MainWindow._trigger_type_out_hotkey(window)
        window._wait_for_modifier_release.assert_not_called()
        window._type_cached_text_via_hotkey.assert_not_called()

    def test_typing_reports_rejected_native_input(self):
        window = SimpleNamespace(last_translated_text="a", _set_live_status=Mock())
        with patch.object(module.user32, "GetForegroundWindow", return_value=1), patch.object(module.user32, "SendInput", return_value=0):
            self.assertFalse(MainWindow._type_cached_text_via_hotkey(window))

    def test_unicode_keyboard_inputs_support_hungarian_and_emoji(self):
        for text in ("ő", "ű", "🎮"):
            with self.subTest(text=text):
                self.assertGreaterEqual(len(module.build_character_inputs(text)), 2)

    def test_partial_native_input_releases_synthetic_keys(self):
        window = SimpleNamespace(last_translated_text="A", _set_live_status=Mock())
        with patch.object(module.user32, "GetForegroundWindow", return_value=1), patch.object(module.user32, "SendInput", side_effect=[1, 2]) as send:
            self.assertFalse(MainWindow._type_cached_text_via_hotkey(window))
        self.assertEqual(send.call_count, 2)
        count, releases, _ = send.call_args.args
        self.assertGreater(count, 0)
        self.assertTrue(all(entry.ki.dwFlags & module.KEYEVENTF_KEYUP for entry in releases))

    def test_manual_actions_do_not_reenter_active_delivery(self):
        for method in (MainWindow.open_chatgpt, MainWindow.send_prompt_now):
            with self.subTest(method=method.__name__):
                window = SimpleNamespace(browser_interaction_active=True, clipboard_translation_in_progress=False, _set_live_status=Mock())
                method(window)
                window._set_live_status.assert_called_once()

    def test_clipboard_is_deferred_during_manual_delivery(self):
        window = SimpleNamespace(clipboard_translation_in_progress=False, browser_interaction_active=True, clipboard_debounce_timer=Mock())
        MainWindow._poll_clipboard(window)
        window.clipboard_debounce_timer.start.assert_called_once()

    def test_oversized_clipboard_image_is_rejected_before_encoding(self):
        image = Mock()
        image.isNull.return_value = False
        image.width.return_value = 10000
        image.height.return_value = 10000
        window = SimpleNamespace(clipboard=SimpleNamespace(image=lambda: image), _set_live_status=Mock())
        self.assertIsNone(MainWindow._read_clipboard_image_payload(window))
        image.save.assert_not_called()

    def test_followup_identifier_is_serialized_as_data(self):
        identifier = 'id"];window.injected=true;//'
        window = SimpleNamespace(response_followup_progress_call_id=identifier, response_followup_timer=Mock(), _run_javascript=Mock())
        MainWindow._stop_response_followup_polling(window)
        script = window._run_javascript.call_args.args[0]
        self.assertIn(f"progressBucket[{json.dumps(identifier)}]", script)

    def test_malformed_followup_progress_does_not_crash(self):
        for payload in ("[]", '{"seq":"invalid"}', "null"):
            with self.subTest(payload=payload):
                window = SimpleNamespace(response_followup_progress_call_id="test", response_followup_started_monotonic=0, response_followup_last_activity_monotonic=0, _run_javascript=Mock(return_value=payload))
                MainWindow._poll_response_followup_progress(window)

    def test_restart_preserves_spaces_and_quotes_in_arguments(self):
        command = [r"C:\Program Files\Python\python.exe", r"C:\Saját mappa\main.py", "two words", 'embedded"quote']
        window = SimpleNamespace(_powershell_literal=lambda value: MainWindow._powershell_literal(None, value))
        with tempfile.TemporaryDirectory() as directory, patch.object(module.tempfile, "gettempdir", return_value=directory), patch.object(module.subprocess, "Popen") as launch:
            MainWindow._schedule_windows_restart(window, command)
            script = next(Path(directory).glob("*.ps1")).read_text(encoding="utf-8-sig")
            expected = window._powershell_literal(subprocess.list2cmdline(command[1:]))
            self.assertIn(f"$StartProcessArgs.ArgumentList = {expected}", script)
            self.assertIn("Hidden", launch.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
