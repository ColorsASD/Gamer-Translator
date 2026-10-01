"""Helyi, tartalommentes eseménynapló külön háttéríróval.

A napló kizárólag ismert állapotokat és számszerű mérési adatokat fogad el.
Vágólapszöveg, fordítás, kép, URL, fájlút és kivételüzenet nem kerül bele.
"""
from __future__ import annotations

import atexit
import ctypes
import json
import math
import os
import queue
import re
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from types import TracebackType
from typing import Any


MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5
QUEUE_CAPACITY = 4096
LOG_FILENAME = "gamer-translator.jsonl"
_TOKEN = re.compile(r"[A-Za-z0-9_.:-]{1,64}\Z")
_EVENT = re.compile(r"[A-Za-z0-9_.:-]{1,96}\Z")
_REQUEST_ID = re.compile(r"(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})\Z")
_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_TOKEN_FIELDS = frozenset({
    "action", "stage", "kind", "reason", "error_type", "state", "mode",
    "engine", "result", "trigger", "source", "code", "severity", "method",
})
_NUMBER_FIELDS = frozenset({
    "duration_ms", "elapsed_ms", "timeout_ms", "interval_ms", "attempt", "count",
    "queue_size", "dropped_count", "write_failures", "clipboard_sequence", "generation",
    "text_length", "image_width", "image_height", "image_bytes", "image_encoding_ms",
    "width", "height", "bytes", "size_bytes", "response_count", "attachment_count",
    "selected_file_count", "prompt_length", "file_count", "assistant_count", "user_count",
    "progress", "pending_count", "changed_count", "error_count",
    "lag_ms", "exit_code", "line_number", "code", "severity", "threads", "intra_threads",
    "inter_threads", "cpu_count", "process_cpu_seconds", "process_cpu_percent",
    "process_memory_bytes", "private_memory_bytes", "system_memory_total_bytes",
    "system_memory_available_bytes", "system_memory_load_percent", "renderer_pid",
    "renderer_cpu_seconds", "renderer_cpu_percent", "renderer_memory_bytes",
    "renderer_private_memory_bytes",
})
_BOOL_FIELDS = frozenset({
    "enabled", "success", "ready", "busy", "stale", "cancelled", "accepted", "has_text",
    "has_image", "has_response", "submitted", "visible", "active", "monitoring_enabled",
    "ocr_enabled", "game_mode_enabled", "loading", "background", "gpu_enabled",
    "followup", "response_pending", "main_window_visible", "minimized", "pending", "fresh",
    "stable", "has_identity", "auto_submit", "copy_response", "late", "ok",
})
_PACKAGE_DIR = Path(__file__).resolve().parent
_KNOWN_FILES = {
    os.path.normcase(str(_PACKAGE_DIR / name)): name
    for name in (
        "diagnostics.py", "main_window.py", "settings_store.py", "defaults.py",
        "hotkeys.py", "ocr_service.py", "self_test.py", "__init__.py",
    )
}
_KNOWN_FILES[os.path.normcase(str(_PACKAGE_DIR.parent / "main.py"))] = "main.py"
_KNOWN_MODULES = {
    f"gamer_translator.{Path(name).stem}": name for name in _KNOWN_FILES.values() if name != "main.py"
}
_writer: _BackgroundWriter | None = None
_setup_lock = threading.RLock()
_hooks_lock = threading.Lock()
_hook_state = threading.local()
_original_sys_hook: Any = None
_original_thread_hook: Any = None
_cpu_lock = threading.Lock()
_last_cpu_sample: tuple[float, float] | None = None
_renderer_cpu_samples: OrderedDict[int, tuple[float, float, int]] = OrderedDict()
_MAX_RENDERER_SAMPLES = 16


def _safe_token(value: Any) -> str | None:
    return value if type(value) is str and _TOKEN.fullmatch(value) else None


