"""Betöltési versenyhelyzetek valós Qt jelzésekkel, hálózat nélkül."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtWidgets import QApplication

from gamer_translator import main_window as module
from gamer_translator.main_window import BrowserOperationCancelled, MainWindow


class CancellationSignals(QObject):
    cancelled = Signal()


class DelayedBrowser(QObject):
    loadFinished = Signal(bool)

    def __init__(self, window, url):
        super().__init__()
        self.window = window
        self.current_url = QUrl(url)
        self.finished = False

    def url(self):
        return self.current_url

    def load(self, url):
        self.current_url = url
        QTimer.singleShot(10, self.finish)

    def reload(self):
        QTimer.singleShot(10, self.finish)

    def finish(self):
        self.finished = True
        self.window.page_loading = False
        self.loadFinished.emit(True)


class BrowserLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_navigation_waits_when_load_started_is_still_queued(self):
        for url, reload in (("about:blank", False), ("https://chatgpt.com/", True)):
            with self.subTest(url=url):
                window = SimpleNamespace(
                    settings=SimpleNamespace(page_ready_timeout_ms=100),
                    page_loading=False, browser_interaction_active=False,
                    clipboard_translation_in_progress=False, _set_live_status=Mock(),
                    _is_chatgpt_url=lambda u: MainWindow._is_chatgpt_url(None, u),
                )
                window.browser = DelayedBrowser(window, url)
                window._wait_for_page_load = lambda timeout: MainWindow._wait_for_page_load(window, timeout)
                MainWindow._ensure_chatgpt_page_loaded(window, reload_if_open=reload)
                self.assertTrue(window.browser.finished)
                self.assertFalse(window.page_loading)

    def test_close_cancels_pending_javascript_without_timeout_error(self):
        signal = CancellationSignals()
        browser = Mock()
        browser.url.return_value = QUrl("https://chatgpt.com/")
        window = SimpleNamespace(
            browser=browser, operations_cancelled=False,
            browser_operations_cancelled=signal.cancelled,
            browser_interaction_active=False, clipboard_translation_in_progress=False,
            _is_chatgpt_url=lambda u: MainWindow._is_chatgpt_url(None, u),
        )

        def cancel():
            window.operations_cancelled = True
            signal.cancelled.emit()

        QTimer.singleShot(10, cancel)
        with patch.object(module, "log_event") as log, self.assertRaises(BrowserOperationCancelled):
            MainWindow._run_javascript(window, "42", timeout_ms=2000)
        log.assert_not_called()
        self.assertTrue(window.operations_cancelled)

    def test_close_cancels_pending_navigation(self):
        signal = CancellationSignals()
        window = SimpleNamespace(
            page_loading=True, operations_cancelled=False,
            browser_operations_cancelled=signal.cancelled,
            browser_interaction_active=False, clipboard_translation_in_progress=False,
        )
        window.browser = DelayedBrowser(window, "https://chatgpt.com/")

        def cancel():
            window.operations_cancelled = True
            signal.cancelled.emit()

        QTimer.singleShot(10, cancel)
        with self.assertRaises(BrowserOperationCancelled):
            MainWindow._wait_for_page_load(window, 2000)

    def test_cancelled_operations_do_not_start_new_javascript(self):
        window = SimpleNamespace(operations_cancelled=True, browser=Mock())
        with self.assertRaises(BrowserOperationCancelled):
            MainWindow._run_javascript(window, "42", timeout_ms=2000)
        window.browser.page.assert_not_called()

    def test_cancelled_operations_do_not_start_navigation_or_reload(self):
        for url in ("about:blank", "https://chatgpt.com/"):
            with self.subTest(url=url):
                window = SimpleNamespace(operations_cancelled=True, browser=Mock())
                window.browser.url.return_value = QUrl(url)
                with self.assertRaises(BrowserOperationCancelled):
                    MainWindow._ensure_chatgpt_page_loaded(window, reload_if_open=True)
                window.browser.load.assert_not_called()
                window.browser.reload.assert_not_called()

    def test_close_during_load_finished_injection_is_cancellation(self):
        window = SimpleNamespace(
            operations_cancelled=False, page_loading=True, browser=Mock(),
            _update_browser_origin_label=Mock(), _set_live_status=Mock(),
            _sync_browser_runtime_state=Mock(),
            _ensure_automation_ready=Mock(side_effect=BrowserOperationCancelled()),
        )
        with patch.object(module, "log_event") as log, patch.object(module, "log_exception") as errors:
            MainWindow._handle_load_finished(window, True)
        errors.assert_not_called()
        window._set_live_status.assert_not_called()
        self.assertIn("browser.automation_cancelled", [call.args[0] for call in log.call_args_list])


if __name__ == "__main__":
    unittest.main()
