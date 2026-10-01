"""Tartalommentes Gamer Translator napló olvasása idővonalként vagy összesítésként.

Példa: python tools/read_diagnostics.py --last 200 --level ERROR
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gamer_translator import diagnostics


_ID = re.compile(r"[0-9a-fA-F]{32}\Z")
_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z",
    re.ASCII,
)
_SEVERITY = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
_MAX_LINE_BYTES = 64 * 1024


@dataclass
class ReadStats:
    files_read: int = 0
    skipped_lines: int = 0
    unreadable_files: int = 0


def default_log_directory() -> Path:
    """A profil inicializálása és a beállítások olvasása nélkül keresi a naplóhelyet."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_app_data) / "Gamer Translator" if local_app_data else Path.home() / ".gamer-translator"
    return root / "logs"


def sanitize_record(raw: Any) -> dict[str, Any] | None:
    """Idegen JSONL fájlból is csak ellenőrzött szerkezeti adatot enged a kimenetre."""
    if type(raw) is not dict:
        return None
    event, timestamp, level = raw.get("event"), raw.get("timestamp"), raw.get("level")
    if type(event) is not str or not diagnostics._EVENT.fullmatch(event):
        return None
    if type(level) is not str or level not in _SEVERITY:
        return None
    if type(timestamp) is not str or not _TIMESTAMP.fullmatch(timestamp):
        return None
    try:
        instant = datetime.fromisoformat(timestamp)
        if instant.utcoffset() is None:
            return None
        local_timestamp = instant.astimezone().isoformat(timespec="milliseconds")
    except (ValueError, OverflowError, OSError):
        return None
    result = {"timestamp": local_timestamp, "event": event, "level": level}
    for key in ("request_id", "session_id"):
        value = raw.get(key)
        if type(value) is str and _ID.fullmatch(value):
            result[key] = value.lower()
    for key in ("pid", "thread_id", "monotonic_ms"):
        value = raw.get(key)
        if type(value) in (int, float) and 0 <= value <= 10**18 and math.isfinite(value):
            result[key] = value
    version = diagnostics._safe_token(raw.get("app_version"))
    if version is not None:
        result["app_version"] = version
    result.update(diagnostics._metadata(raw))
    return result


def iter_records(directory: Path, stats: ReadStats) -> Iterator[dict[str, Any]]:
    """A forgatott fájlokat a legrégebbitől az aktív naplóig dolgozza fel."""
    names = [f"{diagnostics.LOG_FILENAME}.{number}" for number in range(diagnostics.BACKUP_COUNT, 0, -1)]
    names.append(diagnostics.LOG_FILENAME)
    for name in names:
        try:
            with (directory / name).open("rb") as handle:
                stats.files_read += 1
                while line := handle.readline(_MAX_LINE_BYTES + 1):
                    if len(line) > _MAX_LINE_BYTES:
                        stats.skipped_lines += 1
                        while line and not line.endswith(b"\n"):
                            line = handle.readline(_MAX_LINE_BYTES + 1)
                        continue
                    if not line.strip():
                        continue
                    try:
                        raw = json.loads(line.decode("utf-8"))
                        record = sanitize_record(raw)
                    except (UnicodeError, ValueError, RecursionError):
                        record = None
                    if record is None:
                        stats.skipped_lines += 1
                    else:
                        yield record
        except FileNotFoundError:
            continue
        except OSError:
            stats.unreadable_files += 1


def format_record(record: dict[str, Any]) -> str:
    """Az összes megjelenített mezőt újra megszűri, nyers JSON-t nem ír ki."""
    safe = sanitize_record(record)
    if safe is None:
        return ""
    parts = [safe["timestamp"], f"[{safe['level']}]", safe["event"]]
    request_id = safe.get("request_id")
    if request_id:
        parts.append(f"request={request_id}")
    for key, value in sorted(diagnostics._metadata(safe).items()):
        rendered = str(value).lower() if type(value) is bool else str(value)
        parts.append(f"{key}={rendered}")
    return " ".join(parts)


def _request_id(value: str) -> str:
    if not _ID.fullmatch(value):
        raise argparse.ArgumentTypeError("A kérésazonosító 32 hexadecimális karakterből álljon.")
    return value.lower()


def _last_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Az eseményszám egész szám legyen.") from None
    if not 1 <= count <= 100_000:
        raise argparse.ArgumentTypeError("Az eseményszám 1 és 100000 között legyen.")
    return count


def _level(value: str) -> str:
    return "mind" if value.lower() == "mind" else value.upper()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", type=Path, default=default_log_directory(), help="A helyi JSONL naplók könyvtára.")
    parser.add_argument("--request-id", type=_request_id, help="Szűrés egyetlen, 32 hexadecimális karakterű kérésazonosítóra.")
    parser.add_argument("--last", type=_last_count, default=200, metavar="N", help="Az idővonal utolsó N eseménye; alapérték: 200.")
    parser.add_argument("--level", type=_level, choices=["mind", *_SEVERITY], default="mind", help="Minimum súlyosság; mind: összes esemény.")
    parser.add_argument("--summary", action="store_true", help="A teljes napló szűrt eseményeinek összesítése; a --last csak az idővonalra vonatkozik.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stats = ReadStats()
    timeline: deque[dict[str, Any]] = deque(maxlen=args.last)
    events: Counter[str] = Counter()
    requests: set[str] = set()
    matching = errors = 0
    for record in iter_records(args.log_dir, stats):
        if args.request_id and record.get("request_id") != args.request_id:
            continue
        if args.level != "mind" and _SEVERITY[record["level"]] < _SEVERITY[args.level]:
            continue
        if args.summary:
            matching += 1
            errors += record["level"] in {"ERROR", "CRITICAL"}
            events[record["event"]] += 1
            if request_id := record.get("request_id"):
                requests.add(request_id)
        else:
            timeline.append(record)
    if stats.skipped_lines:
        print(f"Kihagyott hibás vagy hiányos sorok: {stats.skipped_lines}.", file=sys.stderr)
    if stats.unreadable_files:
        print(f"Nem olvasható naplófájlok: {stats.unreadable_files}.", file=sys.stderr)
    if not stats.files_read:
        print("Nem található olvasható eseménynapló a megadott könyvtárban.", file=sys.stderr)
        return 1
    if args.summary:
        print(f"Események: {matching}")
        print(f"Hibák (ERROR/CRITICAL): {errors}")
        print(f"Kérések: {len(requests)}")
        for event, count in sorted(events.items()):
            print(f"{event}: {count}")
    elif timeline:
        for record in timeline:
            print(format_record(record))
    else:
        print("Nincs a szűrésnek megfelelő esemény.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
