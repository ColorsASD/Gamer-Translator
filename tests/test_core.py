from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

import main
from gamer_translator.defaults import DEFAULT_BIDIRECTIONAL_PROMPT, PREVIOUS_BIDIRECTIONAL_PROMPT
from gamer_translator.ocr_service import OCRAsset, OCRCandidate, OCRService
from gamer_translator.settings_store import AppSettings, LastRunStatus, SettingsStore


class SettingsStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_dir.cleanup)
        self.root_dir = Path(self.temporary_dir.name)

    def test_malformed_documents_do_not_crash_startup(self) -> None:
        for payload in (b"null", b"[]", b"1", b'"text"', b"{", b"\xff\xfe"):
            with self.subTest(payload=payload):
                store = SettingsStore(self.root_dir)
                store.config_path.write_bytes(payload)
                self.assertEqual(store.load_settings(), AppSettings())
                self.assertEqual(store.load_last_run_status(), LastRunStatus())

    def test_malformed_nested_settings_and_status_are_ignored(self) -> None:
        for value in (True, 13, ["unexpected"], "unexpected"):
            with self.subTest(value=value):
                store = SettingsStore(self.root_dir)
                store.config_path.write_text(json.dumps({"settings": value, "lastRunStatus": value}), encoding="utf-8")
                self.assertEqual(store.load_settings(), AppSettings())
                self.assertEqual(store.load_last_run_status(), LastRunStatus())

    def test_false_string_does_not_enable_monitoring_or_clipboard(self) -> None:
        settings = AppSettings.from_dict({"monitoringEnabled": "false", "copyResponseToClipboard": " FALSE "})
        self.assertFalse(settings.monitoring_enabled)
        self.assertFalse(settings.copy_response_to_clipboard)

    def test_settings_are_bounded_before_qt_receives_them(self) -> None:
        settings = AppSettings.from_dict({"overlayOpacityPercent": -30, "overlayDurationSeconds": 10**50, "pageReadyTimeoutMs": -1})
        self.assertEqual(settings.overlay_opacity_percent, 1)
        self.assertEqual(settings.overlay_duration_seconds, 120)
        self.assertEqual(settings.page_ready_timeout_ms, 1000)
        self.assertEqual(AppSettings.from_dict({"pageReadyTimeoutMs": float("inf")}).page_ready_timeout_ms, AppSettings().page_ready_timeout_ms)

    def test_legacy_prompt_is_migrated_but_custom_prompt_is_preserved(self) -> None:
        self.assertEqual(AppSettings.from_dict({"promptTemplate": PREVIOUS_BIDIRECTIONAL_PROMPT}).prompt_template, DEFAULT_BIDIRECTIONAL_PROMPT)
        self.assertEqual(AppSettings.from_dict({"promptTemplate": "Saját fordítási szabály."}).prompt_template, "Saját fordítási szabály.")

    def test_failed_replace_preserves_previous_document_and_cache(self) -> None:
        store = SettingsStore(self.root_dir)
        store.save_last_translated_text("Korábbi fordítás")
        original_bytes = store.config_path.read_bytes()

        with patch("gamer_translator.settings_store.os.replace", side_effect=OSError("szimulált lemezhiba")):
            with self.assertRaises(OSError):
                store.save_last_translated_text("Új fordítás")

        self.assertEqual(store.config_path.read_bytes(), original_bytes)
        self.assertEqual(store.load_last_translated_text(), "Korábbi fordítás")
        self.assertEqual(list(self.root_dir.glob(".settings-*.tmp")), [])

    def test_atomic_save_preserves_other_sections_and_unicode(self) -> None:
        store = SettingsStore(self.root_dir)
        store.save_last_translated_text("Árvíztűrő tükörfúrógép")
        store.save_last_run_status("Fordítás elkészült.")
        store.save_settings(AppSettings(monitoring_enabled=False))
        reloaded = SettingsStore(self.root_dir)
        self.assertFalse(reloaded.load_settings().monitoring_enabled)
        self.assertEqual(reloaded.load_last_translated_text(), "Árvíztűrő tükörfúrógép")
        self.assertEqual(reloaded.load_last_run_status().message, "Fordítás elkészült.")


class OCRServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_dir.cleanup)
        self.root_dir = Path(self.temporary_dir.name)
        with patch.object(OCRService, "_resolve_windows_language_tags", return_value=()):
            self.service = OCRService(self.root_dir)

    def configure_asset(self, payload: bytes = b"ellenorzott modell", **overrides) -> OCRAsset:
        fields = {"filename": "model.onnx", "url": "https://example.invalid/model.onnx", "sha256": hashlib.sha256(payload).hexdigest()}
        fields.update(overrides)
        asset = OCRAsset(**fields)
        self.service._required_assets = lambda: (asset,)
        return asset

    def test_existing_verified_model_requires_no_network(self) -> None:
        payload = b"ellenorzott modell"
        self.configure_asset(payload)
        (self.root_dir / "model.onnx").write_bytes(payload)
        with patch("gamer_translator.ocr_service.DownloadFile.run") as download:
            self.service._ensure_assets()
            download.assert_not_called()

    def test_new_model_is_checked_before_replacing_old_file(self) -> None:
        payload = b"ellenorzott modell"
        self.configure_asset(payload)
        target = self.root_dir / "model.onnx"
        target.write_bytes(b"regi modell")
        with patch("gamer_translator.ocr_service.DownloadFile.run", side_effect=lambda params: Path(params.save_path).write_bytes(payload)):
            self.service._ensure_assets()
        self.assertEqual(target.read_bytes(), payload)
        self.assertEqual(list(self.root_dir.glob(".download-*")), [])

    def test_tampered_download_is_rejected_without_overwriting_previous_file(self) -> None:
        self.configure_asset()
        target = self.root_dir / "model.onnx"
        target.write_bytes(b"regi modell")
        with patch("gamer_translator.ocr_service.DownloadFile.run", side_effect=lambda params: Path(params.save_path).write_bytes(b"serult modell")):
            with self.assertRaisesRegex(RuntimeError, "ellenőrzőösszege eltér"):
                self.service._ensure_assets()
        self.assertEqual(target.read_bytes(), b"regi modell")
        self.assertEqual(list(self.root_dir.glob(".download-*")), [])

    def test_download_requires_checksum_https_and_local_filename(self) -> None:
        for overrides in ({"sha256": None}, {"sha256": "invalid"}, {"url": "http://example.invalid/model"}, {"filename": "../model.onnx"}):
            with self.subTest(overrides=overrides):
                self.configure_asset(**overrides)
                with patch("gamer_translator.ocr_service.DownloadFile.run") as download:
                    with self.assertRaises(RuntimeError):
                        self.service._ensure_assets()
                    download.assert_not_called()

    def test_oversized_image_is_rejected_before_decoding(self) -> None:
        large_image = Mock(width=10000, height=10000)
        context = Mock()
        context.__enter__ = Mock(return_value=large_image)
        context.__exit__ = Mock(return_value=False)
        with patch("gamer_translator.ocr_service.Image.open", return_value=context), patch("gamer_translator.ocr_service.ImageOps.exif_transpose") as transpose:
            with self.assertRaisesRegex(ValueError, "40 millió"):
                self.service._load_image(b"fake header")
            transpose.assert_not_called()

    def test_oversized_payload_is_rejected_before_opening(self) -> None:
        with patch("gamer_translator.ocr_service.MAX_SOURCE_IMAGE_BYTES", 8), patch("gamer_translator.ocr_service.Image.open") as open_image:
            with self.assertRaisesRegex(ValueError, "64 MiB"):
                self.service._load_image(b"123456789")
            open_image.assert_not_called()

    def test_transparent_black_background_does_not_hide_text(self) -> None:
        source = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
        source.putpixel((0, 0), (0, 0, 0, 255))
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        loaded = self.service._load_image(buffer.getvalue())
        self.assertEqual(loaded.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(loaded.getpixel((1, 0)), (255, 255, 255))

    def test_more_than_five_candidates_can_finish_fast_pass(self) -> None:
        candidates = [OCRCandidate(f"fordítás {index}", 1.8, "teszt", "eredeti") for index in range(6)]
        self.assertTrue(self.service._can_stop_fast_pass(candidates, 6))
        self.assertFalse(self.service._can_stop_fast_pass(candidates + candidates, 7))


class EntryPointTests(unittest.TestCase):
    def test_gpu_disabled_removes_acceleration_and_preserves_unrelated_flags(self) -> None:
        settings = AppSettings(webview_gpu_acceleration_enabled=False)
        with patch.object(main.sys, "platform", "win32"), patch.object(main, "SettingsStore") as store, patch.dict(os.environ, {"QTWEBENGINE_CHROMIUM_FLAGS": "--enable-gpu-rasterization --disable-features=Example,CalculateNativeWinOcclusion --custom"}):
            store.return_value.load_settings.return_value = settings
            main.configure_webengine_environment()
            flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
        self.assertIn("--disable-gpu", flags)
        self.assertIn("--custom", flags)
        self.assertIn("--disable-features=Example", flags)
        self.assertNotIn("--enable-gpu-rasterization", flags)

    def test_import_and_single_instance_lock_are_isolated_from_live_profile(self) -> None:
        script = '''
import sys
import tempfile
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from PySide6.QtNetwork import QLocalServer
import main
assert "gamer_translator.main_window" not in sys.modules
app = QCoreApplication([])
with tempfile.TemporaryDirectory() as directory:
    first = main.SingleInstanceController("GamerTranslatorCoreTest", Path(directory) / "a")
    second = main.SingleInstanceController("GamerTranslatorCoreTest", Path(directory) / "a")
    other_profile = main.SingleInstanceController("GamerTranslatorCoreTest", Path(directory) / "b")
    assert first.ensure_primary_instance()
    assert not second.ensure_primary_instance()
    assert other_profile.ensure_primary_instance()
    assert first.server.socketOptions() == QLocalServer.SocketOption.UserAccessOption
    first.server.close()
    other_profile.server.close()
    first.instance_lock.unlock()
    other_profile.instance_lock.unlock()
'''
        completed = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
