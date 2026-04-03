from __future__ import annotations

import asyncio
import io
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median
from typing import Iterable

from PIL import Image, ImageEnhance, ImageFilter, ImageOps
from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR
from rapidocr.inference_engine.base import FileInfo, InferSession
from rapidocr.utils.download_file import DownloadFile, DownloadFileInput
from rapidocr.utils.typings import TaskType
from wordfreq import zipf_frequency

from .settings_store import default_app_data_dir

LOGGER = logging.getLogger("gamer_translator.ocr")
HUNGARIAN_WORD_PATTERN = re.compile(r"[A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+")
FAST_VARIANT_NAMES = (
    "eredeti",
    "alap_kontrasztos",
    "szurke_alap",
    "nagyitott_elesitett",
    "kuszobolt_160",
)
WINDOWS_FAST_VARIANT_NAMES = (
    "eredeti",
    "szurke_alap",
)
WINDOWS_FALLBACK_VARIANT_NAMES = (
    "szurke_elesitett",
    "kuszobolt_160",
)
MAX_SOURCE_IMAGE_EDGE = 1700
OCR_VARIANT_COOLDOWN_SECONDS = 0.012
DEFAULT_OCR_CANDIDATE_COUNT = 5
AMBIGUOUS_HUNGARIAN_GROUPS: dict[str, tuple[str, ...]] = {
    "a": ("a", "á"),
    "á": ("a", "á"),
    "e": ("e", "é"),
    "é": ("e", "é"),
    "i": ("i", "í"),
    "í": ("i", "í"),
    "o": ("o", "ó", "ö", "ő"),
    "ó": ("o", "ó", "ö", "ő"),
    "ö": ("o", "ó", "ö", "ő"),
    "ő": ("o", "ó", "ö", "ő"),
    "u": ("u", "ú", "ü", "ű"),
    "ú": ("u", "ú", "ü", "ű"),
    "ü": ("u", "ú", "ü", "ű"),
    "ű": ("u", "ú", "ü", "ű"),
}

try:
    from winsdk.windows.globalization import Language
    from winsdk.windows.graphics.imaging import BitmapDecoder
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.storage.streams import DataWriter, InMemoryRandomAccessStream

    WINDOWS_OCR_AVAILABLE = True
except ImportError:
    Language = None
    BitmapDecoder = None
    OcrEngine = None
    DataWriter = None
    InMemoryRandomAccessStream = None
    WINDOWS_OCR_AVAILABLE = False


@dataclass(frozen=True, slots=True)
class OCRAsset:
    filename: str
    url: str
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class OCRCandidate:
    text: str
    score: float
    engine_name: str
    variant_name: str


