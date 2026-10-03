"""Az aszinkron napló adatvédelmi, forgatási és hibatűrési ellenőrzései."""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gamer_translator import diagnostics as module
from tools import read_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        module.shutdown_diagnostics()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(module.shutdown_diagnostics)

    def records(self) -> list[dict]:
        result = []
        directory = self.root / "logs"
        for path in sorted(directory.glob(f"{module.LOG_FILENAME}*")):
            result.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
        return result

    def flush(self) -> None:
        writer = module._writer
        deadline = time.monotonic() + 3
        while writer is not None and writer.queue.unfinished_tasks:
            if time.monotonic() >= deadline:
                self.fail("A háttéríró nem ürítette ki időben a naplósort.")
            time.sleep(0.005)

    def test_shutdown_flushes_metadata_and_request_identity(self) -> None:
        directory = module.setup_diagnostics(self.root, app_version="5.12")
        self.assertEqual(directory, self.root / "logs")
        self.assertEqual(module.get_log_directory(), directory)
        request_id = uuid.uuid4()
        for index in range(100):
            module.log_event("request.progress", request_id=str(request_id), count=index, action="translate", ready=True)
        module.shutdown_diagnostics()
        records = self.records()
        events = [record for record in records if record["event"] == "request.progress"]
        self.assertEqual(len(events), 100)
        self.assertEqual([event["count"] for event in events], list(range(100)))
        for record in events:
            self.assertEqual(record["request_id"], request_id.hex)
            self.assertEqual(record["app_version"], "5.12")
            self.assertEqual(record["action"], "translate")
            self.assertIs(record["ready"], True)
            self.assertRegex(record["timestamp"], r"[+-]\d\d:\d\d$")
            self.assertRegex(record["session_id"], r"^[a-f0-9]{32}$")
            self.assertIsInstance(record["pid"], int)
            self.assertIsInstance(record["thread_id"], int)
            self.assertGreaterEqual(record["monotonic_ms"], 0)
        self.assertEqual(records[-1]["event"], "diagnostics.session_stopped")
        self.assertIsNone(module.get_log_directory())

    def test_only_explicit_metadata_survives_and_hostile_objects_are_not_stringified(self) -> None:
        class Hostile:
            def __str__(self):
                raise AssertionError("Nem kérhető tartalom a napló számára.")

        module.setup_diagnostics(self.root, app_version="á titkos verzió")
        module.log_event(
            "privacy.probe", request_id="secret-request", level="secret-level",
            prompt="secret-prompt", text="secret-text", translation="secret-translation",
            ocr="secret-ocr", image=b"secret-image", url="https://example.com/private",
            path="C:\\Users\\private-name\\secret", cookie="secret-cookie", token="secret-token",
            console="secret-console", thread_id=999, session_id="fake-session",
            action="szöveg", stage="token with spaces", reason="https://private", code="x" * 65,
            count=math.inf, image_bytes=-math.inf, elapsed_ms=math.nan,
            duration_ms=10**100, image_width=Hostile(), busy=Hostile(),
            text_length=42, source="clipboard", ready=True, gpu_enabled=False,
        )
        module.log_event("titkos esemény", count=1)
        module.shutdown_diagnostics()
        record = next(record for record in self.records() if record["event"] == "privacy.probe")
        self.assertEqual(record["app_version"], "unknown")
        self.assertEqual(record["level"], "INFO")
        self.assertEqual(record["text_length"], 42)
        self.assertEqual(record["source"], "clipboard")
        self.assertIs(record["ready"], True)
        self.assertIs(record["gpu_enabled"], False)
        for key in (
            "request_id", "prompt", "text", "translation", "ocr", "image", "url", "path",
            "cookie", "token", "console", "action", "stage", "reason", "code", "count",
            "image_bytes", "elapsed_ms", "duration_ms", "image_width", "busy",
        ):
            self.assertNotIn(key, record)
        raw = (self.root / "logs" / module.LOG_FILENAME).read_text(encoding="utf-8")
        self.assertNotIn("secret", raw)
        self.assertNotIn("private", raw)
        self.assertNotIn("titkos", raw)

    def test_exception_omits_messages_source_lines_and_external_filenames(self) -> None:
        module.setup_diagnostics(self.root)
        try:
            exec(compile('raise ValueError("secret-message")', "C:\\Users\\private-person\\secret-filename.py", "exec"))
        except ValueError as error:
            module.log_exception("request.failed", error, request_id=uuid.uuid4().hex, stage="response", error_type="wrong")
        module.shutdown_diagnostics()
        record = next(record for record in self.records() if record["event"] == "request.failed")
        self.assertEqual(record["error_type"], "ValueError")
        self.assertEqual(record["level"], "ERROR")
        self.assertEqual(record["stage"], "response")
        self.assertTrue(record["traceback"])
        self.assertEqual(set(record["traceback"][-1]), {"file", "function", "line"})
        self.assertEqual(record["traceback"][-1]["file"], "external")
        raw = json.dumps(record)
        self.assertNotIn("secret", raw)
        self.assertNotIn("private-person", raw)
        self.assertNotIn("raise ValueError", raw)

    def test_response_binding_metadata_survives_writer_reader_and_formatting(self) -> None:
        request_id = uuid.uuid4().hex
        fields = {
            "assistant_count": 2,
            "user_count": 1,
            "user_role_candidates": 2,
            "clickable_image_candidates": 1,
            "text_length": 29,
            "elapsed_ms": 6000.5,
            "pending": False,
            "stable": True,
            "fresh": False,
            "request_user_bound": True,
            "last_user_matches_request": True,
            "response_user_matches_request": False,
            "assistant_identity_new": True,
            "user_role_source": "heading_role",
            "rejection_reason": "response_user_mismatch",
        }
        private_fields = {
            "message_id": "private-user-message-1",
            "assistant_identity": "private-assistant-message-2",
            "response_user_id": "private-user-message-1",
            "request_user_id": "private-user-message-1",
            "last_user_id": "private-user-message-1",
            "text": "private translation text",
            "token": "private-access-token",
            "url": "https://private.example/conversation",
        }
        module.setup_diagnostics(self.root)
        module.log_event("page.response.snapshot", request_id=request_id, **fields, **private_fields)
        module.shutdown_diagnostics()
        record = next(record for record in self.records() if record["event"] == "page.response.snapshot")
        self.assertEqual(record["request_id"], request_id)
        stats = read_diagnostics.ReadStats()
        read_record = next(record for record in read_diagnostics.iter_records(self.root / "logs", stats)
                           if record["event"] == "page.response.snapshot")
        self.assertEqual(stats.skipped_lines, 0)
        for candidate in (record, read_record):
            for key, value in fields.items():
                with self.subTest(source="writer" if candidate is record else "reader", field=key):
                    self.assertEqual(candidate[key], value)
                    self.assertIs(type(candidate[key]), type(value))
            for key in private_fields:
                self.assertNotIn(key, candidate)
        rendered = read_diagnostics.format_record(read_record)
        for key, value in fields.items():
            expected = str(value).lower() if type(value) is bool else str(value)
            self.assertIn(f"{key}={expected}", rendered)
        raw = (self.root / "logs" / module.LOG_FILENAME).read_text(encoding="utf-8")
        self.assertNotIn("private", raw + rendered)

    def test_response_binding_metadata_rejects_wrong_types_and_content(self) -> None:
        bool_fields = (
            "request_user_bound", "last_user_matches_request", "response_user_matches_request",
            "assistant_identity_new",
        )
        for key in bool_fields:
            for value in (0, 1, "true", "private-message-id", None, [], {}):
                with self.subTest(field=key, value=value):
                    self.assertEqual(module._metadata({key: value}), {})
        for key in ("user_role_source", "rejection_reason"):
            for value in (
                True, 42, None, [], {}, "private response text", "https://private.example", "x" * 65,
                "private_user_id", "private-access-token", "9dc3f0d1-f983-4b65-80b5-ab5e6da4265b",
            ):
                with self.subTest(field=key, value=value):
                    self.assertEqual(module._metadata({key: value}), {})
        expected_values = {
            "user_role_source": (
                "none", "message_author", "user_bubble", "conversation_role", "aria_role", "heading_role", "role_conflict",
            ),
            "rejection_reason": (
                "none", "request_user_unbound", "last_user_mismatch", "response_user_mismatch",
                "assistant_identity_old", "assistant_text_missing", "assistant_text_transient", "assistant_pending",
            ),
        }
        for key, values in expected_values.items():
            for value in values:
                with self.subTest(field=key, value=value):
                    self.assertEqual(module._metadata({key: value}), {key: value})
        for key in ("assistant_count", "user_count", "text_length", "user_role_candidates", "clickable_image_candidates"):
            for value in (True, "2", None, [], {}, math.inf, math.nan):
                with self.subTest(field=key, value=value):
                    self.assertEqual(module._metadata({key: value}), {})

    def test_same_setup_is_idempotent_and_new_root_starts_a_new_session(self) -> None:
        module.setup_diagnostics(self.root, app_version="5.12")
        first = module._writer
        module.setup_diagnostics(self.root, app_version="5.12")
        self.assertIs(module._writer, first)
        second_root = self.root / "second"
        module.setup_diagnostics(second_root, app_version="5.12")
        self.assertFalse(first.thread.is_alive())
        self.assertNotEqual(first.session_id, module._writer.session_id)
        module.shutdown_diagnostics()
        self.assertTrue((second_root / "logs" / module.LOG_FILENAME).is_file())

    def test_rotation_keeps_at_most_five_backups_and_complete_json_lines(self) -> None:
        with patch.object(module, "MAX_LOG_BYTES", 1500):
            module.setup_diagnostics(self.root, app_version="5.12")
            for index in range(150):
                module.log_event("rotation.progress", count=index, stage="attachment", duration_ms=index / 10)
            module.shutdown_diagnostics()
        files = list((self.root / "logs").glob(f"{module.LOG_FILENAME}*"))
        self.assertEqual(len(files), 6)
        self.assertTrue(all(path.stat().st_size <= 1500 for path in files))
        records = self.records()
        self.assertTrue(records)
        self.assertIn(149, [record.get("count") for record in records])
        self.assertFalse((self.root / "logs" / f"{module.LOG_FILENAME}.6").exists())

    def test_full_queue_does_not_wait_for_disk_and_reports_loss(self) -> None:
        started = threading.Event()
        release = threading.Event()
        original = module._BackgroundWriter._append

        def slow_append(writer, record):
            if not started.is_set():
                started.set()
                release.wait(3)
            original(writer, record)

        with patch.object(module, "QUEUE_CAPACITY", 3), patch.object(module._BackgroundWriter, "_append", slow_append):
            module.setup_diagnostics(self.root)
            self.assertTrue(started.wait(1))
            before = time.monotonic()
            for index in range(100):
                module.log_event("queue.probe", count=index)
            self.assertLess(time.monotonic() - before, 0.5)
            self.assertGreater(module._writer.dropped, 0)
            release.set()
            module.shutdown_diagnostics()
        drops = [record["dropped_count"] for record in self.records() if record["event"] == "diagnostics.queue_dropped"]
        self.assertGreaterEqual(sum(drops), 97)

    def test_disk_failure_does_not_raise_and_recovery_is_logged(self) -> None:
        (self.root / "logs").write_text("not-a-directory", encoding="utf-8")
        module.setup_diagnostics(self.root)
        module.log_event("disk.before", count=1)
        self.flush()
        self.assertGreater(module._writer.write_failures, 0)
        (self.root / "logs").unlink()
        module.log_event("disk.after", count=2)
        module.shutdown_diagnostics()
        records = self.records()
        self.assertTrue(any(record["event"] == "disk.after" for record in records))
        recovery = next(record for record in records if record["event"] == "diagnostics.write_recovered")
        self.assertGreaterEqual(recovery["write_failures"], 2)

    def test_hooks_preserve_previous_handlers_and_handler_errors_do_not_escape(self) -> None:
        previous_sys = Mock(side_effect=RuntimeError("secret-handler-failure"))
        previous_thread = Mock(side_effect=RuntimeError("secret-handler-failure"))
        with patch.object(sys, "excepthook", previous_sys), patch.object(threading, "excepthook", previous_thread):
            module.setup_diagnostics(self.root)
            module.install_exception_hooks()
            module.install_exception_hooks()
            error = ValueError("secret-exception")
            args = SimpleNamespace(exc_type=ValueError, exc_value=error, exc_traceback=None, thread=None)
            sys.excepthook(ValueError, error, None)
            threading.excepthook(args)
            previous_sys.assert_called_once_with(ValueError, error, None)
            previous_thread.assert_called_once_with(args)
            module.shutdown_diagnostics()
            self.assertIs(sys.excepthook, previous_sys)
            self.assertIs(threading.excepthook, previous_thread)
        events = {record["event"] for record in self.records()}
        self.assertIn("python.unhandled_exception", events)
        self.assertIn("python.thread_exception", events)
        self.assertNotIn("secret", json.dumps(self.records()))

    def test_resource_snapshot_contains_only_allowed_finite_numbers(self) -> None:
        first = module.resource_snapshot()
        second = module.resource_snapshot()
        self.assertGreaterEqual(first["cpu_count"], 1)
        self.assertIn("process_cpu_seconds", second)
        self.assertIn("process_cpu_percent", second)
        self.assertEqual(second, module._metadata(second))
        self.assertTrue(all(type(value) in (int, float) and math.isfinite(value) for value in second.values()))
        if sys.platform == "win32":
            self.assertGreater(second["process_memory_bytes"], 0)
            self.assertGreater(second["system_memory_total_bytes"], second["system_memory_available_bytes"])

    def test_invalid_renderer_pid_is_ignored_without_converting_private_values(self) -> None:
        class Hostile:
            def __int__(self):
                raise AssertionError("Nem alakítható át felhasználói adat PID-vé.")

        for pid in (0, -1, 2**40, True, "private-process-id", None, Hostile()):
            with self.subTest(pid_type=type(pid).__name__):
                snapshot = module.resource_snapshot(renderer_pid=pid)
                self.assertFalse(any(key.startswith("renderer_") for key in snapshot))
                self.assertIn("process_cpu_seconds", snapshot)
                self.assertEqual(snapshot, module._metadata(snapshot))
        snapshot = module.resource_snapshot(renderer_pid=0xFFFFFFFF)
        self.assertNotIn("renderer_memory_bytes", snapshot)

    @unittest.skipUnless(sys.platform == "win32", "A renderer mérése Windows API-t használ.")
    def test_renderer_memory_and_cpu_are_read_from_the_requested_process(self) -> None:
        module.resource_snapshot(renderer_pid=os.getpid())
        snapshot = module.resource_snapshot(renderer_pid=os.getpid())
        self.assertEqual(snapshot["renderer_pid"], os.getpid())
        self.assertGreater(snapshot["renderer_memory_bytes"], 0)
        self.assertGreater(snapshot["renderer_private_memory_bytes"], 0)
        self.assertGreaterEqual(snapshot["renderer_cpu_seconds"], 0)
        self.assertGreaterEqual(snapshot["renderer_cpu_percent"], 0)
        self.assertLessEqual(snapshot["renderer_cpu_percent"], 100)
        self.assertEqual(snapshot, module._metadata(snapshot))

    @unittest.skipUnless(sys.platform == "win32", "A renderer mérése Windows API-t használ.")
    def test_renderer_query_failure_still_closes_handle_and_preserves_main_measurement(self) -> None:
        fake_kernel = SimpleNamespace(
            GetCurrentProcess=Mock(return_value=1),
            GlobalMemoryStatusEx=Mock(return_value=False),
            K32GetProcessMemoryInfo=Mock(side_effect=[True, OSError("private-error")]),
            OpenProcess=Mock(return_value=42),
            CloseHandle=Mock(return_value=True),
            GetProcessTimes=Mock(return_value=False),
        )
        with patch.object(module.ctypes, "WinDLL", return_value=fake_kernel):
            snapshot = module.resource_snapshot(renderer_pid=123)
        fake_kernel.OpenProcess.assert_called_once_with(0x1010, False, 123)
        fake_kernel.CloseHandle.assert_called_once_with(42)
        self.assertIn("process_cpu_seconds", snapshot)
        self.assertNotIn("private-error", json.dumps(snapshot))

    def test_renderer_cpu_history_is_bounded_and_pid_reuse_restarts_measurement(self) -> None:
        with patch.object(module, "_renderer_cpu_samples", module.OrderedDict()):
            for pid in range(30):
                module._renderer_cpu_percent(pid, 100, 1.0, 10.0, 4)
            self.assertEqual(len(module._renderer_cpu_samples), 16)
            self.assertIsNone(module._renderer_cpu_percent(29, 101, 0.1, 11.0, 4))
            self.assertEqual(module._renderer_cpu_percent(29, 101, 0.3, 12.0, 4), 5.0)


if __name__ == "__main__":
    unittest.main()
