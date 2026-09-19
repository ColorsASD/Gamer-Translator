"""Háttérfeldolgozás alatti GUI-események, újrabelépés és kilépés regressziói."""
from __future__ import annotations

import os
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow


class BackgroundTaskTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.release_worker = threading.Event()
        self.addCleanup(self.executor.shutdown, wait=True, cancel_futures=True)
        self.addCleanup(self.release_worker.set)
        self.window = SimpleNamespace(
            background_executor=self.executor,
            current_background_future=None,
            browser_interaction_active=True,
            clipboard_translation_in_progress=True,
            _touch_browser_interaction_heartbeat=Mock(),
            _touch_clipboard_translation_heartbeat=Mock(),
            _set_live_status=Mock(),
            _run_low_priority_background_task=lambda task: task(),
        )
        for name in ("_run_in_background_with_events", "_shutdown_background_executor", "_wait_with_events"):
            setattr(self.window, name, getattr(MainWindow, name).__get__(self.window, SimpleNamespace))

    def timer(self, interval_ms, callback):
        timer = QTimer()
        timer.setInterval(interval_ms)
        timer.timeout.connect(callback)
        self.addCleanup(timer.stop)
        timer.start()
        return timer

    def test_gui_timers_run_while_worker_waits_without_sleeping_gui_thread(self):
        ticks = []
        gui_thread = threading.get_ident()

        def tick():
            ticks.append(threading.get_ident())
            if len(ticks) >= 3:
                self.release_worker.set()

        def task():
            if not self.release_worker.wait(2):
                raise TimeoutError("A GUI-időzítő nem szolgálta ki a háttérfeladatot.")
            return threading.get_ident()

        timer = self.timer(5, tick)
        with patch.object(module.time, "sleep", side_effect=AssertionError("A GUI-szál nem aludhat.")):
            worker_thread = self.window._run_in_background_with_events(task, progress_message="Feldolgozás.")
        timer.stop()
        self.assertNotEqual(worker_thread, gui_thread)
        self.assertGreaterEqual(len(ticks), 3)
        self.assertEqual(set(ticks), {gui_thread})
        self.assertIsNone(self.window.current_background_future)
        self.window._touch_browser_interaction_heartbeat.assert_called()
        self.window._touch_clipboard_translation_heartbeat.assert_called()
        self.window._set_live_status.assert_called_with("Feldolgozás.")

    def test_worker_exception_propagates_and_clears_current_future(self):
        def task():
            raise ValueError("OCR-hiba")

        with self.assertRaisesRegex(ValueError, "OCR-hiba"):
            self.window._run_in_background_with_events(task)
        self.assertIsNone(self.window.current_background_future)
        self.assertEqual(self.window._run_in_background_with_events(lambda: "újra kész"), "újra kész")

    def test_event_callback_cannot_reenter_and_replace_active_worker(self):
        observed = []
        nested_task = Mock()

        def reenter():
            timer.stop()
            current_future = self.window.current_background_future
            try:
                self.window._run_in_background_with_events(nested_task)
            except RuntimeError as error:
                observed.append(str(error))
            observed.append(self.window.current_background_future is current_future)
            self.release_worker.set()

        timer = self.timer(0, reenter)
        self.assertTrue(self.window._run_in_background_with_events(lambda: self.release_worker.wait(2)))
        self.assertEqual(observed, ["Már fut egy háttérben végzett feldolgozás.", True])
        nested_task.assert_not_called()
        self.assertIsNone(self.window.current_background_future)

    def test_shutdown_waits_for_running_worker_while_servicing_gui(self):
        started = threading.Event()
        ticks = []

        def task():
            started.set()
            return self.release_worker.wait(2)

        def tick():
            ticks.append(True)
            if len(ticks) >= 3:
                self.release_worker.set()

        future = self.executor.submit(task)
        self.window.current_background_future = future
        self.assertTrue(started.wait(2))
        timer = self.timer(5, tick)
        with patch.object(module.time, "sleep", side_effect=AssertionError("A GUI-szál nem aludhat.")):
            self.window._shutdown_background_executor()
        timer.stop()
        self.assertTrue(future.result())
        self.assertGreaterEqual(len(ticks), 3)
        with self.assertRaises(RuntimeError):
            self.executor.submit(lambda: None)

    def test_shutdown_from_gui_callback_preserves_active_future_until_worker_finishes(self):
        observations = []
        started = threading.Event()

        def task():
            started.set()
            return self.release_worker.wait(2)

        def shutdown():
            if not started.is_set():
                return
            close_timer.stop()
            future = self.window.current_background_future
            QTimer.singleShot(5, self.release_worker.set)
            self.window._shutdown_background_executor()
            observations.extend((future.done(), self.window.current_background_future is future))

        close_timer = self.timer(0, shutdown)
        self.assertTrue(self.window._run_in_background_with_events(task))
        self.assertEqual(observations, [True, True])
        self.assertIsNone(self.window.current_background_future)


if __name__ == "__main__":
    unittest.main()
