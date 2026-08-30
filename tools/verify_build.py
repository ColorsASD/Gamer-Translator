"""A staging EXE tartalmának statikus ellenőrzése, az alkalmazás elindítása nélkül."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import marshal
import re
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path

import pefile
from PyInstaller.archive.readers import CArchiveReader

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("executable", nargs="?", type=Path, default=root / "dist" / "staging" / "Gamer Translator.exe")
executable = parser.parse_args().executable.resolve()
archive = CArchiveReader(str(executable))
entries = {name.replace("\\", "/"): name for name in archive.toc}
pyz_entry = next(name for name in archive.toc if name.endswith(".pyz"))
pyz = archive.open_embedded_archive(pyz_entry)
checks: dict[str, bool] = {}
source_hashes: dict[str, str] = {}

source_paths = ["main.py", *(path.relative_to(root).as_posix() for path in sorted((root / "gamer_translator").glob("*.py")) if path.name != "__init__.py")]

for relative_path in source_paths:
    module_name = relative_path.removesuffix(".py").replace("/", ".")
    stored_code = marshal.loads(archive.extract("main")) if module_name == "main" else pyz.extract(module_name)
    source = (root / relative_path).read_text(encoding="utf-8")
    expected_code = compile(source, stored_code.co_filename, "exec", dont_inherit=True, optimize=0)
    checks[f"source:{relative_path}"] = stored_code == expected_code
    source_hashes[relative_path] = hashlib.sha256((root / relative_path).read_bytes()).hexdigest()

for relative_path in ("gamer_translator/automation.js", "gamer_translator/assets/icon-128.png"):
    checks[f"asset:{relative_path}"] = relative_path in entries and archive.extract(entries[relative_path]) == (root / relative_path).read_bytes()

for suffix in ("QtWebEngineProcess.exe", "Qt6WebEngineCore.dll", "qtwebengine_resources.pak", "icudtl.dat", "qwindows.dll", "onnxruntime_pybind11_state.pyd"):
    checks[f"runtime:{suffix}"] = any(name.endswith(suffix) for name in entries)

checks["runtime:Windows OCR"] = any("winrt" in name and "windows_media_ocr" in name.lower() and name.endswith(".pyd") for name in entries)
checks["runtime:WinRT runtime"] = any(name.startswith("winrt/_winrt") and name.endswith(".pyd") for name in entries)
checks["runtime:RapidOCR data"] = any(name.startswith("rapidocr/") and name.endswith(".yaml") for name in entries)
checks["runtime:wordfreq Hungarian"] = any(name.startswith("wordfreq/data/") and "hu" in name for name in entries)
checks["runtime:wordfreq English"] = any(name.startswith("wordfreq/data/") and "en" in name for name in entries)

# A Python és az OpenSSL DLL-ek bájtpontos egyezése a javított buildkörnyezettel.
native_hashes: dict[str, str] = {}
runtime_root = Path(sys.base_prefix)
runtime_files = [runtime_root / "python3.dll", runtime_root / f"python{sys.version_info.major}{sys.version_info.minor}.dll", *(runtime_root / "DLLs" / name for name in ("_ssl.pyd", "libssl-3.dll", "libcrypto-3.dll"))]

for runtime_file in runtime_files:
    entry = next((entry for name, entry in entries.items() if name.rsplit("/", 1)[-1] == runtime_file.name), None)
    original_bytes = runtime_file.read_bytes()
    checks[f"runtime:verified {runtime_file.name}"] = entry is not None and archive.extract(entry) == original_bytes
    native_hashes[runtime_file.name] = hashlib.sha256(original_bytes).hexdigest()

for relative_path in ("PySide6/QtCore.pyd", "PySide6/Qt6Core.dll", "PySide6/pyside6.abi3.dll",
                      "shiboken6/Shiboken.pyd", "shiboken6/shiboken6.abi3.dll"):
    original_bytes = (Path(sys.prefix) / "Lib/site-packages" / relative_path).read_bytes()
    checks[f"runtime:verified {relative_path}"] = relative_path in entries and archive.extract(entries[relative_path]) == original_bytes
    native_hashes[relative_path] = hashlib.sha256(original_bytes).hexdigest()

# A Qt a Windows ICU verzióutótag nélküli exportjait használja. Egy PATH-ról bekerült
# Poppler ICU azonos DLL-névvel, de eltérő exportokkal már importkor leállítaná.
checks["runtime:Windows ICU not bundled"] = not any(
    re.fullmatch(r"icu(?:uc|in|dt\d*)\.dll", name.rsplit("/", 1)[-1].lower()) for name in entries
)
system_directory = ctypes.create_unicode_buffer(32768)
get_system_directory = ctypes.windll.kernel32.GetSystemDirectoryW
get_system_directory.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
get_system_directory.restype = ctypes.c_uint32
if not get_system_directory(system_directory, len(system_directory)):
    raise RuntimeError("A Windows rendszerkönyvtára nem határozható meg.")
system_icu = Path(system_directory.value) / "icuuc.dll"
qt_core = pefile.PE(data=archive.extract(entries["PySide6/Qt6Core.dll"]), max_symbol_exports=200000)
required_icu_exports = {symbol.name for dependency in qt_core.DIRECTORY_ENTRY_IMPORT
                        if dependency.dll.lower() == b"icuuc.dll" for symbol in dependency.imports if symbol.name}
windows_icu = pefile.PE(str(system_icu), max_symbol_exports=200000)
system_icu_exports = {symbol.name for symbol in windows_icu.DIRECTORY_ENTRY_EXPORT.symbols if symbol.name}
checks["runtime:Qt ICU exports available from Windows"] = bool(required_icu_exports) and required_icu_exports <= system_icu_exports
system_dependencies = {"icuuc.dll": {"path": str(system_icu), "sha256": hashlib.sha256(system_icu.read_bytes()).hexdigest(),
                                      "requiredExports": sorted(name.decode("ascii") for name in required_icu_exports)}}
qt_core.close()
windows_icu.close()

pe = pefile.PE(str(executable), fast_load=True)
checks["PE:Windows x64 GUI"] = pe.FILE_HEADER.Machine == 0x8664 and pe.OPTIONAL_HEADER.Subsystem == 2
pe.close()
with executable.open("rb") as executable_file:
    executable_sha256 = hashlib.file_digest(executable_file, "sha256").hexdigest()
manifest = {"generatedAt": datetime.now(timezone.utc).isoformat(), "executable": str(executable), "bytes": executable.stat().st_size, "sha256": executable_sha256, "entries": len(entries), "pythonModules": len(pyz.toc), "checks": checks, "sourceSha256": source_hashes, "buildRuntime": {"python": sys.version, "openssl": ssl.OPENSSL_VERSION, "executable": sys.executable, "nativeSha256": native_hashes}, "systemDependencies": system_dependencies}
(executable.parent / "build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(manifest, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(checks.values()) else 1)
