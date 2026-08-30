"""A becsomagolt QtCore és a ténylegesen betöltött Windows ICU ellenőrzése."""
from __future__ import annotations

import ctypes
import json
import sys
from pathlib import Path

from PySide6.QtCore import qVersion


kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint32]
kernel32.GetModuleFileNameW.restype = ctypes.c_uint32
kernel32.GetSystemDirectoryW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
kernel32.GetSystemDirectoryW.restype = ctypes.c_uint32

module = kernel32.GetModuleHandleW("icuuc.dll")
loaded = ctypes.create_unicode_buffer(32768)
system = ctypes.create_unicode_buffer(32768)
if not module or not kernel32.GetModuleFileNameW(module, loaded, len(loaded)):
    raise ctypes.WinError(ctypes.get_last_error())
if not kernel32.GetSystemDirectoryW(system, len(system)):
    raise ctypes.WinError(ctypes.get_last_error())
expected = Path(system.value) / "icuuc.dll"
passed = Path(loaded.value).resolve() == expected.resolve()
print(json.dumps({"frozen": bool(getattr(sys, "frozen", False)), "python": sys.version,
                  "qt": qVersion(), "icu": loaded.value, "systemIcu": str(expected),
                  "passed": passed}, ensure_ascii=False))
raise SystemExit(0 if passed else 1)