def _metadata(fields: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in fields.items():
        if type(key) is not str:
            continue
        if key in _BOOL_FIELDS and type(value) is bool:
            result[key] = value
        elif key in _NUMBER_FIELDS and type(value) in (int, float):
            if -10**18 <= value <= 10**18 and (type(value) is int or math.isfinite(value)):
                result[key] = value
        elif key in _TOKEN_FIELDS and (token := _safe_token(value)) is not None:
            result[key] = token
    return result


def _exception_fields(error: BaseException, traceback: TracebackType | None = None) -> dict[str, Any]:
    frames = []
    current = traceback if traceback is not None else error.__traceback__
    while current is not None and len(frames) < 32:
        code = current.tb_frame.f_code
        # Külső vagy felhasználó által megadott fájl neve sem kerül a naplóba.
        filename = _KNOWN_FILES.get(os.path.normcase(code.co_filename))
        if filename is None:
            # A csomagolt EXE kódobjektuma eltérő build útvonalat is hordozhat.
            module_name = current.tb_frame.f_globals.get("__name__")
            filename = _KNOWN_MODULES.get(module_name, "external") if type(module_name) is str else "external"
        frames.append({
            "file": filename,
            "function": _safe_token(code.co_name) or "unknown",
            "line": int(current.tb_lineno),
        })
        current = current.tb_next
    return {"error_type": _safe_token(type(error).__name__) or "Exception", "traceback": frames}


class _BackgroundWriter:
    def __init__(self, directory: Path, app_version: str) -> None:
        self.directory = directory
        self.app_version = _safe_token(app_version) or "unknown"
        self.session_id = uuid.uuid4().hex
        self.started = time.monotonic()
        self.queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=QUEUE_CAPACITY)
        self.stop = threading.Event()
        self.dropped_lock = threading.Lock()
        self.dropped = 0
        self.write_failures = 0
        self.file: Any = None
        self.file_size = 0
        self.thread = threading.Thread(target=self._run, name="GamerTranslatorDiagnostics", daemon=True)

    def record(self, event: str, level: str, request_id: Any, fields: dict[str, Any]) -> dict[str, Any]:
        record = {
            "schema_version": 1,
            "timestamp": datetime.now().astimezone().isoformat(timespec="milliseconds"),
            "monotonic_ms": round((time.monotonic() - self.started) * 1000, 3),
            "session_id": self.session_id,
            "pid": os.getpid(),
            "thread_id": threading.get_ident(),
            "app_version": self.app_version,
            "event": event,
            "level": level if type(level) is str and level in _LEVELS else "INFO",
        }
        if type(request_id) is str and _REQUEST_ID.fullmatch(request_id):
            record["request_id"] = request_id.replace("-", "").lower()
        record.update(fields)
        return record

    def enqueue(self, record: dict[str, Any]) -> None:
        if self.stop.is_set():
            return
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            with self.dropped_lock:
                self.dropped += 1

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
        size = len(line.encode("utf-8"))
        if self.file is None:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.file = (self.directory / LOG_FILENAME).open("a", encoding="utf-8", newline="\n")
            self.file_size = self.file.tell()
        if self.file_size and self.file_size + size > MAX_LOG_BYTES:
            self._close_file()
            path = self.directory / LOG_FILENAME
            oldest = self.directory / f"{LOG_FILENAME}.{BACKUP_COUNT}"
            oldest.unlink(missing_ok=True)
            for number in range(BACKUP_COUNT - 1, 0, -1):
                source = self.directory / f"{LOG_FILENAME}.{number}"
                if source.exists():
                    source.replace(self.directory / f"{LOG_FILENAME}.{number + 1}")
            path.replace(self.directory / f"{LOG_FILENAME}.1")
            self.file = path.open("a", encoding="utf-8", newline="\n")
            self.file_size = 0
        self.file.write(line)
        self.file.flush()
        self.file_size += size

    def _close_file(self) -> None:
        handle, self.file = self.file, None
        if handle is not None:
            try:
                handle.close()
            except (OSError, ValueError):
                pass

    def _write(self, record: dict[str, Any]) -> None:
        try:
            self._append(record)
            if self.write_failures:
                self._append(self.record("diagnostics.write_recovered", "WARNING", None, {"write_failures": self.write_failures}))
                self.write_failures = 0
        except Exception:
            # A megtelt vagy nem elérhető lemez nem állíthatja le a fordítást.
            self.write_failures += 1
            self._close_file()

    def _run(self) -> None:
        try:
            while not self.stop.is_set() or not self.queue.empty():
                try:
                    record = self.queue.get(timeout=0.05)
                except queue.Empty:
                    record = None
                if record is not None:
                    try:
                        self._write(record)
                    finally:
                        self.queue.task_done()
                with self.dropped_lock:
                    dropped, self.dropped = self.dropped, 0
                if dropped:
                    self._write(self.record("diagnostics.queue_dropped", "WARNING", None, {"dropped_count": dropped}))
        finally:
            self._close_file()

    def shutdown(self) -> None:
        self.enqueue(self.record("diagnostics.session_stopped", "INFO", None, {}))
        self.stop.set()
        if self.thread is not threading.current_thread() and self.thread.ident is not None:
            # Hibás lemez esetén a kilépésnek is véges ideje maradjon.
            self.thread.join(timeout=2.0)


