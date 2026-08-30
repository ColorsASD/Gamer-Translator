"""OCR összefűzési és rangsorolási regressziók hálózat/modellek nélkül."""
from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from gamer_translator.ocr_service import OCRCandidate, OCRService


def box(left, top, right, bottom):
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


class OCRQualityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        with patch.object(OCRService, "_resolve_windows_language_tags", return_value=()):
            self.service = OCRService(Path(self.directory.name))
        image = Image.new("RGB", (200, 100), "white")
        data = io.BytesIO()
        image.save(data, format="PNG")
        self.image_bytes = data.getvalue()

    def test_contractions_and_unicode_words_are_not_broken_into_noise(self):
        self.assertEqual(self.service._extract_words("Don't rush B; ő vár. Ångström."), ["Don't", "rush", "B", "ő", "vár", "Ångström"])
        self.assertEqual(self.service._noise_penalty("Don't rush B; ő vár."), 0)
        self.assertGreater(self.service._noise_penalty("Hi \ufffd (cid:12)"), 0)

    def test_two_recognizers_can_outvote_many_filtered_copies_of_one(self):
        wrong = [OCRCandidate("Keep the shield dn", 1.50, "RapidOCR", f"filter-{index}") for index in range(20)]
        agreed = [OCRCandidate("Keep the shield up", 1.43, engine, "eredeti") for engine in ("Windows OCR (hu-HU)", "Windows OCR (en-US)")]
        self.assertEqual(self.service._rank_candidates(wrong + agreed)[0].text, "Keep the shield up")

    def test_accent_variants_share_evidence_without_rewriting_text(self):
        candidates = [
            OCRCandidate("Hűvös idő", 1.51, "Windows OCR (hu-HU)", "eredeti"),
            OCRCandidate("Hüvös idö", 1.49, "RapidOCR", "eredeti"),
            OCRCandidate("Hűvös ii idő", 1.58, "RapidOCR", "szurke"),
        ]
        ranked = self.service._rank_candidates(candidates)
        self.assertEqual(ranked[0].text, "Hűvös idő")
        self.assertEqual(candidates[0].score, 1.51, "A rangsorolás nem halmozhatja a bónuszt az eredeti jelöltben.")
        self.assertEqual(self.service._rank_candidates(candidates), ranked)

    def test_same_engine_copies_do_not_receive_consensus_bonus(self):
        candidates = [OCRCandidate("Same text", 1.4, "RapidOCR", str(index)) for index in range(12)]
        self.assertEqual({candidate.score for candidate in self.service._rank_candidates(candidates)}, {1.4})

    def test_fast_path_waits_for_available_second_recognizer(self):
        self.service.windows_language_tags = ("hu-HU",)
        candidates = [OCRCandidate("Első eredmény", 1.9, "RapidOCR", "eredeti")]
        self.assertFalse(self.service._can_stop_fast_pass(candidates, 1))
        candidates.append(OCRCandidate("Második eredmény", 1.8, "Windows OCR (hu-HU)", "eredeti"))
        self.assertTrue(self.service._can_stop_fast_pass(candidates, 1))

    def test_overlapping_same_line_boxes_are_grouped_but_other_lines_are_not(self):
        boxes = [box(0, 0, 80, 30), box(60, 2, 150, 32), box(10, 50, 90, 80)]
        self.assertEqual(self.service._overlapping_box_groups(boxes), [[0, 1], [2]])

    def test_repeated_words_without_spatial_overlap_remain_untouched(self):
        boxes = [box(0, 0, 70, 30), box(90, 0, 150, 30)]
        engine = Mock()
        result = self.service._recognize_overlapping_boxes(self.image_bytes, boxes, ("go", "go"), (.99, .99), engine)
        self.assertEqual(result[1], ("go", "go"))
        engine.assert_not_called()

    def test_overlap_recovery_reads_pixels_instead_of_deleting_partial_words(self):
        boxes = [box(0, 0, 100, 30), box(75, 0, 180, 30)]
        engine = Mock(return_value=SimpleNamespace(txts=("hello tower",), scores=(.99,)))
        new_boxes, new_texts, new_scores = self.service._recognize_overlapping_boxes(self.image_bytes, boxes, ("hello to", "tower"), (.98, .99), engine)
        self.assertEqual(new_texts, ("hello tower",))
        self.assertEqual(len(new_boxes), 1)
        self.assertEqual(new_scores, (.99,))
        self.assertEqual(engine.call_args.kwargs, {"use_det": False, "use_cls": False, "use_rec": True})

    def test_unreliable_overlap_recovery_preserves_original_readings(self):
        boxes = [box(0, 0, 100, 30), box(75, 0, 180, 30)]
        engine = Mock(return_value=SimpleNamespace(txts=("unreliable",), scores=(.2,)))
        result = self.service._recognize_overlapping_boxes(self.image_bytes, boxes, ("hello to", "tower"), (.98, .99), engine)
        self.assertEqual(result[1], ("hello to", "tower"))

    def test_empty_recognition_does_not_shift_text_to_another_box(self):
        boxes = [box(0, 0, 10, 20), box(20, 0, 90, 20), box(100, 0, 180, 20)]
        engine = Mock(return_value=SimpleNamespace(txts=("", "hello", "gamer"), scores=(.2, .99, .99), boxes=boxes))
        with patch.object(self.service, "_get_engine", return_value=engine):
            result = self.service._extract_with_rapidocr("eredeti", self.image_bytes)
        self.assertEqual(result[0].text, "hello gamer")
        self.assertEqual(engine.call_args.kwargs, {"use_det": True, "use_cls": True, "use_rec": True})

    def test_recovery_work_is_bounded(self):
        boxes = [box(0, 0, 100, 30), box(75, 0, 180, 30)]
        engine = Mock()
        with patch("gamer_translator.ocr_service.MAX_OVERLAP_RECOVERY_GROUPS", 0):
            result = self.service._recognize_overlapping_boxes(self.image_bytes, boxes, ("hello to", "tower"), (.98, .99), engine)
        self.assertEqual(result[1], ("hello to", "tower"))
        engine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
