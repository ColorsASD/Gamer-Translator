"""Az önteszt és a staging profil elkülönítése, valódi rendszerműveletek nélkül."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

import main
from gamer_translator import main_window
from gamer_translator import self_test
from gamer_translator.settings_store import SettingsStore


class TestModeDispatchTests(unittest.TestCase):
    def test_staging_dispatch_never_opens_default_profile_or_singleton(self):
        with patch.object(main.sys, "argv", ["main.py", "--staging"]), patch.dict(os.environ), patch.object(main, "SettingsStore") as store, patch.object(main, "SingleInstanceController") as singleton, patch.object(self_test, "run_staging", return_value=42) as run:
            self.assertEqual(main.main(), 42)
            store.assert_not_called()
            singleton.assert_not_called()
            run.assert_called_once_with()

    def test_self_test_dispatch_uses_offscreen_and_explicit_report(self):
        with patch.object(main.sys, "argv", ["main.py", "--self-test-report", "result.json", "--self-test-duration", "2"]), patch.dict(os.environ), patch.object(main, "SettingsStore") as store, patch.object(main, "SingleInstanceController") as singleton, patch.object(self_test, "run_self_test", return_value=0) as run:
            self.assertEqual(main.main(), 0)
            self.assertEqual(os.environ["QT_QPA_PLATFORM"], "offscreen")
            run.assert_called_once_with(Path("result.json"), 2, None)
            store.assert_not_called()
            singleton.assert_not_called()

    def test_invalid_test_mode_arguments_fail_before_profile_access(self):
        for arguments in (["--self-test-duration", "0"], ["--self-test-duration", "3601"], ["--staging", "--self-test-report", "result.json"], ["--self-test-model-dir", "models"], ["--staging", "--self-test-model-dir", "models"]):
            with self.subTest(arguments=arguments), patch.object(main.sys, "argv", ["main.py", *arguments]), patch.object(main, "SettingsStore") as store, contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main.main()
                self.assertEqual(error.exception.code, 2)
                store.assert_not_called()


class IsolatedWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_live_staging_defaults_disable_automatic_system_actions(self):
        settings = self_test.test_settings(offline=False)
        self.assertFalse(settings.monitoring_enabled)
        self.assertFalse(settings.ocr_text_from_clipboard_image)
        self.assertFalse(settings.type_out_hotkey_enabled)
        self.assertFalse(settings.screen_clip_hotkey_enabled)
        self.assertFalse(settings.quick_chat_hotkey_enabled)

    def test_offline_window_never_reads_system_clipboard_and_closes_cleanly(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(Path(directory))
            store.save_settings(self_test.test_settings(offline=True))
            with patch.object(main_window.QGuiApplication, "clipboard", side_effect=AssertionError("Rendszervágólap elérése")), patch.object(main_window.user32, "SetWindowsHookExW") as hook, patch.object(main_window.user32, "SendInput") as send, patch.object(main_window, "SettingsStore", side_effect=AssertionError("Normál profil megnyitása")):
                window = self_test.IsolatedWindow(store, offline=True)
                self.app.processEvents()
                objects = [window, window.page, window.profile, window.browser, window.browser_background_host, window.translation_overlay, window.quick_chat_overlay]
                try:
                    self.assertTrue(window.profile.isOffTheRecord())
                    self.assertIs(window.clipboard, window.test_clipboard)
                    self.assertEqual(window.ocr_service.root_dir, store.root_dir / "ocr")
                    self.assertIsNone(window.tray_icon)
                    self.assertFalse(window.reset_defaults_button.isEnabled())
                    self.assertEqual(window.registered_hotkeys, {})
                    window.test_clipboard.setText("Csak memóriában tárolt teszt.")
                    self.assertTrue(window.close())
                    with self.assertRaises(RuntimeError):
                        window.background_executor.submit(lambda: None)
                finally:
                    # A staging futtató az ablak bezárása után még egyszer felszabadítja az objektumokat.
                    self_test.dispose_window(window)
                self.assertTrue(all(not isValid(obj) for obj in objects))
                hook.assert_not_called()
                send.assert_not_called()

    def test_offline_interceptor_blocks_remote_and_file_requests(self):
        blocker = self_test.BlockNetwork(None)
        for url in ("https://chatgpt.com/", "http://localhost/", "file:///C:/private.txt", "ftp://example.invalid/data"):
            with self.subTest(url=url):
                request = Mock()
                request.requestUrl.return_value = QUrl(url)
                blocker.interceptRequest(request)
                request.block.assert_called_once_with(True)
        self.assertEqual(len(blocker.blocked), 4)

    def test_staging_event_loop_exits_on_close_and_removes_temporary_profile(self):
        # Külön folyamat kell: a többi Qt teszt megosztott QApplication példányt használ.
        script = '''
import json
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWidgets import QApplication
from gamer_translator import self_test
state = {"fallback": False}
original = self_test.IsolatedWindow
class ProbeWindow(original):
    def __init__(self, store, *, offline):
        super().__init__(store, offline=True)
        state["temporary"] = str(store.root_dir)
        self.page.setHtml(self_test.FIXTURE, QUrl("https://chatgpt.com/"))
        QTimer.singleShot(300, self.close)
        QTimer.singleShot(1500, fallback)
def fallback():
    state["fallback"] = True
    QApplication.instance().quit()
self_test.IsolatedWindow = ProbeWindow
state["result"] = self_test.run_staging()
state["temporary_removed"] = not Path(state["temporary"]).exists()
print(json.dumps(state))
'''
        result = subprocess.run([sys.executable, "-X", "utf8", "-c", script],
                                cwd=Path(__file__).resolve().parents[1],
                                env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = json.loads(result.stdout)
        self.assertEqual(state["result"], 0)
        self.assertFalse(state["fallback"], "Az ablak bezárult, de a Qt eseményhurok tovább futott.")
        self.assertTrue(state["temporary_removed"])


if __name__ == "__main__":
    unittest.main()
