"""Indulási és OCR események: elkülönítés, hibafolyamat és tartalomvédelem."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QtMsgType

import main
from gamer_translator import diagnostics, ocr_service, self_test
from gamer_translator.ocr_service import OCRAsset, OCRCandidate, OCRService


def records_in(root: Path) -> list[dict]:
    diagnostics.shutdown_diagnostics()
    return [json.loads(line) for line in (root / "logs" / diagnostics.LOG_FILENAME).read_text(encoding="utf-8").splitlines()]


class StartupDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        diagnostics.shutdown_diagnostics()
        self.addCleanup(diagnostics.shutdown_diagnostics)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_normal_startup_records_version_and_shutdown(self):
        with patch.object(main.sys, "argv", ["main.py"]), patch.object(main, "default_app_data_dir", return_value=self.root), patch.object(main, "_run_normal", return_value=0):
            self.assertEqual(main.main(), 0)
        records = records_in(self.root)
        start = next(record for record in records if record["event"] == "app.start")
        stop = next(record for record in records if record["event"] == "app.exit")
        self.assertEqual(start["mode"], "normal")
        self.assertEqual(start["app_version"], main.APP_VERSION)
        self.assertEqual(stop["code"], 0)
        self.assertEqual(stop["result"], "completed")
        self.assertEqual(records[-1]["event"], "diagnostics.session_stopped")

    def test_startup_failure_is_recorded_without_exception_message(self):
        sensitive_message = "private text C:/private/settings.json https://example.invalid/secret"
        with patch.object(main.sys, "argv", ["main.py"]), patch.object(main, "default_app_data_dir", return_value=self.root), patch.object(main, "_run_normal", side_effect=RuntimeError(sensitive_message)):
            self.assertEqual(main.main(), 1)
        records = records_in(self.root)
        failure = next(record for record in records if record["event"] == "app.startup_or_runtime_failed")
        self.assertEqual(failure["error_type"], "RuntimeError")
        self.assertTrue(failure["traceback"])
        self.assertNotIn(sensitive_message, json.dumps(records))
        stop = next(record for record in records if record["event"] == "app.exit")
        self.assertEqual(stop["result"], "nonzero")
        self.assertEqual(stop["level"], "ERROR")

    def test_test_modes_never_initialize_default_profile_diagnostics(self):
        for arguments, mode, runner in ((["--staging"], "staging", "run_staging"), (["--self-test-report", "result.json"], "self_test", "run_self_test")):
            with self.subTest(mode=mode), patch.object(main.sys, "argv", ["main.py", *arguments]), patch.object(main, "default_app_data_dir", side_effect=AssertionError("Éles profil")), patch.object(main, "SettingsStore", side_effect=AssertionError("Éles beállítások")), patch.object(main, "setup_diagnostics", wraps=diagnostics.setup_diagnostics) as setup, patch.object(self_test, runner, return_value=0):
                self.assertEqual(main.main(), 0)
                isolated_root = setup.call_args.args[0]
                self.assertNotEqual(isolated_root, self.root)
                self.assertTrue(isolated_root.name.startswith("gamer-translator-test-diagnostics-"))
                self.assertFalse(isolated_root.exists())

    def test_qt_warning_keeps_only_severity_and_length(self):
        diagnostics.setup_diagnostics(self.root)
        sensitive_message = "Authorization: secret https://chatgpt.com/private C:/private/image.png"
        context = Mock(file="C:/private/source.py", function="private_user_name")
        main._handle_qt_message(QtMsgType.QtWarningMsg, context, sensitive_message)
        records = records_in(self.root)
        warning = next(record for record in records if record["event"] == "qt.message")
        self.assertEqual(warning["level"], "WARNING")
        self.assertEqual(warning["text_length"], len(sensitive_message))
        self.assertEqual(warning["code"], QtMsgType.QtWarningMsg.value)
        self.assertNotIn("secret", json.dumps(records))
        self.assertNotIn("private", json.dumps(records))

    def test_qt_import_failure_records_bootstrap_error_without_dll_path(self):
        sensitive_message = "DLL load failed: C:/private/account/Qt6Core.dll"
        try:
            raise ImportError(sensitive_message)
        except ImportError as error:
            with patch.object(main.sys, "argv", ["main.py"]), patch.object(main, "default_app_data_dir", return_value=self.root):
                self.assertEqual(main._report_qt_import_failure(error), 1)
        records = records_in(self.root)
        failure = next(record for record in records if record["event"] == "app.qt_import_failed")
        self.assertEqual(failure["mode"], "normal")
        self.assertEqual(failure["error_type"], "ImportError")
        self.assertTrue(failure["traceback"])
        self.assertNotIn(sensitive_message, json.dumps(records))
        self.assertEqual(records[-1]["event"], "diagnostics.session_stopped")

    def test_qt_import_failure_test_modes_keep_default_profile_isolated(self):
        for arguments, mode in ((["--staging"], "staging"), (["--self-test-report", "result.json"], "self_test"), (["--self-test-report=result.json"], "self_test")):
            with self.subTest(mode=mode, arguments=arguments), patch.object(main.sys, "argv", ["main.py", *arguments]), patch.object(main, "default_app_data_dir", side_effect=AssertionError("Éles profil")), patch.object(main, "SettingsStore", side_effect=AssertionError("Éles beállítások")), patch.object(main, "setup_diagnostics", wraps=diagnostics.setup_diagnostics) as setup, patch.object(main, "log_exception", wraps=diagnostics.log_exception) as exception:
                self.assertEqual(main._report_qt_import_failure(OSError("private DLL path")), 1)
                setup.assert_called_once()
                isolated_root = setup.call_args.args[0]
                self.assertTrue(isolated_root.name.startswith("gamer-translator-test-diagnostics-"))
                self.assertFalse(isolated_root.exists())
                self.assertEqual(exception.call_args.kwargs["mode"], mode)


class OCRDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        diagnostics.shutdown_diagnostics()
        self.addCleanup(diagnostics.shutdown_diagnostics)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        diagnostics.setup_diagnostics(self.root)
        with patch.object(OCRService, "_resolve_windows_language_tags", return_value=()):
            self.service = OCRService(self.root / "ocr")

    def test_request_correlates_nested_events_without_recognized_text(self):
        request_id = "a" * 32
        sensitive_text = "Private OCR text and username"
        candidate = OCRCandidate(sensitive_text, 1.5, "RapidOCR", "eredeti")

        def collect(*_args, **_kwargs):
            ocr_service._log_ocr_event("ocr.variant_completed", engine="rapidocr", stage="eredeti", count=1)
            return [candidate]

        with patch.object(self.service, "_collect_ranked_candidates", side_effect=collect):
            self.assertEqual(self.service.extract_text_candidates(b"private image pixels", request_id=request_id), (sensitive_text,))
        self.assertIsNone(ocr_service._OCR_REQUEST_ID.get())
        records = records_in(self.root)
        events = [record for record in records if record["event"] in {"ocr.started", "ocr.variant_completed", "ocr.result_ready", "ocr.finished"}]
        self.assertEqual(len(events), 4)
        self.assertTrue(all(record["request_id"] == request_id for record in events))
        self.assertNotIn(sensitive_text, json.dumps(records))
        self.assertNotIn("private image pixels", json.dumps(records))

    def test_failure_keeps_original_exception_and_resets_correlation(self):
        error = ValueError("Private image payload")
        with patch.object(self.service, "_collect_ranked_candidates", side_effect=error):
            with self.assertRaises(ValueError) as caught:
                self.service.extract_text(b"invalid pixels", request_id="b" * 32)
        self.assertIs(caught.exception, error)
        self.assertIsNone(ocr_service._OCR_REQUEST_ID.get())
        records = records_in(self.root)
        failure = next(record for record in records if record["event"] == "ocr.failed")
        self.assertEqual(failure["request_id"], "b" * 32)
        self.assertEqual(failure["error_type"], "ValueError")
        self.assertNotIn("Private image payload", json.dumps(records))

    def test_model_integrity_event_never_records_asset_url_or_file(self):
        payload = b"verified model bytes"
        filename = "private-user-model.onnx"
        (self.service.root_dir / filename).write_bytes(payload)
        asset = OCRAsset(filename, "https://example.invalid/private/model.onnx", hashlib.sha256(payload).hexdigest())
        with patch.object(self.service, "_required_assets", return_value=(asset,)), patch.object(ocr_service.DownloadFile, "run") as download:
            self.service._ensure_assets()
        download.assert_not_called()
        records = records_in(self.root)
        completed = next(record for record in records if record["event"] == "ocr.model_check_completed")
        self.assertEqual(completed["result"], "cached")
        self.assertEqual(completed["attempt"], 1)
        self.assertNotIn(filename, json.dumps(records))
        self.assertNotIn(asset.url, json.dumps(records))


if __name__ == "__main__":
    unittest.main()