def setup_diagnostics(root_dir: Path, *, app_version: str = "unknown") -> Path:
    """Elindítja a helyi naplót; ugyanarra a könyvtárra ismételve nem indít új írót."""
    global _writer
    directory = Path(root_dir) / "logs"
    with _setup_lock:
        if _writer is not None and _writer.directory == directory and _writer.app_version == (_safe_token(app_version) or "unknown"):
            return directory
        previous, _writer = _writer, None
        if previous is not None:
            previous.shutdown()
        writer = _BackgroundWriter(directory, app_version)
        try:
            writer.thread.start()
        except Exception:
            return directory
        _writer = writer
        log_event("diagnostics.session_started", mode="automatic")
    return directory


def get_log_directory() -> Path | None:
    """Az aktív helyi napló könyvtárát adja vissza."""
    writer = _writer
    return writer.directory if writer is not None else None


def log_event(event: str, *, level: str = "INFO", request_id: str | None = None, **fields: Any) -> None:
    """Nem blokkoló eseményrögzítés; az ismeretlen és tartalmi mezőket kihagyja."""
    try:
        writer = _writer
        if writer is not None and type(event) is str and _EVENT.fullmatch(event):
            writer.enqueue(writer.record(event, level, request_id, _metadata(fields)))
    except Exception:
        pass


def log_exception(event: str, error: BaseException, *, request_id: str | None = None, **fields: Any) -> None:
    """A kivétel típusa és szerkezeti trace kerül be, az üzenete nem."""
    try:
        writer = _writer
        if writer is not None and type(event) is str and _EVENT.fullmatch(event):
            metadata = _metadata(fields)
            metadata.update(_exception_fields(error))
            writer.enqueue(writer.record(event, "ERROR", request_id, metadata))
    except Exception:
        pass


def _sys_exception_hook(error_type: type[BaseException], error: BaseException, traceback: TracebackType | None) -> None:
    if getattr(_hook_state, "active", False):
        return
    _hook_state.active = True
    try:
        try:
            writer = _writer
            if writer is not None:
                writer.enqueue(writer.record("python.unhandled_exception", "CRITICAL", None, _exception_fields(error, traceback)))
        except Exception:
            pass
        original = _original_sys_hook
        if original is not None:
            try:
                original(error_type, error, traceback)
            except BaseException:
                pass
    finally:
        _hook_state.active = False


def _thread_exception_hook(args: Any) -> None:
    if getattr(_hook_state, "active", False):
        return
    _hook_state.active = True
    try:
        try:
            writer = _writer
            if writer is not None:
                writer.enqueue(writer.record("python.thread_exception", "CRITICAL", None, _exception_fields(args.exc_value, args.exc_traceback)))
        except Exception:
            pass
        original = _original_thread_hook
        if original is not None:
            try:
                original(args)
            except BaseException:
                pass
    finally:
        _hook_state.active = False


def install_exception_hooks() -> None:
    """A Python főszál és háttérszál kezeletlen hibáit is rögzíti."""
    global _original_sys_hook, _original_thread_hook
    with _hooks_lock:
        if sys.excepthook is not _sys_exception_hook:
            _original_sys_hook = sys.excepthook
            sys.excepthook = _sys_exception_hook
        if threading.excepthook is not _thread_exception_hook:
            _original_thread_hook = threading.excepthook
            threading.excepthook = _thread_exception_hook


def shutdown_diagnostics() -> None:
    """Kiüríti a naplósort, bezárja az írót és visszaállítja a saját hibafigyelőit."""
    global _writer, _original_sys_hook, _original_thread_hook
    with _setup_lock:
        writer, _writer = _writer, None
        if writer is not None:
            writer.shutdown()
    with _hooks_lock:
        if sys.excepthook is _sys_exception_hook and _original_sys_hook is not None:
            sys.excepthook = _original_sys_hook
        if threading.excepthook is _thread_exception_hook and _original_thread_hook is not None:
            threading.excepthook = _original_thread_hook
        _original_sys_hook = None
        _original_thread_hook = None


