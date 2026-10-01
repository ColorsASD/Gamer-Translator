"""A naplóolvasó CLI csak ideiglenes, mesterséges naplókon végzett tesztjei."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import read_diagnostics as module


class ReadDiagnosticsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.request_a = "a" * 32
        self.request_b = "b" * 32

    def record(self, event: str, *, level: str = "INFO", request_id: str | None = None, **fields) -> dict:
        result = {
            "schema_version": 1,
            "timestamp": "2026-10-01T01:24:09.123+02:00",
            "event": event,
            "level": level,
            "app_version": "5.12",
            "session_id": "c" * 32,
            "pid": 123,
            "thread_id": 456,
            "monotonic_ms": 100.5,
        }
        if request_id is not None:
            result["request_id"] = request_id
        result.update(fields)
        return result

    def write(self, records: list[dict], *, backup: int = 0) -> Path:
        suffix = f".{backup}" if backup else ""
        path = self.directory / f"{module.diagnostics.LOG_FILENAME}{suffix}"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        return path

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            status = module.main(["--log-dir", str(self.directory), *args])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_rotated_files_are_read_oldest_first_and_last_limit_is_applied(self) -> None:
        for number in range(5, 0, -1):
            self.write([self.record(f"step.backup{number}")], backup=number)
        self.write([self.record("step.active1"), self.record("step.active2")])
        status, stdout, stderr = self.run_cli("--last", "3")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        lines = stdout.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("step.backup1", lines[0])
        self.assertIn("step.active1", lines[1])
        self.assertIn("step.active2", lines[2])
        status, stdout, _ = self.run_cli("--last", "20")
        events = [line.split(" ")[2] for line in stdout.splitlines()]
        self.assertEqual(events, ["step.backup5", "step.backup4", "step.backup3", "step.backup2", "step.backup1", "step.active1", "step.active2"])

    def test_request_filter_is_case_insensitive_and_level_is_minimum_severity(self) -> None:
        self.write([
            self.record("request.started", request_id=self.request_a),
            self.record("request.warning", level="WARNING", request_id=self.request_a),
            self.record("request.failed", level="ERROR", request_id=self.request_a, reason="timeout", duration_ms=180000),
            self.record("other.failed", level="ERROR", request_id=self.request_b),
            self.record("request.crashed", level="CRITICAL", request_id=self.request_a, error_type="RuntimeError"),
        ])
        status, stdout, stderr = self.run_cli("--request-id", self.request_a.upper(), "--level", "error")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(stdout.splitlines()), 2)
        self.assertIn("request.failed", stdout)
        self.assertIn("request.crashed", stdout)
        self.assertIn("duration_ms=180000", stdout)
        self.assertIn("reason=timeout", stdout)
        self.assertNotIn("other.failed", stdout)
        self.assertNotIn("request.warning", stdout)

    def test_summary_counts_all_filtered_records_independently_of_timeline_limit(self) -> None:
        self.write([
            self.record("request.started", request_id=self.request_a),
            self.record("request.failed", level="ERROR", request_id=self.request_a),
            self.record("request.failed", level="ERROR", request_id=self.request_b),
            self.record("python.thread_exception", level="CRITICAL"),
        ])
        status, stdout, stderr = self.run_cli("--summary", "--last", "1")
        self.assertEqual(status, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Események: 4", stdout)
        self.assertIn("Hibák (ERROR/CRITICAL): 3", stdout)
        self.assertIn("Kérések: 2", stdout)
        self.assertIn("request.failed: 2", stdout)
        status, stdout, _ = self.run_cli("--summary", "--request-id", self.request_a, "--level", "ERROR")
        self.assertIn("Események: 1", stdout)
        self.assertIn("Kérések: 1", stdout)

    def test_malformed_truncated_and_invalid_utf8_lines_are_skipped_without_disclosing_them(self) -> None:
        path = self.write([self.record("before.valid")])
        with path.open("ab") as handle:
            handle.write(b"secret-malformed-text\n")
            handle.write(b'{"event":"secret-partial"\n')
            handle.write(b"\xffprivate-invalid-utf8\n")
            handle.write((json.dumps(self.record("after.valid")) + "\n").encode("utf-8"))
            handle.write(b'{"secret":"truncated')
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 0)
        self.assertIn("before.valid", stdout)
        self.assertIn("after.valid", stdout)
        self.assertIn("sorok: 4", stderr)
        self.assertNotIn("secret", stdout + stderr)
        self.assertNotIn("private", stdout + stderr)

    def test_oversized_line_is_discarded_as_one_record_then_reading_continues(self) -> None:
        path = self.directory / module.diagnostics.LOG_FILENAME
        path.write_bytes(b"secret" * (module._MAX_LINE_BYTES // 6 + 10) + b"\n" + (json.dumps(self.record("after.large")) + "\n").encode("utf-8"))
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 0)
        self.assertIn("after.large", stdout)
        self.assertIn("sorok: 1", stderr)
        self.assertNotIn("secret", stdout + stderr)

    def test_foreign_record_content_and_untrusted_structural_values_are_never_printed(self) -> None:
        self.write([
            self.record(
                "privacy.safe", prompt="secret-prompt", translation="secret-translation", image="secret-image",
                cookie="secret-cookie", url="https://private/path", console="secret-console",
                reason="secret with spaces", app_version="private version", request_id="secret-request",
                source="https://private/path", duration_ms=float("inf"), busy=True, text_length=42,
                traceback=[{"file": "C:\\Users\\private\\secret.py", "source": "secret-line"}],
            ),
            self.record("event\nsecret-injected"),
            self.record("invalid.timestamp", timestamp="secret-timestamp"),
            self.record("invalid.level", level="secret-level"),
        ])
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 0)
        self.assertIn("privacy.safe", stdout)
        self.assertIn("busy=true", stdout)
        self.assertIn("text_length=42", stdout)
        self.assertIn("sorok: 3", stderr)
        self.assertNotIn("secret", stdout + stderr)
        self.assertNotIn("private", stdout + stderr)
        self.assertNotIn("traceback", stdout + stderr)

    def test_timestamp_is_parsed_and_canonicalized_and_naive_timestamp_is_rejected(self) -> None:
        utc = self.record("time.utc", timestamp="2026-09-30T23:24:09.123Z")
        expected = module.datetime.fromisoformat(utc["timestamp"]).astimezone().isoformat(timespec="milliseconds")
        sanitized = module.sanitize_record(utc)
        self.assertEqual(sanitized["timestamp"], expected)
        self.assertIsNone(module.sanitize_record(self.record("time.naive", timestamp="2026-10-01T01:24:09")))
        self.assertIsNone(module.sanitize_record(self.record("time.invalid", timestamp="2026-02-30T01:24:09+02:00")))

    def test_default_directory_does_not_initialize_or_read_profile(self) -> None:
        with patch.dict(module.os.environ, {"LOCALAPPDATA": str(self.directory)}):
            self.assertEqual(module.default_log_directory(), self.directory / "Gamer Translator" / "logs")
        with patch.dict(module.os.environ, {}, clear=True), patch.object(module.Path, "home", return_value=self.directory):
            self.assertEqual(module.default_log_directory(), self.directory / ".gamer-translator" / "logs")
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_missing_logs_return_clear_error_without_echoing_directory(self) -> None:
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Nem található olvasható eseménynapló", stderr)
        self.assertNotIn(str(self.directory), stderr)

    def test_script_runs_directly_with_only_explicit_temporary_logs(self) -> None:
        self.write([self.record("standalone.valid")])
        result = subprocess.run(
            [sys.executable, str(Path(module.__file__).resolve()), "--log-dir", str(self.directory), "--last", "1"],
            cwd=self.directory, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("standalone.valid", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
