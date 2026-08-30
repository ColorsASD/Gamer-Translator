"""Megismételhető OCR-mérés kizárólag generált, nem személyes képeken.

Példa: python tools/benchmark_ocr.py --model-dir <ellenőrzött modellek> --output <jelentés.json>
A program alapból nem tölt le modellt; a pontos és közelítő találatot külön méri.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from importlib.metadata import PackageNotFoundError, version
import importlib.util
import json
from pathlib import Path
import sys
import time
import unicodedata

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gamer_translator.ocr_service import OCRService


SAMPLES = (
    ("hu_diagnostic", "Árvíztűrő tükörfúrógép", "arial.ttf", 64, False),
    ("hu_round", "Kérlek, gyere vissza a következő körre!", "arial.ttf", 32, False),
    ("hu_quest", "Ősszel új küldetések és erős ellenfelek várnak.", "arial.ttf", 36, False),
    ("hu_meeting", "Tíz perc múlva találkozunk a főtéren.", "arial.ttf", 28, False),
    ("en_hello", "Hello gamer", "arial.ttf", 64, False),
    ("en_round", "Please wait for the next round.", "arial.ttf", 32, False),
    ("en_shield", "Keep your shield up and follow me!", "arial.ttf", 28, False),
    ("en_healer", "Don't push alone, we need a healer.", "arial.ttf", 32, False),
    ("hu_ammo", "Küldj egy TP-t, elfogyott a lőszerem!", "arial.ttf", 24, True),
    ("commands", "/spawn /home base /tp Player_42", "consola.ttf", 24, True),
    ("hu_party", "[Party] Árpi: jövök, várjatok még 2 percet!", "consola.ttf", 22, True),
    ("en_gamer", "gg wp! Heal me at 20 HP, then rush B.", "arial.ttf", 24, True),
    ("hu_accents", "Ági írja: hűvös idő, sűrű köd, őrült szél.", "arial.ttf", 32, False),
    ("holdout_names", "Dóri és Bence később érkeznek.", "arial.ttf", 30, True),
    ("holdout_flag", "Ő már a piros zászlónál vár.", "arial.ttf", 26, False),
    ("holdout_reload", "Indulás előtt töltsd újra a fegyvert!", "consola.ttf", 26, True),
    ("holdout_checkpoint", "Meet at checkpoint C in 15 seconds.", "arial.ttf", 30, False),
    ("holdout_score", "We won 3-2, good game!", "consola.ttf", 26, True),
    ("holdout_commands", "/warp shop /msg Player_7 hello", "consola.ttf", 26, False),
)


def character_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for index, left_character in enumerate(left, 1):
        current = [index]
        for right_index, right_character in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[right_index] + 1, previous[right_index - 1] + (left_character != right_character)))
        previous = current
    return previous[-1]


class TracingEngine:
    def __init__(self, engine, service):
        self.engine = engine
        self.service = service

    def __call__(self, payload, **kwargs):
        result = self.engine(payload, **kwargs)
        self.service.trace.append({
            "engine": "RapidOCR", "variant": self.service.current_variant,
            "texts": list(result.txts or ()), "scores": list(result.scores or ()),
            "boxes": result.boxes.tolist() if getattr(result, "boxes", None) is not None else [],
            "mode": "detect" if kwargs.get("use_det", True) else "overlap_recovery",
        })
        return result


class TracingMixin:
    def __init__(self, root_dir):
        super().__init__(root_dir)
        self.trace = []
        self.current_variant = ""

    def _get_engine(self):
        engine = super()._get_engine()
        if not isinstance(engine, TracingEngine):
            self.engine = TracingEngine(engine, self)
        return self.engine

    def _extract_with_rapidocr(self, variant_name, image_bytes):
        self.current_variant = variant_name
        return super()._extract_with_rapidocr(variant_name, image_bytes)

    def _extract_with_windows_ocr(self, variant_name, image_bytes):
        self.current_variant = variant_name
        return super()._extract_with_windows_ocr(variant_name, image_bytes)

    def _run_windows_ocr(self, image_bytes, language_tag):
        text = super()._run_windows_ocr(image_bytes, language_tag)
        self.trace.append({"engine": f"Windows OCR ({language_tag})", "variant": self.current_variant, "text": text})
        return text


class BenchmarkService(TracingMixin, OCRService):
    pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font-dir", type=Path, default=Path("C:/Windows/Fonts"))
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--candidate-count", type=int, default=5)
    parser.add_argument("--service-source", type=Path, help="Megbízható helyi OCR-forráspéldány összehasonlító futtatáshoz.")
    parser.add_argument("--sample", action="append", choices=[sample[0] for sample in SAMPLES])
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    image_dir = args.output.parent / f"{args.output.stem}-images"
    image_dir.mkdir(exist_ok=True)
    source_path = Path(__file__).resolve().parents[1] / "gamer_translator" / "ocr_service.py"
    service_type = BenchmarkService
    if args.service_source:
        source_path = args.service_source.resolve(strict=True)
        spec = importlib.util.spec_from_file_location("gamer_translator._benchmark_reference", source_path)
        reference = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = reference
        spec.loader.exec_module(reference)
        service_type = type("ReferenceBenchmarkService", (TracingMixin, reference.OCRService), {})
    service = service_type(args.model_dir)
    if not args.allow_download:
        for asset in service._required_assets():
            target = args.model_dir / asset.filename
            if not target.is_file() or service._file_sha256(target) != asset.sha256:
                raise SystemExit(f"Hiányzó vagy hibás helyi modell: {target}")
    versions = {}
    for package in ("rapidocr", "onnxruntime", "Pillow", "wordfreq", "winsdk", "winrt-runtime"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    report = {"python": sys.version, "versions": versions, "windows_languages": service.windows_language_tags, "candidate_count": args.candidate_count,
              "ocr_source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(), "samples": []}
    started_at = time.monotonic()
    for name, text, font_name, size, dark in SAMPLES:
        if args.sample and name not in args.sample:
            continue
        font = ImageFont.truetype(str(args.font_dir / font_name), size)
        box = font.getbbox(text)
        image = Image.new("RGB", (box[2] - box[0] + 64, box[3] - box[1] + 48), "#20252b" if dark else "white")
        ImageDraw.Draw(image).text((32 - box[0], 24 - box[1]), text, font=font, fill="white" if dark else "black")
        image_path = image_dir / f"{name}.png"
        image.save(image_path)
        service.trace = []
        sample_started = time.monotonic()
        candidates = service._collect_ranked_candidates(image_path.read_bytes(), minimum_candidate_count=args.candidate_count)
        selected = service._select_unique_candidates(candidates, args.candidate_count)
        actual = selected[0].text if selected else ""
        sample = {
            "name": name, "expected": text, "actual": actual, "font": font_name, "font_size": size, "dark": dark,
            "exact": actual == text,
            "character_errors": character_distance(unicodedata.normalize("NFC", text), unicodedata.normalize("NFC", actual)),
            "expected_characters": len(text), "expected_in_candidates": any(candidate.text == text for candidate in selected),
            "seconds": round(time.monotonic() - sample_started, 3),
            "candidates": [asdict(candidate) for candidate in selected], "trace": service.trace,
        }
        report["samples"].append(sample)
        print(json.dumps({key: sample[key] for key in ("name", "actual", "exact", "character_errors", "seconds")}, ensure_ascii=True), flush=True)
        report["summary"] = {
            "samples": len(report["samples"]), "exact": sum(item["exact"] for item in report["samples"]),
            "character_errors": sum(item["character_errors"] for item in report["samples"]),
            "expected_characters": sum(item["expected_characters"] for item in report["samples"]),
            "seconds": round(time.monotonic() - started_at, 3),
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