class OCRService:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or default_app_data_dir() / "ocr"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.engine: RapidOCR | None = None
        self.windows_language_tags = self._resolve_windows_language_tags()

    def extract_text(self, image_bytes: bytes) -> str:
        candidates = self._collect_ranked_candidates(image_bytes)

        if not candidates:
            raise RuntimeError("A képről nem sikerült kiolvasni olvasható szöveget.")

        return candidates[0].text

    def extract_text_candidates(self, image_bytes: bytes, limit: int | None = None) -> tuple[str, ...]:
        desired_count = DEFAULT_OCR_CANDIDATE_COUNT if limit is None or limit <= 0 else max(1, int(limit))
        candidates = self._collect_ranked_candidates(image_bytes, minimum_candidate_count=desired_count)

        if not candidates:
            raise RuntimeError("A képről nem sikerült kiolvasni olvasható szöveget.")

        selected_candidates = self._select_unique_candidates(candidates, desired_count)

        return tuple(candidate.text for candidate in selected_candidates)

    def _collect_ranked_candidates(self, image_bytes: bytes, minimum_candidate_count: int = 0) -> list[OCRCandidate]:
        if not image_bytes:
            raise ValueError("Az OCR nem kapott feldolgozható képadatot.")

        image = self._load_image(image_bytes)
        variants = self._build_image_variants(image)
        variants_by_name = {variant_name: variant_bytes for variant_name, variant_bytes in variants}
        fast_variant_names = set(FAST_VARIANT_NAMES)
        fast_candidates: list[OCRCandidate] = []

        for variant_name in FAST_VARIANT_NAMES:
            variant_bytes = variants_by_name.get(variant_name)

            if variant_bytes is None:
                continue

            fast_candidates.extend(self._extract_with_rapidocr(variant_name, variant_bytes))
            ranked_fast_candidates = self._rank_candidates(fast_candidates)

            if self._can_stop_fast_pass(ranked_fast_candidates, minimum_candidate_count):
                return ranked_fast_candidates

            if variant_name in WINDOWS_FAST_VARIANT_NAMES:
                fast_candidates.extend(self._extract_with_windows_ocr(variant_name, variant_bytes))
                ranked_fast_candidates = self._rank_candidates(fast_candidates)

                if self._can_stop_fast_pass(ranked_fast_candidates, minimum_candidate_count):
                    return ranked_fast_candidates

            self._yield_between_variants()

        ranked_fast_candidates = self._rank_candidates(fast_candidates)

        if self._can_stop_fast_pass(ranked_fast_candidates, minimum_candidate_count):
            return ranked_fast_candidates

        fallback_candidates = list(fast_candidates)

        for variant_name, variant_bytes in variants:
            if variant_name in fast_variant_names:
                continue

            fallback_candidates.extend(self._extract_with_rapidocr(variant_name, variant_bytes))
            ranked_fallback_candidates = self._rank_candidates(fallback_candidates)

            if self._can_stop_fallback_pass(ranked_fallback_candidates, minimum_candidate_count):
                return ranked_fallback_candidates

            if variant_name in WINDOWS_FALLBACK_VARIANT_NAMES:
                fallback_candidates.extend(self._extract_with_windows_ocr(variant_name, variant_bytes))
                ranked_fallback_candidates = self._rank_candidates(fallback_candidates)

                if self._can_stop_fallback_pass(ranked_fallback_candidates, minimum_candidate_count):
                    return ranked_fallback_candidates

            self._yield_between_variants()

        return self._rank_candidates(fallback_candidates)

    def _yield_between_variants(self) -> None:
        if OCR_VARIANT_COOLDOWN_SECONDS > 0:
            time.sleep(OCR_VARIANT_COOLDOWN_SECONDS)

    def _select_unique_candidates(self, candidates: Iterable[OCRCandidate], limit: int) -> list[OCRCandidate]:
        selected_candidates: list[OCRCandidate] = []
        seen_texts: set[str] = set()

        for candidate in candidates:
            normalized_text = candidate.text.strip()

            if not normalized_text or normalized_text in seen_texts:
                continue

            seen_texts.add(normalized_text)
            selected_candidates.append(candidate)

            if len(selected_candidates) >= limit:
                break

        return selected_candidates

    def _unique_candidate_count(self, candidates: Iterable[OCRCandidate]) -> int:
        return len(self._select_unique_candidates(candidates, DEFAULT_OCR_CANDIDATE_COUNT))

    def _can_stop_fast_pass(self, ranked_candidates: list[OCRCandidate], minimum_candidate_count: int) -> bool:
        if self._unique_candidate_count(ranked_candidates) < max(1, minimum_candidate_count):
            return False

        return self._is_fast_pass_enough(ranked_candidates)

    def _can_stop_fallback_pass(self, ranked_candidates: list[OCRCandidate], minimum_candidate_count: int) -> bool:
        if self._unique_candidate_count(ranked_candidates) < max(1, minimum_candidate_count):
            return False

        return self._is_fallback_pass_enough(ranked_candidates)

    def _get_engine(self) -> RapidOCR:
        if self.engine is not None:
            return self.engine

        self._ensure_assets()
        self.engine = RapidOCR(
            params={
                "Global.log_level": "ERROR",
                "Det.engine_type": EngineType.ONNXRUNTIME,
                "Det.lang_type": LangDet.MULTI,
                "Det.model_type": ModelType.MOBILE,
                "Det.ocr_version": OCRVersion.PPOCRV4,
                "Det.model_path": str(self.root_dir / "Multilingual_PP-OCRv3_det_infer.onnx"),
                "Cls.engine_type": EngineType.ONNXRUNTIME,
                "Cls.lang_type": LangDet.CH,
                "Cls.model_type": ModelType.MOBILE,
                "Cls.ocr_version": OCRVersion.PPOCRV4,
                "Cls.model_path": str(self.root_dir / "ch_ppocr_mobile_v2.0_cls_infer.onnx"),
                "Rec.engine_type": EngineType.ONNXRUNTIME,
                "Rec.lang_type": LangRec.LATIN,
                "Rec.model_type": ModelType.MOBILE,
                "Rec.ocr_version": OCRVersion.PPOCRV5,
                "Rec.model_path": str(self.root_dir / "latin_PP-OCRv5_rec_mobile_infer.onnx"),
                "Rec.rec_keys_path": str(self._resolve_rec_keys_path()),
            }
        )
        return self.engine

    def _ensure_assets(self) -> None:
        for asset in self._required_assets():
            DownloadFile.run(
                DownloadFileInput(
                    file_url=asset.url,
                    save_path=self.root_dir / asset.filename,
                    sha256=asset.sha256,
                    logger=LOGGER,
                    verbose=False,
                )
            )

    def _required_assets(self) -> tuple[OCRAsset, ...]:
        det_info = InferSession.get_model_url(
            FileInfo(
                engine_type=EngineType.ONNXRUNTIME,
                ocr_version=OCRVersion.PPOCRV4,
                task_type=TaskType.DET,
                lang_type=LangDet.MULTI,
                model_type=ModelType.MOBILE,
            )
        )
        cls_info = InferSession.get_model_url(
            FileInfo(
                engine_type=EngineType.ONNXRUNTIME,
                ocr_version=OCRVersion.PPOCRV4,
                task_type=TaskType.CLS,
                lang_type=LangDet.CH,
                model_type=ModelType.MOBILE,
            )
        )
        rec_file_info = FileInfo(
            engine_type=EngineType.ONNXRUNTIME,
            ocr_version=OCRVersion.PPOCRV5,
            task_type=TaskType.REC,
            lang_type=LangRec.LATIN,
            model_type=ModelType.MOBILE,
        )
        rec_info = InferSession.get_model_url(rec_file_info)
        return (
            OCRAsset(
                filename=Path(str(det_info["model_dir"])).name,
                url=str(det_info["model_dir"]),
                sha256=str(det_info.get("SHA256") or "") or None,
            ),
            OCRAsset(
                filename=Path(str(cls_info["model_dir"])).name,
                url=str(cls_info["model_dir"]),
                sha256=str(cls_info.get("SHA256") or "") or None,
            ),
            OCRAsset(
                filename=Path(str(rec_info["model_dir"])).name,
                url=str(rec_info["model_dir"]),
                sha256=str(rec_info.get("SHA256") or "") or None,
            ),
        )

    def _resolve_rec_keys_path(self) -> Path:
        packaged_dict_path = InferSession.DEFAULT_MODEL_PATH / "ppocrv5_dict.txt"

        if packaged_dict_path.exists():
            return packaged_dict_path

        raise FileNotFoundError("A RapidOCR PP-OCRv5 szótárfájlja nem található.")

    def _load_image(self, image_bytes: bytes) -> Image.Image:
        with Image.open(io.BytesIO(image_bytes)) as image:
            prepared_image = ImageOps.exif_transpose(image).convert("RGB")
            return self._shrink_large_image(prepared_image)

    def _shrink_large_image(self, image: Image.Image) -> Image.Image:
        max_edge = max(image.width, image.height)

        if max_edge <= MAX_SOURCE_IMAGE_EDGE:
            return image

        scale = MAX_SOURCE_IMAGE_EDGE / max_edge
        resized_width = max(1, int(round(image.width * scale)))
        resized_height = max(1, int(round(image.height * scale)))
        return image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)

    def _build_image_variants(self, image: Image.Image) -> tuple[tuple[str, bytes], ...]:
        variants: list[tuple[str, bytes]] = []
        seen_payloads: set[bytes] = set()
        base = image.copy()
        upscale_factor = 3 if max(base.width, base.height) <= 1400 else 2
        enlarged = base.resize((max(1, base.width * upscale_factor), max(1, base.height * upscale_factor)), Image.Resampling.LANCZOS)
        sharpened_base = ImageEnhance.Contrast(
            base.filter(ImageFilter.UnsharpMask(radius=1.1, percent=160, threshold=2))
        ).enhance(1.18)
        enlarged_soft = ImageEnhance.Contrast(enlarged).enhance(1.12)
        enlarged_sharp = ImageEnhance.Contrast(
            enlarged.filter(ImageFilter.UnsharpMask(radius=1.4, percent=210, threshold=2))
        ).enhance(1.38)
        grayscale_base = ImageOps.autocontrast(
            ImageOps.grayscale(base).filter(ImageFilter.MedianFilter(size=3))
        )
        grayscale_enlarged = ImageOps.autocontrast(
            ImageOps.grayscale(enlarged).filter(ImageFilter.MedianFilter(size=3))
        )
        grayscale_soft = ImageEnhance.Contrast(grayscale_enlarged).enhance(1.55)
        grayscale_sharp = ImageEnhance.Contrast(
            grayscale_enlarged.filter(ImageFilter.UnsharpMask(radius=1.2, percent=180, threshold=2))
        ).enhance(1.95)
        grayscale_inverted = ImageOps.invert(grayscale_sharp)

        variant_images = (
            ("eredeti", base),
            ("alap_kontrasztos", sharpened_base),
            ("nagyitott", enlarged_soft),
            ("nagyitott_elesitett", enlarged_sharp),
            ("szurke_alap", grayscale_base),
            ("szurke", grayscale_soft),
            ("szurke_elesitett", grayscale_sharp),
            ("szurke_invertalt", grayscale_inverted),
        )

        for variant_name, variant_image in variant_images:
            payload = self._image_to_png_bytes(variant_image.convert("RGB"))

            if payload in seen_payloads:
                continue

            seen_payloads.add(payload)
            variants.append((variant_name, payload))

        threshold_source = grayscale_sharp
        inverted_threshold_source = ImageOps.invert(threshold_source)

        for variant_name, variant_image in (
            ("kuszobolt_160", threshold_source.point(lambda value: 255 if value >= 160 else 0, mode="1").convert("RGB")),
            ("invertalt_kuszobolt_160", inverted_threshold_source.point(lambda value: 255 if value >= 160 else 0, mode="1").convert("RGB")),
        ):
            payload = self._image_to_png_bytes(variant_image)

            if payload in seen_payloads:
                continue

            seen_payloads.add(payload)
            variants.append((variant_name, payload))

        return tuple(variants)

    def _is_fast_pass_enough(self, ranked_candidates: list[OCRCandidate]) -> bool:
        if not ranked_candidates:
            return False

        best_candidate = ranked_candidates[0]
        compact_text = best_candidate.text.replace(" ", "").replace("\n", "")

        if best_candidate.score >= 1.55:
            return True

        if len(compact_text) >= 18 and best_candidate.score >= 1.45:
            return True

        return False

    def _is_fallback_pass_enough(self, ranked_candidates: list[OCRCandidate]) -> bool:
        if not ranked_candidates:
            return False

        best_candidate = ranked_candidates[0]
        compact_text = best_candidate.text.replace(" ", "").replace("\n", "")

        if best_candidate.score >= 1.72:
            return True

        if len(compact_text) >= 24 and best_candidate.score >= 1.56:
            return True

        return False

    def _image_to_png_bytes(self, image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def _extract_with_rapidocr(self, variant_name: str, image_bytes: bytes) -> list[OCRCandidate]:
        result = self._get_engine()(image_bytes)
        texts = tuple(str(text).strip() for text in (result.txts or ()) if str(text).strip())

        if not texts:
            return []

        if result.boxes is not None and len(result.boxes) == len(texts):
            merged_text = self._merge_lines(result.boxes, texts)
        else:
            merged_text = "\n".join(texts)

        merged_text = self._normalize_text(merged_text)

        if not merged_text:
            return []

        mean_score = mean(float(score) for score in (result.scores or ()) if score is not None) if result.scores else 0.0
        return [self._build_candidate(merged_text, 0.75 + mean_score * 0.4, "RapidOCR", variant_name)]

    def _extract_with_windows_ocr(self, variant_name: str, image_bytes: bytes) -> list[OCRCandidate]:
        if not self.windows_language_tags:
            return []

        candidates: list[OCRCandidate] = []

        for language_tag in self.windows_language_tags:
            text = self._run_windows_ocr(image_bytes, language_tag)
            text = self._normalize_text(text)

            if not text:
                continue

            candidates.append(self._build_candidate(text, 0.98, f"Windows OCR ({language_tag})", variant_name))

        return candidates

    def _run_windows_ocr(self, image_bytes: bytes, language_tag: str) -> str:
        loop = asyncio.new_event_loop()

        try:
            return loop.run_until_complete(self._run_windows_ocr_async(image_bytes, language_tag))
        except Exception:
            return ""
        finally:
            loop.close()

    async def _run_windows_ocr_async(self, image_bytes: bytes, language_tag: str) -> str:
        assert InMemoryRandomAccessStream is not None
        assert DataWriter is not None
        assert BitmapDecoder is not None
        assert OcrEngine is not None
        assert Language is not None

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(image_bytes)
        await writer.store_async()
        writer.detach_stream()
        stream.seek(0)
        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        engine = OcrEngine.try_create_from_language(Language(language_tag))

        if engine is None:
            return ""

        result = await engine.recognize_async(bitmap)
        lines = [str(line.text).strip() for line in result.lines if str(line.text).strip()]

        if lines:
            return "\n".join(lines)

        return str(result.text).strip()

    def _resolve_windows_language_tags(self) -> tuple[str, ...]:
        if not WINDOWS_OCR_AVAILABLE or OcrEngine is None:
            return ()

        try:
            supported = {str(language.language_tag).lower() for language in OcrEngine.available_recognizer_languages}
        except Exception:
            return ()

        language_tags: list[str] = []

        if "hu" in supported or "hu-hu" in supported:
            language_tags.append("hu-HU")

        if "en-us" in supported or "en" in supported:
            language_tags.append("en-US")

        return tuple(language_tags)

    def _build_candidate(self, text: str, base_score: float, engine_name: str, variant_name: str) -> OCRCandidate:
        normalized_text = self._normalize_text(text)
        corrected_text = self._restore_hungarian_diacritics(normalized_text)
        return OCRCandidate(
            text=corrected_text,
            score=base_score + self._language_plausibility_bonus(corrected_text) + self._shape_bonus(corrected_text) - self._noise_penalty(corrected_text),
            engine_name=engine_name,
            variant_name=variant_name,
        )

    def _rank_candidates(self, candidates: Iterable[OCRCandidate]) -> list[OCRCandidate]:
        candidate_list = list(candidates)

        if not candidate_list:
            return []

        ranked_candidates = sorted(
            candidate_list,
            key=lambda candidate: (
                candidate.score,
                len(candidate.text.replace(" ", "").replace("\n", "")),
                candidate.engine_name.startswith("Windows OCR"),
            ),
            reverse=True,
        )

        return ranked_candidates

    def _language_plausibility_bonus(self, text: str) -> float:
        words = self._extract_words(text)

        if not words:
            return 0.0

        language_scores = [
            self._language_score(words, "hu"),
            self._language_score(words, "en"),
            self._language_score(words, "de"),
            self._language_score(words, "fr"),
            self._language_score(words, "es"),
        ]
        best_score = max(language_scores)
        return min(0.45, best_score / 14.0)

    def _shape_bonus(self, text: str) -> float:
        compact = text.replace(" ", "").replace("\n", "")

        if not compact:
            return 0.0

        alpha_numeric_count = sum(character.isalnum() for character in compact)
        alpha_numeric_ratio = alpha_numeric_count / max(1, len(compact))
        return min(0.2, alpha_numeric_ratio * 0.2 + len(compact) * 0.003)

    def _noise_penalty(self, text: str) -> float:
        penalty = 0.0

        for word in self._extract_words(text):
            lowered = word.lower()

            if len(lowered) == 1 and lowered not in {"a", "i"}:
                penalty += 0.28

        return penalty

    def _restore_hungarian_diacritics(self, text: str) -> str:
        words = self._extract_words(text)

        if not words:
            return text

        hungarian_score = self._language_score(words, "hu")
        english_score = self._language_score(words, "en")

        if hungarian_score <= 0.0 and not any(character in "áéíóöőúüűÁÉÍÓÖŐÚÜŰ" for character in text):
            return text

        if hungarian_score + 0.2 < english_score:
            return text

        segments = re.split(r"([A-Za-zÁÉÍÓÖŐÚÜŰáéíóöőúüű]+)", text)
        restored_segments: list[str] = []

        for segment in segments:
            if not segment:
                continue

            if HUNGARIAN_WORD_PATTERN.fullmatch(segment):
                restored_segments.append(self._restore_hungarian_word(segment))
            else:
                restored_segments.append(segment)

        return "".join(restored_segments)

    def _restore_hungarian_word(self, word: str) -> str:
        if len(word) < 3:
            return word

        normalized_word = unicodedata.normalize("NFC", word)
        baseline_score = zipf_frequency(normalized_word, "hu")
        variant_groups: list[tuple[int, tuple[str, ...]]] = []

        for index, character in enumerate(normalized_word):
            lowered = character.lower()
            replacements = AMBIGUOUS_HUNGARIAN_GROUPS.get(lowered)

            if replacements is None:
                continue

            variant_groups.append((index, tuple(self._match_case(character, replacement) for replacement in replacements)))

        if not variant_groups or len(variant_groups) > 4:
            return normalized_word

        variants = {normalized_word}

        for index, replacements in variant_groups:
            updated_variants: set[str] = set()

            for variant in variants:
                for replacement in replacements:
                    updated_variants.add(variant[:index] + replacement + variant[index + 1 :])

                    if len(updated_variants) >= 256:
                        break

                if len(updated_variants) >= 256:
                    break

            variants = updated_variants or variants

            if len(variants) >= 256:
                break

        best_word = normalized_word
        best_score = baseline_score

        for variant in variants:
            score = zipf_frequency(unicodedata.normalize("NFC", variant), "hu")

            if score > best_score:
                best_word = variant
                best_score = score

        if best_score >= max(3.0, baseline_score + 1.2):
            return best_word

        return normalized_word

    def _language_score(self, words: Iterable[str], language_code: str) -> float:
        cleaned_words = [unicodedata.normalize("NFC", word) for word in words if word]

        if not cleaned_words:
            return 0.0

        return sum(max(0.0, zipf_frequency(word, language_code)) for word in cleaned_words) / len(cleaned_words)

    def _extract_words(self, text: str) -> list[str]:
        return [match.group(0) for match in HUNGARIAN_WORD_PATTERN.finditer(text)]

    def _match_case(self, original: str, replacement: str) -> str:
        return replacement.upper() if original.isupper() else replacement

    def _normalize_text(self, text: str) -> str:
        cleaned_text = unicodedata.normalize("NFC", text or "")
        cleaned_text = re.sub(r"\r\n?", "\n", cleaned_text)
        cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)
        cleaned_text = re.sub(r"\s+([,.;:!?%)\]}])", r"\1", cleaned_text)
        cleaned_text = re.sub(r"([(\[{])\s+", r"\1", cleaned_text)
        return cleaned_text.strip()

    def _merge_lines(self, boxes, texts: Iterable[str]) -> str:
        items = []

        for box, text in zip(boxes, texts):
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            top = min(ys)
            bottom = max(ys)
            left = min(xs)
            items.append(
                {
                    "text": str(text).strip(),
                    "left": left,
                    "top": top,
                    "bottom": bottom,
                    "center_y": (top + bottom) / 2.0,
                    "height": max(1.0, bottom - top),
                }
            )

        if not items:
            return ""

        line_tolerance = max(12.0, median(item["height"] for item in items) * 0.65)
        lines: list[dict[str, object]] = []

        for item in sorted(items, key=lambda current: (current["center_y"], current["left"])):
            matched_line = None
            matched_distance = None

            for line in lines:
                distance = abs(float(line["center_y"]) - float(item["center_y"]))

                if distance > max(line_tolerance, float(line["avg_height"]) * 0.65):
                    continue

                if matched_distance is None or distance < matched_distance:
                    matched_line = line
                    matched_distance = distance

            if matched_line is None:
                lines.append(
                    {
                        "items": [item],
                        "center_y": item["center_y"],
                        "top": item["top"],
                        "avg_height": item["height"],
                    }
                )
                continue

            line_items = matched_line["items"]
            assert isinstance(line_items, list)
            line_items.append(item)
            matched_line["center_y"] = sum(float(entry["center_y"]) for entry in line_items) / len(line_items)
            matched_line["top"] = min(float(entry["top"]) for entry in line_items)
            matched_line["avg_height"] = sum(float(entry["height"]) for entry in line_items) / len(line_items)

        merged_lines = []

        for line in sorted(lines, key=lambda current: float(current["top"])):
            line_items = line["items"]
            assert isinstance(line_items, list)
            line_text = " ".join(str(entry["text"]) for entry in sorted(line_items, key=lambda current: float(current["left"])))
            line_text = re.sub(r"\s+([,.;:!?%)\]}])", r"\1", line_text)
            line_text = re.sub(r"([(\[{])\s+", r"\1", line_text)
            line_text = re.sub(r"\s{2,}", " ", line_text).strip()

            if line_text:
                merged_lines.append(line_text)

        return "\n".join(merged_lines)
