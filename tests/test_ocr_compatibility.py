"""RapidOCR csomagverziókhoz kapcsolódó offline regressziók."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from gamer_translator.ocr_service import OCRService


class OCRCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_dir.cleanup)
        with patch.object(OCRService, "_resolve_windows_language_tags", return_value=()):
            self.service = OCRService(Path(self.temporary_dir.name))

    def test_engine_uses_the_verified_assets_current_package_names(self):
        # A telepített csomag valódi metaadatai régebben eltértek a hardcoded nevektől.
        assets = self.service._required_assets()
        with patch.object(self.service, "_ensure_assets") as ensure_assets:
            with patch("gamer_translator.ocr_service.RapidOCR") as engine:
                self.service._get_engine()
        ensure_assets.assert_called_once_with()
        params = engine.call_args.kwargs["params"]
        for task, asset in zip(("Det", "Cls", "Rec"), assets, strict=True):
            self.assertEqual(Path(params[f"{task}.model_path"]), self.service.root_dir / asset.filename)

    def test_embedded_onnx_dictionary_needs_no_removed_internal_api(self):
        with patch.object(self.service, "_ensure_assets"):
            with patch("gamer_translator.ocr_service.RapidOCR") as engine:
                self.service._get_engine()
        self.assertNotIn("Rec.rec_keys_path", engine.call_args.kwargs["params"])

    def test_failed_integrity_validation_cannot_initialize_an_engine(self):
        with patch.object(self.service, "_ensure_assets", side_effect=RuntimeError("ellenőrzőösszeg eltér")):
            with patch("gamer_translator.ocr_service.RapidOCR") as engine:
                with self.assertRaisesRegex(RuntimeError, "ellenőrzőösszeg"):
                    self.service._get_engine()
        engine.assert_not_called()

    def test_initialized_engine_is_reused_without_reloading_models(self):
        existing_engine = Mock()
        self.service.engine = existing_engine
        with patch.object(self.service, "_ensure_assets") as ensure_assets:
            self.assertIs(self.service._get_engine(), existing_engine)
        ensure_assets.assert_not_called()


if __name__ == "__main__":
    unittest.main()