def _renderer_cpu_percent(pid: int, created: int, cpu_seconds: float, now: float, cpu_count: int) -> float | None:
    with _cpu_lock:
        previous = _renderer_cpu_samples.pop(pid, None)
        _renderer_cpu_samples[pid] = (now, cpu_seconds, created)
        while len(_renderer_cpu_samples) > _MAX_RENDERER_SAMPLES:
            _renderer_cpu_samples.popitem(last=False)
    if previous is None or previous[2] != created or now <= previous[0]:
        return None
    percent = 100 * max(0.0, cpu_seconds - previous[1]) / (now - previous[0]) / cpu_count
    return round(min(100.0, percent), 3)


def _renderer_snapshot(kernel32: Any, memory_query: Any, memory_type: Any, pid: int, cpu_count: int) -> dict[str, int | float]:
    """Csak a megadott Chromium folyamathoz nyit rövid életű olvasási handlet."""
    from ctypes import wintypes

    result: dict[str, int | float] = {}
    handle = None
    try:
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ
        handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)
        if not handle:
            return result
        result["renderer_pid"] = pid
        memory = memory_type()
        memory.cb = ctypes.sizeof(memory)
        if memory_query(handle, ctypes.byref(memory), memory.cb):
            result.update(renderer_memory_bytes=int(memory.working_set), renderer_private_memory_bytes=int(memory.private_usage))
        times = [wintypes.FILETIME() for _ in range(4)]
        kernel32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        if kernel32.GetProcessTimes(handle, *(ctypes.byref(value) for value in times)):
            ticks = [(int(value.dwHighDateTime) << 32) | int(value.dwLowDateTime) for value in times]
            cpu_seconds = (ticks[2] + ticks[3]) / 10_000_000
            result["renderer_cpu_seconds"] = round(cpu_seconds, 4)
            percent = _renderer_cpu_percent(pid, ticks[0], cpu_seconds, time.monotonic(), cpu_count)
            if percent is not None:
                result["renderer_cpu_percent"] = percent
    except Exception:
        pass
    finally:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass
    return result


def resource_snapshot(renderer_pid: int = 0) -> dict[str, int | float]:
    """Olcsó mérés a főfolyamatra és opcionálisan az ismert renderer PID-re."""
    global _last_cpu_sample
    result: dict[str, int | float] = {"cpu_count": os.cpu_count() or 1}
    try:
        cpu_seconds = time.process_time()
        if sys.platform == "win32":
            from ctypes import wintypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", wintypes.DWORD), ("load", wintypes.DWORD)] + [
                    (name, ctypes.c_ulonglong) for name in (
                        "total_physical", "available_physical", "total_page", "available_page",
                        "total_virtual", "available_virtual", "extended_virtual",
                    )
                ]

            class ProcessMemory(ctypes.Structure):
                _fields_ = [("cb", wintypes.DWORD), ("page_faults", wintypes.DWORD)] + [
                    (name, ctypes.c_size_t) for name in (
                        "peak_working_set", "working_set", "peak_paged_pool", "paged_pool",
                        "peak_nonpaged_pool", "nonpaged_pool", "pagefile", "peak_pagefile", "private_usage",
                    )
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                result.update(
                    system_memory_total_bytes=int(memory.total_physical),
                    system_memory_available_bytes=int(memory.available_physical),
                    system_memory_load_percent=int(memory.load),
                )
            process_memory = ProcessMemory()
            process_memory.cb = ctypes.sizeof(process_memory)
            query = kernel32.K32GetProcessMemoryInfo
            query.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemory), wintypes.DWORD]
            if query(kernel32.GetCurrentProcess(), ctypes.byref(process_memory), process_memory.cb):
                result.update(process_memory_bytes=int(process_memory.working_set), private_memory_bytes=int(process_memory.private_usage))
            if type(renderer_pid) is int and 0 < renderer_pid <= 0xFFFFFFFF:
                result.update(_renderer_snapshot(kernel32, query, ProcessMemory, renderer_pid, int(result["cpu_count"])))
        now = time.monotonic()
        result["process_cpu_seconds"] = round(cpu_seconds, 4)
        with _cpu_lock:
            previous, _last_cpu_sample = _last_cpu_sample, (now, cpu_seconds)
        if previous is not None and now > previous[0]:
            percent = 100 * max(0.0, cpu_seconds - previous[1]) / (now - previous[0]) / result["cpu_count"]
            result["process_cpu_percent"] = round(min(100.0, percent), 3)
    except Exception:
        pass
    return result


atexit.register(shutdown_diagnostics)
