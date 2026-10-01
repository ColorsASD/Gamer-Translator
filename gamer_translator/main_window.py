from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import winsound
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from PySide6.QtCore import QBuffer, QEasingCurve, QEvent, QEventLoop, QIODevice, QPoint, Property, QPropertyAnimation, QSignalBlocker, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QGuiApplication, QIcon, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QCheckBox,
    QFormLayout,
    QGraphicsBlurEffect,
    QFrame,
    QGraphicsDropShadowEffect,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from .defaults import APP_NAME, CHATGPT_HOSTS, CHATGPT_URL, DEFAULT_RESPONSE_TIMEOUT_MS, DEFAULT_SETTINGS, WINDOW_TITLE
from .diagnostics import log_event, log_exception, resource_snapshot
from .hotkeys import (
    HotkeyEdit,
    MOUSE_KEYCODES,
    MOD_ALTGR,
    active_hotkey_editor,
    current_hotkey_modifiers,
    format_hotkey_definition,
    parse_hotkey_definition,
)
from .ocr_service import OCRService
from .settings_store import AppSettings, LastRunStatus, SettingsStore

BROWSER_CONSOLE_DEBUG = os.environ.get("GAMER_TRANSLATOR_DEBUG_BROWSER", "").strip() == "1"
UI_FRAME_INTERVAL_MS = 20
UI_FRAME_INTERVAL_SECONDS = UI_FRAME_INTERVAL_MS / 1000.0
GAME_MODE_BACKGROUND_FRAME_INTERVAL_MS = 40
IDLE_FRAME_INTERVAL_MS = 60
BACKGROUND_IDLE_FRAME_INTERVAL_MS = 250
SUSPENDED_FRAME_INTERVAL_MS = 1200
BACKGROUND_TASK_EVENT_INTERVAL_MS = 40
SCREEN_CLIP_ARM_TIMEOUT_SECONDS = 45.0
AUTOMATION_SELF_HEAL_TIMEOUT_BUFFER_MS = 70000
AUTOMATION_SCRIPT_VERSION = "2026-10-01-2"
INTERACTION_HEARTBEAT_INTERVAL_MS = 250
INTERACTION_STALE_RESET_SECONDS = 8.0
RESPONSE_FOLLOWUP_IDLE_TIMEOUT_SECONDS = 20.0
RESPONSE_FOLLOWUP_MAX_TIMEOUT_SECONDS = 120.0
RESPONSE_FOLLOWUP_MAX_ERROR_COUNT = 5
MAX_CLIPBOARD_IMAGE_PIXELS = 40_000_000
MAX_CLIPBOARD_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PENDING_CLIPBOARD_IMAGES = 4
# Csak a saját begépelés kerülheti meg a gyorsgombszűrést; a külső
# makrók/injektált események ugyanúgy kezelendők, mint a fizikai bevitel.
OWN_INPUT_MARKER = uuid.uuid4().int & ((1 << (ctypes.sizeof(ctypes.c_void_p) * 8)) - 1)

if sys.platform == "win32":
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi
    kernel32 = ctypes.windll.kernel32
    ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
    LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long

    HWND_TOPMOST = -1
    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOACTIVATE = 0x0010
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_CONTINUOUS = 0x80000000
    INPUT_KEYBOARD = 1
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_UNICODE = 0x0004
    KEYEVENTF_SCANCODE = 0x0008
    MAPVK_VK_TO_VSC = 0
    HC_ACTION = 0
    WH_KEYBOARD_LL = 13
    WH_MOUSE_LL = 14
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    LLKHF_INJECTED = 0x10
    LLMHF_INJECTED = 0x01
    WM_XBUTTONDOWN = 0x020B
    WM_XBUTTONUP = 0x020C
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    VK_SHIFT = 0x10
    VK_LWIN = 0x5B
    VK_RWIN = 0x5C
    VK_RETURN = 0x0D
    VK_TAB = 0x09
    THREAD_PRIORITY_ERROR_RETURN = 0x7FFFFFFF
    THREAD_PRIORITY_LOWEST = -2
    DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    DWMWA_WINDOW_CORNER_PREFERENCE = 33
    DWMWCP_ROUND = 2

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUTUNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("union",)
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", INPUTUNION),
        ]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class MSLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("pt", wintypes.POINT),
            ("mouseData", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    user32.GetKeyboardLayout.restype = wintypes.HANDLE
    user32.GetKeyState.argtypes = (ctypes.c_int,)
    user32.GetKeyState.restype = ctypes.c_short
    user32.VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HANDLE)
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HANDLE
    user32.CallNextHookEx.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HANDLE,)
    user32.UnhookWindowsHookEx.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = (
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    )
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = ()
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.restype = wintypes.BOOL
    dwmapi.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    kernel32.GetCurrentThread.argtypes = ()
    kernel32.GetCurrentThread.restype = wintypes.HANDLE
    kernel32.GetCurrentThreadId.argtypes = ()
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    kernel32.GetLastError.argtypes = ()
    kernel32.GetLastError.restype = wintypes.DWORD
    kernel32.SetLastError.argtypes = (wintypes.DWORD,)
    kernel32.SetLastError.restype = None
    kernel32.GetThreadPriority.argtypes = (wintypes.HANDLE,)
    kernel32.GetThreadPriority.restype = ctypes.c_int
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    kernel32.SetThreadExecutionState.argtypes = (wintypes.ULONG,)
    kernel32.SetThreadExecutionState.restype = wintypes.ULONG
    kernel32.SetThreadPriority.argtypes = (wintypes.HANDLE, ctypes.c_int)
    kernel32.SetThreadPriority.restype = wintypes.BOOL


def resource_path(relative_path: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")) / relative_path

    return Path(__file__).resolve().parents[1] / relative_path


def build_unicode_inputs(text: str) -> list[INPUT]:
    inputs: list[INPUT] = []

    for character in text:
        if character == "\r":
            continue

        if character == "\n":
            inputs.extend(build_virtual_key_inputs(VK_RETURN))
            continue

        if character == "\t":
            inputs.extend(build_virtual_key_inputs(VK_TAB))
            continue

        encoded_character = character.encode("utf-16-le")

        for index in range(0, len(encoded_character), 2):
            scan_code = int.from_bytes(encoded_character[index : index + 2], "little")
            inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=OWN_INPUT_MARKER)))
            inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=OWN_INPUT_MARKER)))

    return inputs


def build_virtual_key_inputs(virtual_key: int) -> list[INPUT]:
    return [
        build_scan_code_input(virtual_key),
        build_scan_code_input(virtual_key, key_up=True),
    ]


def build_key_input(virtual_key: int, *, key_up: bool = False) -> INPUT:
    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=virtual_key,
            wScan=0,
            dwFlags=KEYEVENTF_KEYUP if key_up else 0,
            time=0,
            dwExtraInfo=OWN_INPUT_MARKER,
        ),
    )


def is_extended_virtual_key(virtual_key: int) -> bool:
    return virtual_key in {
        0x21,
        0x22,
        0x23,
        0x24,
        0x25,
        0x26,
        0x27,
        0x28,
        0x2D,
        0x2E,
        0x6F,
        0x90,
        0x91,
        VK_MENU,
        VK_RWIN,
    }


def build_scan_code_input(virtual_key: int, *, key_up: bool = False, keyboard_layout: int | None = None) -> INPUT:
    scan_code = (user32.MapVirtualKeyExW(virtual_key, MAPVK_VK_TO_VSC, keyboard_layout)
                 if keyboard_layout else user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC))
    flags = KEYEVENTF_SCANCODE

    if key_up:
        flags |= KEYEVENTF_KEYUP

    if is_extended_virtual_key(virtual_key):
        flags |= KEYEVENTF_EXTENDEDKEY

    if type(scan_code) is not int or scan_code == 0:
        return build_key_input(virtual_key, key_up=key_up)

    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=OWN_INPUT_MARKER,
        ),
    )


def build_modified_key_inputs(modifier_virtual_key: int, key_virtual_key: int) -> list[INPUT]:
    return [
        build_key_input(modifier_virtual_key),
        build_key_input(key_virtual_key),
        build_key_input(key_virtual_key, key_up=True),
        build_key_input(modifier_virtual_key, key_up=True),
    ]


def build_character_inputs(character: str, *, keyboard_layout: int | None = None, caps_lock: bool | None = None) -> list[INPUT]:
    if sys.platform != "win32":
        return []

    if character == "\r":
        return []

    if character == "\n":
        return build_virtual_key_inputs(VK_RETURN)

    if character == "\t":
        return build_virtual_key_inputs(VK_TAB)

    if ord(character) > 0xFFFF:
        return build_unicode_inputs(character)

    if caps_lock is None:
        caps_lock = _typing_caps_lock_enabled()
    if caps_lock and character.isalpha():
        # A CapsLock nem fordíthatja meg a kész fordítás betűinek méretét.
        # Unicode-bevitelhez nem nyomunk Shiftet és nem kapcsoljuk a CapsLockot.
        return build_unicode_inputs(character)

    if keyboard_layout == 0:
        return build_unicode_inputs(character)
    keyboard_layout = keyboard_layout if keyboard_layout is not None else user32.GetKeyboardLayout(0)
    mapping = user32.VkKeyScanExW(character, keyboard_layout)

    if mapping == -1:
        return build_unicode_inputs(character)

    virtual_key = mapping & 0xFF
    shift_state = (mapping >> 8) & 0xFF
    modifier_keys: list[int] = []

    if shift_state & 0x01:
        modifier_keys.append(VK_SHIFT)

    if shift_state & 0x02:
        modifier_keys.append(VK_CONTROL)

    if shift_state & 0x04:
        modifier_keys.append(VK_MENU)

    inputs: list[INPUT] = []

    for modifier_key in modifier_keys:
        inputs.append(build_scan_code_input(modifier_key, keyboard_layout=keyboard_layout))

    inputs.append(build_scan_code_input(virtual_key, keyboard_layout=keyboard_layout))
    inputs.append(build_scan_code_input(virtual_key, key_up=True, keyboard_layout=keyboard_layout))

    for modifier_key in reversed(modifier_keys):
        inputs.append(build_scan_code_input(modifier_key, key_up=True, keyboard_layout=keyboard_layout))

    return inputs


def _typing_keyboard_layout(target_window: int) -> int:
    try:
        thread_id = user32.GetWindowThreadProcessId(target_window, None)
        if type(thread_id) is int and thread_id > 0:
            layout = user32.GetKeyboardLayout(thread_id)
            return layout if type(layout) is int and layout else 0
    except Exception:
        pass
    return 0


def _typing_modifiers_pressed() -> bool:
    for virtual_key in (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN):
        state = user32.GetAsyncKeyState(virtual_key)
        if type(state) is int and state & 0x8000:
            return True
    return False


def _typing_caps_lock_enabled() -> bool:
    state = user32.GetKeyState(0x14)
    return type(state) is int and bool(state & 1)


def _typing_event_flags(target_window: int) -> QEventLoop.ProcessEventsFlag:
    try:
        process_id = wintypes.DWORD()
        user32.GetWindowThreadProcessId(target_window, ctypes.byref(process_id))
        if process_id.value == os.getpid():
            # A saját Qt célmező keypress üzeneteit karakterenként is fel kell
            # dolgozni, amíg a hozzájuk tartozó Shift/AltGr állapot érvényes.
            return QEventLoop.ProcessEventsFlag.AllEvents
    except Exception:
        pass
    return QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents


def _typing_snapshot_error(window: Any, text: str, request_id: str, generation: int | None = None) -> str | None:
    if getattr(window, "operations_cancelled", False) or getattr(window, "exit_requested", False):
        return "shutdown"
    if generation is not None and generation != getattr(window, "hotkey_generation", None):
        return "hotkey_changed"
    if request_id != getattr(window, "latest_translation_request_id", ""):
        return "new_request"
    if (window.last_translated_text != text
            or request_id and request_id != getattr(window, "translation_result_request_id", "")
            or not getattr(window, "translation_result_complete", True)):
        return "translation_changed"
    return None


def _partial_input_releases(inputs: list[INPUT], inserted_count: int) -> list[INPUT]:
    pressed: dict[tuple[int, int, int], INPUT] = {}
    for entry in inputs[:inserted_count]:
        identity = (int(entry.ki.wVk), int(entry.ki.wScan), int(entry.ki.dwFlags) & ~KEYEVENTF_KEYUP)
        if entry.ki.dwFlags & KEYEVENTF_KEYUP:
            pressed.pop(identity, None)
        else:
            pressed[identity] = entry
    releases = []
    for entry in reversed(list(pressed.values())):
        release = INPUT.from_buffer_copy(entry)
        release.ki.dwFlags |= KEYEVENTF_KEYUP
        releases.append(release)
    return releases


class BrowserPage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        log_event("browser.console", level="ERROR" if "Error" in level.name else "WARNING" if "Warning" in level.name else "DEBUG",
                  severity=level.name, text_length=len(message), line_number=line_number, source="webengine")


class DrawerBackdrop(QWidget):
    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._opacity = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setObjectName("drawerBackdrop")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.clicked.emit()
        event.accept()

    def get_opacity(self) -> float:
        return self._opacity

    def set_opacity(self, value: float) -> None:
        self._opacity = max(0.0, min(1.0, float(value)))
        alpha = int(92 * self._opacity)
        self.setStyleSheet(f"#drawerBackdrop {{ background-color: rgba(4, 10, 18, {alpha}); }}")

    opacity = Property(float, get_opacity, set_opacity)


class TitleBar(QFrame):
    def _has_interactive_child(self, position: QPoint) -> bool:
        child = self.childAt(position)

        while child is not None:
            if isinstance(child, QAbstractButton):
                return True

            child = child.parentWidget()

        return False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._has_interactive_child(event.position().toPoint()):
            window_handle = self.window().windowHandle()

            if window_handle is not None:
                window_handle.startSystemMove()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._has_interactive_child(event.position().toPoint()):
            window = self.window()

            if isinstance(window, MainWindow):
                window._toggle_maximize_restore()
                event.accept()
                return

        super().mouseDoubleClickEvent(event)


class BrowserBackgroundHost(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnBottomHint
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("background: #111111;")
        self.host_layout = QVBoxLayout(self)
        self.host_layout.setContentsMargins(0, 0, 0, 0)
        self.host_layout.setSpacing(0)

    def prepare_geometry(self, reference_widget: QWidget) -> None:
        screen = QGuiApplication.primaryScreen()
        virtual_geometry = screen.virtualGeometry() if screen is not None else reference_widget.frameGeometry()
        width = max(reference_widget.width(), 1280)
        height = max(reference_widget.height(), 900)
        self.setGeometry(virtual_geometry.right() + 120, virtual_geometry.top() + 120, width, height)


class TranslationOverlay(QWidget):
    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.set_overlay_opacity_percent(int(DEFAULT_SETTINGS["overlayOpacityPercent"]))

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.panel = QFrame(self)
        self.panel.setObjectName("translationOverlayPanel")
        self.panel_layout = QVBoxLayout(self.panel)
        self.panel_layout.setContentsMargins(22, 16, 22, 16)
        self.panel_layout.setSpacing(0)

        self.label = QLabel("")
        # A fordítás külső adat: HTML helyett mindig szó szerinti szöveg jelenjen meg.
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setObjectName("translationOverlayLabel")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.panel_layout.addWidget(self.label)
        layout.addWidget(self.panel)

        self.setStyleSheet(
            """
            #translationOverlayPanel {
                background: rgba(0, 0, 0, 255);
                border-radius: 18px;
            }
            #translationOverlayLabel {
                color: #ffffff;
                font-size: 22px;
                font-weight: 700;
            }
            """
        )

    def show_message(self, text: str, *, duration_ms: int | None = 20000) -> None:
        cleaned_text = str(text or "").strip()

        if not cleaned_text:
            return

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

        if screen is None:
            return

        geometry = screen.availableGeometry()
        max_width = min(max(int(geometry.width() * 0.7), 420), 1100)
        self.label.setText(cleaned_text)
        self.label.setFixedWidth(max_width - 44)
        self.label.adjustSize()
        self.panel.adjustSize()
        self.adjustSize()

        pos_x = geometry.x() + max(0, (geometry.width() - self.width()) // 2)
        pos_y = geometry.y() + max(28, int(geometry.height() * 0.045))
        self.move(pos_x, pos_y)
        self.show()
        self.raise_()

        if sys.platform == "win32":
            hwnd = int(self.winId())

            if hwnd != 0:
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)

        self.hide_timer.stop()

        if duration_ms is not None:
            self.hide_timer.start(max(1000, int(duration_ms)))

    def show_translation(self, text: str, *, duration_ms: int = 20000) -> None:
        self.show_message(text, duration_ms=duration_ms)

    def show_loading(self) -> None:
        self.show_message("Betöltés...", duration_ms=None)

    def hide_overlay(self) -> None:
        self.hide_timer.stop()
        self.hide()

    def set_overlay_opacity_percent(self, percent: int) -> None:
        safe_percent = max(1, min(100, int(percent)))
        self.setWindowOpacity(safe_percent / 100.0)


class QuickChatTextEdit(QPlainTextEdit):
    submit_requested = Signal()
    cancel_requested = Signal()

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if not self.isReadOnly() and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            modifiers = event.modifiers()
            non_keypad_modifiers = modifiers & ~Qt.KeyboardModifier.KeypadModifier

            if non_keypad_modifiers == Qt.KeyboardModifier.ControlModifier:
                cursor = self.textCursor()
                cursor.insertText("\n")
                self.setTextCursor(cursor)
                event.accept()
                return

            if non_keypad_modifiers == Qt.KeyboardModifier.NoModifier:
                self.submit_requested.emit()
                event.accept()
                return

        if not self.isReadOnly() and event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class QuickChatOverlay(QWidget):
    submitted = Signal(str)
    closed = Signal()
    ACTIVATION_GUARD_SECONDS = 0.45

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._busy = False
        self._shown_at_monotonic = 0.0

        self.background_label = QLabel(self)
        self.background_label.setScaledContents(True)
        self.background_label.setObjectName("quickChatBackground")
        self.background_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.background_blur = QGraphicsBlurEffect(self.background_label)
        self.background_blur.setBlurRadius(26)
        self.background_label.setGraphicsEffect(self.background_blur)

        self.backdrop = QFrame(self)
        self.backdrop.setObjectName("quickChatBackdrop")
        self.backdrop.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(36, 36, 36, 36)
        root_layout.setSpacing(0)
        root_layout.addStretch(1)

        self.panel = QFrame(self)
        self.panel.setObjectName("quickChatPanel")
        self.panel.setMaximumWidth(860)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(28, 24, 28, 24)
        panel_layout.setSpacing(14)

        self.title_label = QLabel("Gyors chat")
        self.title_label.setObjectName("quickChatTitle")

        self.hint_label = QLabel("Írd be a fordítandó szöveget. Küldés: Enter, sortörés: Ctrl+Enter, bezárás: Esc")
        self.hint_label.setObjectName("quickChatHint")
        self.hint_label.setWordWrap(True)

        self.text_input = QuickChatTextEdit()
        self.text_input.setObjectName("quickChatInput")
        self.text_input.setPlaceholderText("Ide írd be a szöveget...")
        self.text_input.setMinimumHeight(220)
        self.text_input.submit_requested.connect(self._emit_submit)
        self.text_input.cancel_requested.connect(self.hide_overlay)

        self.status_label = QLabel("")
        self.status_label.setObjectName("quickChatStatus")
        self.status_label.setWordWrap(True)
        self.status_label.hide()

        button_row_widget = QWidget()
        button_row_layout = QHBoxLayout(button_row_widget)
        button_row_layout.setContentsMargins(0, 12, 0, 0)
        button_row_layout.setSpacing(10)
        button_row_layout.addStretch(1)

        self.cancel_button = QPushButton("Bezárás")
        self.cancel_button.clicked.connect(self.hide_overlay)

        self.submit_button = QPushButton("Küldés")
        self.submit_button.setObjectName("quickChatSubmitButton")
        self.submit_button.clicked.connect(self._emit_submit)

        button_row_layout.addWidget(self.cancel_button)
        button_row_layout.addWidget(self.submit_button)

        panel_layout.addWidget(self.title_label)
        panel_layout.addWidget(self.hint_label)
        panel_layout.addWidget(self.text_input, 1)
        panel_layout.addWidget(self.status_label)
        panel_layout.addWidget(button_row_widget)

        root_layout.addWidget(self.panel, 0, Qt.AlignmentFlag.AlignHCenter)
        root_layout.addStretch(1)

        self.setStyleSheet(
            """
            #quickChatBackdrop {
                background: rgba(5, 10, 18, 150);
                border-radius: 0px;
            }
            #quickChatPanel {
                background: rgba(25, 28, 34, 236);
                border: 1px solid #343842;
                border-radius: 24px;
            }
            #quickChatTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f3f4f6;
            }
            #quickChatHint {
                font-size: 13px;
                color: #aab3c2;
            }
            #quickChatInput {
                background: rgba(17, 19, 24, 232);
                color: #f5f5f5;
                border: 1px solid #3d424d;
                border-radius: 16px;
                padding: 14px 16px;
                selection-background-color: #6b7280;
                font-size: 15px;
            }
            #quickChatStatus {
                font-size: 13px;
                color: #d1d5db;
            }
            QPushButton {
                background: #23262b;
                color: #ececec;
                border: 1px solid #343842;
                border-radius: 12px;
                padding: 9px 14px;
                font-weight: 600;
                min-width: 110px;
            }
            QPushButton:hover {
                background: #2c3038;
                border-color: #4a4f5a;
            }
            QPushButton:pressed {
                background: #1f2125;
            }
            #quickChatSubmitButton {
                background: #5e6673;
                border: 1px solid #747d8b;
                color: #ffffff;
            }
            #quickChatSubmitButton:hover {
                background: #6b7482;
                border-color: #848d9b;
            }
            #quickChatSubmitButton:pressed {
                background: #525966;
            }
            """
        )
        self.background_label.lower()
        self.backdrop.lower()
        self.panel.raise_()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        geometry = self.rect()
        self.background_label.setGeometry(geometry)
        self.backdrop.setGeometry(geometry)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._busy:
            event.accept()
            return

        if not self.panel.geometry().contains(event.position().toPoint()):
            self.hide_overlay()
            event.accept()
            return

        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and not self._busy:
            self.hide_overlay()
            event.accept()
            return

        super().keyPressEvent(event)

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == QEvent.Type.WindowDeactivate and self.isVisible() and not self._busy:
            if time.monotonic() - self._shown_at_monotonic >= self.ACTIVATION_GUARD_SECONDS:
                QTimer.singleShot(0, self._hide_if_inactive)

        super().changeEvent(event)

    def show_overlay(self, initial_text: str = "") -> None:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

        if screen is None:
            return

        geometry = screen.geometry()
        background = screen.grabWindow(0, geometry.x(), geometry.y(), geometry.width(), geometry.height())

        if not background.isNull():
            background = background.scaled(
                max(320, geometry.width() // 2),
                max(240, geometry.height() // 2),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

        self.background_label.setPixmap(background)
        self.setGeometry(geometry)
        self.text_input.setPlainText(initial_text)
        self.set_busy(False)
        self._shown_at_monotonic = time.monotonic()
        self.show()
        self.raise_()
        self.activateWindow()

        window_handle = self.windowHandle()

        if window_handle is not None:
            window_handle.requestActivate()

        self._focus_text_input()
        QTimer.singleShot(0, self._focus_text_input)
        QTimer.singleShot(40, self._focus_text_input)

        if sys.platform == "win32":
            QTimer.singleShot(0, self._force_foreground_activation)

    def _force_foreground_activation(self) -> None:
        if sys.platform != "win32":
            self.raise_()
            self.activateWindow()
            return

        hwnd = int(self.winId())

        if hwnd == 0:
            return

        self.raise_()
        self.activateWindow()
        window_handle = self.windowHandle()

        if window_handle is not None:
            window_handle.requestActivate()

        foreground_hwnd = user32.GetForegroundWindow()
        foreground_thread_id = user32.GetWindowThreadProcessId(foreground_hwnd, None) if foreground_hwnd else 0
        current_thread_id = kernel32.GetCurrentThreadId()
        attached = False

        if foreground_thread_id and foreground_thread_id != current_thread_id:
            attached = bool(user32.AttachThreadInput(foreground_thread_id, current_thread_id, True))

        try:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
        finally:
            if attached:
                user32.AttachThreadInput(foreground_thread_id, current_thread_id, False)

    def hide_overlay(self) -> None:
        self.set_busy(False)

        if not self.isVisible():
            return

        self.hide()
        self.closed.emit()

    def is_busy(self) -> bool:
        return self._busy

    def set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = bool(busy)
        self.text_input.setReadOnly(self._busy)
        self.submit_button.setEnabled(not self._busy)
        self.cancel_button.setEnabled(not self._busy)
        self._set_status(message)

    def show_error(self, message: str) -> None:
        self.set_busy(False, message)
        self.text_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _set_status(self, message: str) -> None:
        cleaned_message = str(message or "").strip()

        if not cleaned_message:
            self.status_label.hide()
            self.status_label.setText("")
            return

        self.status_label.setText(cleaned_message)
        self.status_label.show()

    def _focus_text_input(self) -> None:
        self.raise_()
        self.activateWindow()
        self.text_input.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        cursor = self.text_input.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text_input.setTextCursor(cursor)

    def _hide_if_inactive(self) -> None:
        if not self.isVisible() or self._busy:
            return

        if self.isActiveWindow():
            return

        if time.monotonic() - self._shown_at_monotonic < self.ACTIVATION_GUARD_SECONDS:
            return

        self.hide_overlay()

    def _emit_submit(self) -> None:
        if self._busy:
            return

        text = self.text_input.toPlainText().strip()

        if not text:
            self.show_error("Írj be legalább egy sort a gyors chat elküldéséhez.")
            return

        self.set_busy(True, "Fordítás folyamatban...")
        self.submitted.emit(text)


class BrowserOperationCancelled(RuntimeError):
    """A kilépés miatt megszakított böngészőművelet nem oldalhiba."""


class MainWindow(QMainWindow):
    browser_operations_cancelled = Signal()
    def __init__(self, *, store: SettingsStore | None = None, clipboard: Any = None,
                 private_browser: bool = False, open_on_start: bool = True) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(1080, 720)

        self.store = store if store is not None else SettingsStore()
        self.private_browser = private_browser
        self.ocr_service = OCRService(self.store.root_dir / "ocr")
        self.background_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gamer_translator")
        self.current_background_future: Future[Any] | None = None
        self.settings = self.store.load_settings()
        self.last_run_status = self.store.load_last_run_status()
        self.automation_script = resource_path("gamer_translator/automation.js").read_text(encoding="utf-8")

        self.page_loading = False
        self.automation_ready = False
        self.clipboard_translation_in_progress = False
        self.drawer_open = False
        self.drawer_width = 460
        self.last_translated_text = self.store.load_last_translated_text()
        self.latest_translation_request_id = ""
        self.translation_result_request_id = ""
        self.translation_result_complete = bool(self.last_translated_text)
        self.active_translation_request_id = ""
        self.pending_clipboard_payload_queue: list[dict[str, Any]] = []
        self.pending_hotkey_actions: list[tuple[str, int]] = []
        self.registered_hotkeys: dict[str, tuple[int, int]] = {}
        self.hotkey_errors: dict[str, str] = {}
        self.hotkey_pressed_states: dict[str, bool] = {}
        self.suppressed_hotkey_presses: dict[tuple[int, bool], str] = {}
        self.hotkey_generation = 0
        self.hotkey_action_running = False
        self.registered_hotkey_primary_keys: set[int] = set()
        self.keyboard_hook_handle = None
        self.keyboard_hook_callback = None
        self.mouse_hook_handle = None
        self.mouse_hook_callback = None
        self.mouse_recording_buttons: set[tuple[int, bool]] = set()
        self.hotkey_system_integration_enabled = False
        self.operations_cancelled = False
        self.native_window_theme_applied = False
        self.exit_requested = False
        self.window_was_maximized_before_hide = False
        self.tray_message_shown = False
        self.browser_background_mode = False
        self.browser_interaction_active = False
        self.browser_interaction_heartbeat_monotonic = 0.0
        self.clipboard_translation_heartbeat_monotonic = 0.0
        self.frame_pulse_state = False
        self.current_browser_refresh_interval_ms = UI_FRAME_INTERVAL_MS
        self.browser_keepalive_failures = 0
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_toggle_action: QAction | None = None
        self.browser_background_host = BrowserBackgroundHost()
        self.translation_overlay = TranslationOverlay()
        self.quick_chat_overlay = QuickChatOverlay()
        self.quick_chat_overlay.submitted.connect(self._process_quick_chat_translation)

        self.browser_keepalive_timer = QTimer(self)
        self.browser_keepalive_timer.setInterval(45000)
        self.browser_keepalive_timer.timeout.connect(self._perform_browser_keepalive)
        self.browser_keepalive_timer.start()

        self.system_keepawake_timer = QTimer(self)
        self.system_keepawake_timer.setInterval(50000)
        self.system_keepawake_timer.timeout.connect(self._refresh_system_keep_awake)
        self.system_keepawake_timer.start()

        self._build_browser()
        self.browser_refresh_timer = QTimer(self)
        self.browser_refresh_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.browser_refresh_timer.setInterval(self.current_browser_refresh_interval_ms)
        self.browser_refresh_timer.timeout.connect(self._refresh_browser_view)
        self.browser_refresh_timer.start()
        self._build_ui()
        self._apply_styles()
        self._apply_settings_to_form(self.settings)
        self._render_last_run_status(self.last_run_status)
        self._set_live_status("Indulásra kész.")
        self._layout_overlay_widgets()

        self.clipboard = clipboard if clipboard is not None else QGuiApplication.clipboard()
        self.last_seen_image_signature = self._current_clipboard_signature()
        self.pending_clipboard_payload: dict[str, Any] | None = None
        self.screen_clip_hotkey_armed_until = 0.0
        self.clipboard_debounce_timer = QTimer(self)
        self.clipboard_debounce_timer.setSingleShot(True)
        self.clipboard_debounce_timer.setInterval(120)
        self.clipboard_debounce_timer.timeout.connect(self._poll_clipboard)
        self.clipboard.changed.connect(self._handle_clipboard_changed)
        self.response_followup_progress_call_id = ""
        self.response_followup_last_sequence = 0
        self.response_followup_handler: Callable[[dict[str, Any]], None] | None = None
        self.response_followup_started_monotonic = 0.0
        self.response_followup_last_activity_monotonic = 0.0
        self.response_followup_error_count = 0
        self.response_followup_timer = QTimer(self)
        self.response_followup_timer.setInterval(180)
        self.response_followup_timer.timeout.connect(self._poll_response_followup_progress)
        self.interaction_watchdog_timer = QTimer(self)
        self.interaction_watchdog_timer.setInterval(1000)
        self.interaction_watchdog_timer.timeout.connect(self._recover_stuck_interaction_flags)
        self.interaction_watchdog_timer.start()
        self.diagnostics_last_tick = time.monotonic()
        self.diagnostics_timer = QTimer(self)
        self.diagnostics_timer.setInterval(15000)
        self.diagnostics_timer.timeout.connect(self._record_runtime_diagnostics)
        self.diagnostics_timer.start()
        log_event("window.created", monitoring_enabled=self.settings.monitoring_enabled,
                  ocr_enabled=self.settings.ocr_text_from_clipboard_image,
                  game_mode_enabled=self.settings.game_mode_enabled,
                  gpu_enabled=self.settings.webview_gpu_acceleration_enabled,
                  background=self.settings.keep_chatgpt_in_background,
                  has_text=bool(self.last_translated_text))

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1680, 980)
        self._apply_window_icon()
        self._build_tray_icon()
        self._sync_window_buttons()
        app = QApplication.instance()

        if app is not None:
            app.applicationStateChanged.connect(self._handle_application_state_changed)
            app.focusChanged.connect(self._handle_hotkey_focus_changed)

        QTimer.singleShot(0, self._register_hotkeys)
        if open_on_start:
            QTimer.singleShot(0, self.open_chatgpt)
        QTimer.singleShot(0, self._refresh_system_keep_awake)

    def closeEvent(self, event: QCloseEvent) -> None:
        log_event("window.close_requested", cancelled=not self.exit_requested)
        if not self.exit_requested and self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self._hide_to_tray(show_message=True)
            return

        self.hotkey_system_integration_enabled = False
        self.operations_cancelled = True
        self.browser_operations_cancelled.emit()
        if hasattr(self, "diagnostics_timer"):
            self.diagnostics_timer.stop()
        self.store.save_settings(self._read_settings_from_form())
        self._unregister_hotkeys()
        self._uninstall_keyboard_hook()
        self._uninstall_mouse_hook()
        self._restore_system_sleep_state()
        self._shutdown_background_executor()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.browser_background_host.close()
        self.translation_overlay.hide()
        self.quick_chat_overlay.hide()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)

        if not self.native_window_theme_applied:
            self._apply_native_window_theme()
            self.native_window_theme_applied = True

        if self.isVisible() and not self.isMinimized():
            self._deactivate_background_browser_host()

        self._sync_tray_toggle_action()
        QTimer.singleShot(0, self._sync_browser_host_mode)
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        self._sync_tray_toggle_action()
        QTimer.singleShot(0, self._sync_browser_host_mode)
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._layout_overlay_widgets()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_buttons()
            self._sync_tray_toggle_action()

            if self.isMinimized():
                if self.settings.keep_chatgpt_in_background or self.browser_interaction_active:
                    self._activate_background_browser_host()
            elif self.isVisible():
                self._deactivate_background_browser_host()

            QTimer.singleShot(0, self._sync_browser_host_mode)
            QTimer.singleShot(0, self._sync_browser_runtime_state)
        elif event.type() in (QEvent.Type.WindowActivate, QEvent.Type.WindowDeactivate):
            QTimer.singleShot(0, self._sync_browser_host_mode)
            QTimer.singleShot(0, self._sync_browser_runtime_state)

        super().changeEvent(event)

    def _handle_application_state_changed(self, _state) -> None:
        QTimer.singleShot(0, self._sync_browser_host_mode)
        QTimer.singleShot(0, self._sync_browser_runtime_state)
        self._handle_hotkey_focus_changed()

    def _handle_hotkey_focus_changed(self, *_widgets) -> None:
        # A tesztmód nem hívja a natív regisztrálást, ezért puszta mezőfókusz
        # ott sem telepíthet rendszerhookot.
        if self.hotkey_system_integration_enabled:
            if active_hotkey_editor() is not None:
                self._clear_screen_clip_hotkey_arm()
                self.hotkey_generation += 1
            QTimer.singleShot(0, self._update_keyboard_hook_state)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and self.drawer_open:
            self.close_drawer()
            event.accept()
            return

        super().keyPressEvent(event)

    def _build_browser(self) -> None:
        if getattr(self, "private_browser", False):
            self.profile = QWebEngineProfile(self)
        else:
            self.profile = QWebEngineProfile(APP_NAME, self)
            self.profile.setCachePath(str(self.store.browser_dir / "cache"))
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
            self.profile.setHttpCacheMaximumSize(512 * 1024 * 1024)
            self.profile.setPersistentStoragePath(str(self.store.browser_dir / "storage"))
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

        self.page = BrowserPage(self.profile, self)
        self.browser = QWebEngineView(self)
        self.browser.setPage(self.page)
        self.browser.setMinimumWidth(900)
        self.browser_blur_effect: QGraphicsBlurEffect | None = None
        self.browser.loadStarted.connect(self._handle_load_started)
        self.browser.loadFinished.connect(self._handle_load_finished)
        self.page.renderProcessTerminated.connect(lambda status, code: MainWindow._handle_renderer_terminated(self, status, code))

        browser_settings = self.browser.settings()
        self._set_web_attribute(browser_settings, "JavascriptEnabled", True)
        self._set_web_attribute(browser_settings, "LocalStorageEnabled", True)
        # A vágólapot a natív alkalmazás kezeli, a megnyitott weboldalak nem kapnak hozzáférést.
        self._set_web_attribute(browser_settings, "JavascriptCanAccessClipboard", False)
        self._set_web_attribute(browser_settings, "JavascriptCanPaste", False)
        self._set_web_attribute(browser_settings, "LocalContentCanAccessFileUrls", False)
        self._set_web_attribute(browser_settings, "LocalContentCanAccessRemoteUrls", False)
        self._set_web_attribute(browser_settings, "Accelerated2dCanvasEnabled", True)
        self._set_web_attribute(browser_settings, "WebGLEnabled", True)
        self._set_web_attribute(browser_settings, "ScrollAnimatorEnabled", False)
        self._set_web_attribute(browser_settings, "FullScreenSupportEnabled", True)

    def _build_ui(self) -> None:
        self.monitoring_enabled = QCheckBox("A program legyen aktív")
        self.chatgpt_url = QLineEdit()
        self.prompt_template = QPlainTextEdit()
        self.prompt_template.setPlaceholderText("Ide kerül a kézi prompt.")
        self.prompt_template.setMinimumHeight(180)
        self.copy_response_to_clipboard = QCheckBox("A ChatGPT válasza kerüljön a vágólapra")
        self.ocr_text_from_clipboard_image = QCheckBox("Szöveg kiolvasása képről")
        self.webview_gpu_acceleration_enabled = QCheckBox("A ChatGPT nézet használja a GPU gyorsítást")
        self.type_out_hotkey_enabled = QCheckBox("A memóriába mentett fordítás legyen begépelhető gyorsbillentyűvel")
        self.type_out_hotkey = self._build_hotkey_edit()
        self.screen_clip_hotkey_enabled = QCheckBox("A Windows képkivágó nyíljon meg gyorsbillentyűvel")
        self.screen_clip_hotkey_enabled.setToolTip(
            "Csak az itt beállított gyorsbillentyűvel készített kép kerül automatikusan fordításra. "
            "A Win+Shift+S és a többi másolt kép nem indít fordítást."
        )
        self.screen_clip_hotkey = self._build_hotkey_edit()
        self.quick_chat_hotkey_enabled = QCheckBox("A gyors chat overlay nyíljon meg gyorsbillentyűvel")
        self.quick_chat_hotkey = self._build_hotkey_edit()
        self.overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.overlay_opacity_slider.setRange(1, 100)
        self.overlay_opacity_slider.setSingleStep(1)
        self.overlay_opacity_slider.setPageStep(10)
        self.overlay_opacity_slider.valueChanged.connect(self._handle_overlay_opacity_slider_changed)
        self.overlay_opacity_value_label = QLabel("10%")
        self.overlay_opacity_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.overlay_duration_seconds = self._build_spin_box(maximum=120, step=1)
        self.overlay_duration_seconds.setMinimum(1)
        self.overlay_duration_seconds.setSuffix(" mp")
        self.keep_chatgpt_in_background = QCheckBox("A ChatGPT maradjon háttérben, ne kapjon fókuszt")
        self.game_mode_enabled = QCheckBox("Játék mód csökkentse a háttérterhelést")
        self.page_ready_timeout_ms = self._build_spin_box(maximum=120000, step=1000)
        self.page_ready_timeout_ms.setMinimum(1000)

        overlay_opacity_row = QWidget()
        overlay_opacity_layout = QHBoxLayout(overlay_opacity_row)
        overlay_opacity_layout.setContentsMargins(0, 0, 0, 0)
        overlay_opacity_layout.setSpacing(10)
        overlay_opacity_layout.addWidget(self.overlay_opacity_slider, 1)
        overlay_opacity_layout.addWidget(self.overlay_opacity_value_label)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.addRow("", self.monitoring_enabled)
        form_layout.addRow("Kézi prompt", self.prompt_template)
        form_layout.addRow("", self.copy_response_to_clipboard)
        form_layout.addRow("", self.ocr_text_from_clipboard_image)
        form_layout.addRow("", self.webview_gpu_acceleration_enabled)
        form_layout.addRow("", self.screen_clip_hotkey_enabled)
        form_layout.addRow("Képkivágási gyorsbillentyű", self.screen_clip_hotkey)
        form_layout.addRow("", self.type_out_hotkey_enabled)
        form_layout.addRow("Begépelési gyorsbillentyű", self.type_out_hotkey)
        form_layout.addRow("", self.quick_chat_hotkey_enabled)
        form_layout.addRow("Gyors chat gyorsbillentyű", self.quick_chat_hotkey)
        form_layout.addRow("", self.keep_chatgpt_in_background)
        form_layout.addRow("", self.game_mode_enabled)
        form_layout.addRow("Overlay láthatósága", overlay_opacity_row)
        form_layout.addRow("Overlay megjelenési ideje (másodperc)", self.overlay_duration_seconds)

        settings_group = QGroupBox("Beállítások")
        settings_group.setLayout(form_layout)

        self.status_label = QLabel("Indulásra kész.")
        self.status_label.setWordWrap(True)
        self.last_run_label = QLabel("Még nincs futási állapot.")
        self.last_run_label.setWordWrap(True)
        self.current_url_label = QLabel("")
        self.current_url_label.setWordWrap(True)
        self.current_url_label.setTextFormat(Qt.TextFormat.PlainText)
        self.current_url_label.setContentsMargins(18, 4, 18, 4)
        self.top_status_label = QLabel("Indulásra kész.")
        self.top_status_label.setObjectName("topStatusLabel")
        self.top_status_label.setWordWrap(False)
        for label in (self.status_label, self.last_run_label, self.top_status_label):
            label.setTextFormat(Qt.TextFormat.PlainText)

        self.menu_button = QPushButton("Beállítások")
        self.menu_button.clicked.connect(self.toggle_drawer)

        self.open_chatgpt_button = QPushButton("ChatGPT")
        self.send_prompt_now_button = QPushButton("Prompt elküldése")
        self.save_settings_button = QPushButton("Beállítások mentése")
        self.reset_defaults_button = QPushButton("Alapértékek visszaállítása")
        self.close_drawer_button = QPushButton("Bezárás")

        self.open_chatgpt_button.clicked.connect(self._handle_open_chatgpt_button_clicked)
        self.send_prompt_now_button.clicked.connect(self.send_prompt_now)
        self.save_settings_button.clicked.connect(self.save_settings)
        self.reset_defaults_button.clicked.connect(self.reset_defaults)
        self.close_drawer_button.clicked.connect(self.close_drawer)

        status_group = QGroupBox("Állapot")
        status_layout = QVBoxLayout()
        status_layout.addWidget(QLabel("Utolsó állapot:"))
        status_layout.addWidget(self.last_run_label)
        status_layout.addWidget(QLabel("Futási információ:"))
        status_layout.addWidget(self.status_label)
        self.open_logs_button = QPushButton("Naplómappa megnyitása")
        self.open_logs_button.clicked.connect(self._open_log_directory)
        status_layout.addWidget(self.open_logs_button)
        log_hint = QLabel("Részletes helyi eseménynaplózás aktív. A szövegek és képek tartalma nem kerül a naplóba.")
        log_hint.setWordWrap(True)
        status_layout.addWidget(log_hint)
        status_group.setLayout(status_layout)

        drawer_buttons = QHBoxLayout()
        drawer_buttons.addWidget(self.save_settings_button)
        drawer_buttons.addWidget(self.reset_defaults_button)

        drawer_content = QWidget()
        drawer_content.setObjectName("drawerContent")
        drawer_content_layout = QVBoxLayout(drawer_content)
        drawer_content_layout.setContentsMargins(0, 0, 0, 0)
        drawer_content_layout.setSpacing(16)
        drawer_content_layout.addWidget(settings_group)
        drawer_content_layout.addLayout(drawer_buttons)
        drawer_content_layout.addWidget(status_group)
        drawer_content_layout.addStretch(1)

        self.window_title_label = QLabel(APP_NAME)
        self.window_title_label.setObjectName("windowTitleLabel")
        self.window_icon_label = QLabel("")
        self.window_icon_label.setObjectName("windowIconLabel")
        self._load_title_icon()

        self.menu_button.setObjectName("headerButton")
        self.open_chatgpt_button.setObjectName("headerButton")
        self.send_prompt_now_button.setObjectName("accentHeaderButton")
        self.top_status_label.setFixedHeight(44)

        root_surface = QWidget()
        root_surface.setObjectName("rootSurface")
        root_layout = QVBoxLayout(root_surface)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.setCentralWidget(root_surface)

        self.top_bar = TitleBar(root_surface)
        self.top_bar.setObjectName("topBar")
        self.top_bar.setFixedHeight(72)
        top_bar_layout = QHBoxLayout(self.top_bar)
        top_bar_layout.setContentsMargins(18, 14, 18, 14)
        top_bar_layout.setSpacing(10)
        top_bar_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        top_bar_layout.addWidget(self.top_status_label, 1)
        top_bar_layout.addWidget(self.open_chatgpt_button)
        top_bar_layout.addWidget(self.menu_button)
        top_bar_layout.addWidget(self.send_prompt_now_button)
        root_layout.addWidget(self.top_bar)
        # A böngésző eredete mindig látható; a bejelentkezési tokeneket nem jelenítjük meg.
        root_layout.addWidget(self.current_url_label)
        self.browser.urlChanged.connect(self._update_browser_origin_label)

        self.content_surface = QFrame()
        self.content_surface.setObjectName("contentSurface")
        self.content_layout = QVBoxLayout(self.content_surface)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self.content_layout.addWidget(self.browser)
        root_layout.addWidget(self.content_surface, 1)

        self.browser_status_placeholder = QFrame(self.content_surface)
        self.browser_status_placeholder.setObjectName("browserStatusPlaceholder")
        self.browser_status_placeholder.hide()
        placeholder_layout = QVBoxLayout(self.browser_status_placeholder)
        placeholder_layout.setContentsMargins(48, 42, 48, 42)
        placeholder_layout.setSpacing(14)
        placeholder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_status_title = QLabel("A ChatGPT nézet pihentetve van")
        self.browser_status_title.setObjectName("browserStatusTitle")
        self.browser_status_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_status_body = QLabel("")
        self.browser_status_body.setObjectName("browserStatusBody")
        self.browser_status_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_status_body.setWordWrap(True)
        self.browser_status_hint = QLabel("")
        self.browser_status_hint.setObjectName("browserStatusHint")
        self.browser_status_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.browser_status_hint.setWordWrap(True)
        placeholder_layout.addStretch(1)
        placeholder_layout.addWidget(self.browser_status_title)
        placeholder_layout.addWidget(self.browser_status_body)
        placeholder_layout.addWidget(self.browser_status_hint)
        placeholder_layout.addStretch(1)

        self.frame_pulse_dot = QFrame(self.content_surface)
        self.frame_pulse_dot.setObjectName("framePulseDot")
        self.frame_pulse_dot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.frame_pulse_dot.setStyleSheet("background: rgba(16, 18, 22, 1);")
        self.frame_pulse_dot.setGeometry(0, 0, 1, 1)
        self.frame_pulse_dot.show()

        self.drawer_backdrop = DrawerBackdrop(self.content_surface)
        self.drawer_backdrop.clicked.connect(self.close_drawer)
        self.drawer_backdrop.hide()
        self.drawer_backdrop.set_opacity(0.0)

        self.drawer_panel = QFrame(self.content_surface)
        self.drawer_panel.setObjectName("drawerPanel")
        self.drawer_panel.hide()

        top_bar_shadow = QGraphicsDropShadowEffect(self.top_bar)
        top_bar_shadow.setBlurRadius(20)
        top_bar_shadow.setColor(Qt.GlobalColor.black)
        top_bar_shadow.setOffset(0, 5)
        self.top_bar.setGraphicsEffect(top_bar_shadow)

        drawer_layout = QVBoxLayout(self.drawer_panel)
        drawer_layout.setContentsMargins(18, 18, 18, 18)
        drawer_layout.setSpacing(14)

        drawer_header = QHBoxLayout()
        drawer_title = QLabel("Beállítások")
        drawer_title.setObjectName("drawerTitle")
        drawer_header.addWidget(drawer_title)
        drawer_header.addStretch(1)
        drawer_header.addWidget(self.close_drawer_button)

        self.drawer_scroll = QScrollArea()
        self.drawer_scroll.setWidgetResizable(True)
        self.drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.drawer_scroll.setWidget(drawer_content)
        self.drawer_scroll.viewport().setObjectName("drawerScrollViewport")

        drawer_layout.addLayout(drawer_header)
        drawer_layout.addWidget(self.drawer_scroll, 1)

        self.drawer_animation = QPropertyAnimation(self.drawer_panel, b"pos", self)
        self.drawer_animation.setDuration(280)
        self.drawer_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.drawer_animation.finished.connect(self._on_drawer_animation_finished)

        self.backdrop_animation = QPropertyAnimation(self.drawer_backdrop, b"opacity", self)
        self.backdrop_animation.setDuration(220)
        self.backdrop_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.backdrop_animation.finished.connect(self._on_backdrop_animation_finished)

    def _apply_styles(self) -> None:
        self.centralWidget().setStyleSheet(
            """
            #rootSurface {
                background: #181818;
            }
            QWidget {
                color: #ececec;
                font-size: 13px;
            }
            #topBar {
                background: #181818;
                border-bottom: 1px solid #2b2d31;
            }
            #contentSurface {
                background: #171717;
            }
            #browserStatusPlaceholder {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #15181d, stop:1 #101216);
                border: 1px solid #2b2d31;
                border-radius: 18px;
            }
            #browserStatusTitle {
                font-size: 22px;
                font-weight: 700;
                color: #f3f4f6;
            }
            #browserStatusBody {
                font-size: 15px;
                color: #e5e7eb;
            }
            #browserStatusHint {
                font-size: 13px;
                color: #9ca3af;
            }
            #drawerPanel {
                background: transparent;
                border: none;
            }
            #drawerContent, #drawerScrollViewport {
                background: transparent;
            }
            #drawerTitle {
                font-size: 18px;
                font-weight: 700;
                color: #f3f4f6;
            }
            #windowTitleLabel {
                font-size: 14px;
                font-weight: 700;
                color: #f7f7f8;
            }
            #windowIconLabel {
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
            }
            #topStatusLabel {
                background: #202227;
                border: 1px solid #343842;
                border-radius: 12px;
                padding: 9px 14px;
                color: #d1d5db;
            }
            QGroupBox {
                font-size: 14px;
                font-weight: 700;
                border: 1px solid #343842;
                border-radius: 16px;
                margin-top: 14px;
                padding: 18px 14px 14px 14px;
                background: #1f2125;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #d1d5db;
            }
            QPushButton {
                background: #23262b;
                color: #ececec;
                border: 1px solid #343842;
                border-radius: 12px;
                padding: 9px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2c3038;
                border-color: #4a4f5a;
            }
            QPushButton:pressed {
                background: #1f2125;
            }
            #headerButton {
                min-height: 44px;
                max-height: 44px;
                background: #23262b;
                border-color: #343842;
                padding-top: 0;
                padding-bottom: 0;
                padding-left: 13px;
                padding-right: 13px;
            }
            #accentHeaderButton {
                min-height: 44px;
                max-height: 44px;
                background: #5e6673;
                border: 1px solid #747d8b;
                color: #ffffff;
                padding-top: 0;
                padding-bottom: 0;
                padding-left: 13px;
                padding-right: 13px;
            }
            #accentHeaderButton:hover {
                background: #6b7482;
                border-color: #848d9b;
            }
            #accentHeaderButton:pressed {
                background: #525966;
            }
            QLineEdit, QPlainTextEdit, QSpinBox {
                background: #17191d;
                color: #f1f1f1;
                border: 1px solid #343842;
                border-radius: 12px;
                padding: 8px 10px;
                selection-background-color: #6b7280;
            }
            QPlainTextEdit {
                padding-top: 10px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 18px;
                border: none;
                background: transparent;
            }
            QCheckBox {
                spacing: 9px;
                color: #ececec;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 6px;
                border: 1px solid #4b4f57;
                background: #17191d;
            }
            QCheckBox::indicator:checked {
                background: #6b7280;
                border-color: #6b7280;
            }
            QLabel {
                color: #ececec;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            """
        )

    def _load_title_icon(self) -> None:
        icon_path = resource_path("gamer_translator/assets/icon-128.png")

        if not icon_path.exists():
            return

        pixmap = QPixmap(str(icon_path))

        if pixmap.isNull():
            return

        self.window_icon_label.setPixmap(
            pixmap.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        )

    def _build_window_button(self, text: str, object_name: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.clicked.connect(callback)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    def _toggle_maximize_restore(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

        self._sync_window_buttons()

    def _sync_window_buttons(self) -> None:
        if not hasattr(self, "maximize_button"):
            return

        self.maximize_button.setText("❐" if self.isMaximized() else "□")

    def _build_spin_box(self, *, maximum: int = 60000, step: int = 100) -> QSpinBox:
        spin_box = QSpinBox()
        spin_box.setMinimum(0)
        spin_box.setMaximum(maximum)
        spin_box.setSingleStep(step)
        spin_box.setAccelerated(True)
        return spin_box

    def _build_hotkey_edit(self) -> HotkeyEdit:
        return HotkeyEdit()

    def _set_hotkey_value(self, hotkey_edit: HotkeyEdit, value: str) -> None:
        hotkey_edit.set_hotkey_value(value)

    def _read_hotkey_value(self, hotkey_edit: HotkeyEdit, fallback: str) -> str:
        return hotkey_edit.hotkey_value() or fallback

    def _handle_overlay_opacity_slider_changed(self, value: int) -> None:
        safe_value = max(1, min(100, int(value)))
        self.overlay_opacity_value_label.setText(f"{safe_value}%")
        self.translation_overlay.set_overlay_opacity_percent(safe_value)

    def _apply_window_icon(self) -> None:
        icon_path = resource_path("gamer_translator/assets/icon-128.png")

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _move_browser_to_widget(self, target_widget: QWidget, target_layout: QVBoxLayout) -> None:
        current_parent = self.browser.parentWidget()

        if current_parent is not None and current_parent.layout() is not None:
            current_parent.layout().removeWidget(self.browser)

        self.browser.setParent(target_widget)
        target_layout.addWidget(self.browser)
        self.browser.show()

    def _activate_background_browser_host(self) -> None:
        if self.browser_background_mode:
            self.browser_background_host.prepare_geometry(self)
            if not self.browser_background_host.isVisible():
                self.browser_background_host.show()
            self._sync_browser_runtime_state()
            return

        self.browser_background_host.prepare_geometry(self)
        self._move_browser_to_widget(self.browser_background_host, self.browser_background_host.host_layout)
        self.browser_background_host.show()
        self.browser_background_mode = True
        self._sync_browser_runtime_state()

    def _deactivate_background_browser_host(self) -> None:
        if not self.browser_background_mode:
            return

        self._move_browser_to_widget(self.content_surface, self.content_layout)
        self.browser_background_host.hide()
        self.browser_background_mode = False
        self._layout_overlay_widgets()
        self._sync_browser_runtime_state()

    def _should_use_background_browser_host(self) -> bool:
        interaction_active = (self.browser_interaction_active or self.page_loading or self.clipboard_translation_in_progress
                              or bool(getattr(self, "response_followup_progress_call_id", "")))

        return self._is_window_hidden_for_tray() and (self.settings.keep_chatgpt_in_background or interaction_active)

    def _sync_browser_host_mode(self) -> None:
        if not hasattr(self, "browser"):
            return

        should_use_background_host = self._should_use_background_browser_host()

        if should_use_background_host and not self.browser_background_mode:
            self._activate_background_browser_host()
            return

        if not should_use_background_host and self.browser_background_mode:
            self._deactivate_background_browser_host()

    def _sync_browser_runtime_state(self) -> None:
        if not hasattr(self, "browser"):
            return

        page = self.browser.page()
        window_visible = self.isVisible() and not self.isMinimized()
        visible_main_window_render = window_visible and not self.browser_background_mode
        background_interaction_active = self.browser_background_mode and (
            self.browser_interaction_active or self.page_loading or self.clipboard_translation_in_progress
            or bool(getattr(self, "response_followup_progress_call_id", ""))
        )
        background_keepalive_active = (
            self.browser_background_mode
            and self._is_window_hidden_for_tray()
            and self.settings.keep_chatgpt_in_background
            and self.settings.monitoring_enabled
        )
        should_render_page = visible_main_window_render or background_interaction_active or background_keepalive_active
        if should_render_page != getattr(self, "diagnostic_last_render_state", None):
            self.diagnostic_last_render_state = should_render_page
            log_event("browser.lifecycle_changed", active=should_render_page, background=self.browser_background_mode)
        frozen_state = getattr(QWebEnginePage.LifecycleState, "Frozen", QWebEnginePage.LifecycleState.Active)

        try:
            page.setLifecycleState(
                QWebEnginePage.LifecycleState.Active if should_render_page else frozen_state
            )
            page.setVisible(should_render_page)
            self.browser.setUpdatesEnabled(should_render_page)

            if self.browser_background_mode and self._is_window_hidden_for_tray():
                if should_render_page:
                    self.browser_background_host.show()
                    self.browser.show()
                else:
                    self.browser_background_host.hide()
                    self.browser.hide()
            elif should_render_page:
                self.browser.show()
            else:
                self.browser.hide()
        except RuntimeError:
            return
        finally:
            self._sync_browser_placeholder()
            self._update_browser_refresh_timer()

    def _should_keep_system_awake(self) -> bool:
        return self.settings.monitoring_enabled

    def _refresh_system_keep_awake(self) -> None:
        if sys.platform != "win32":
            return

        execution_state = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if self._should_keep_system_awake() else ES_CONTINUOUS

        try:
            kernel32.SetThreadExecutionState(execution_state)
        except Exception:  # noqa: BLE001
            return

    def _restore_system_sleep_state(self) -> None:
        if sys.platform != "win32":
            return

        try:
            kernel32.SetThreadExecutionState(ES_CONTINUOUS)
        except Exception:  # noqa: BLE001
            return

    def _should_run_browser_keepalive(self) -> bool:
        if not hasattr(self, "browser"):
            return False

        if self.page_loading or self.browser_interaction_active or self.clipboard_translation_in_progress:
            return False

        if getattr(self, "response_followup_progress_call_id", ""):
            return False

        if not self.settings.monitoring_enabled or not self.settings.keep_chatgpt_in_background:
            return False

        if self.settings.game_mode_enabled:
            return False

        if not (self.browser_background_mode or self._is_window_hidden_for_tray()):
            return False

        return self._is_chatgpt_url(self.browser.url().toString().strip())

    def _perform_browser_keepalive(self) -> None:
        if not self._should_run_browser_keepalive():
            self.browser_keepalive_failures = 0
            return

        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()

        try:
            keepalive_result = self._run_javascript(
                """
                    (() => ({
                      readyState: document.readyState,
                      visibilityState: document.visibilityState,
                      hasAutomation: typeof window.__gamerTranslatorDeliver === "function"
                        && window.__gamerTranslatorDeliverVersion === "%s",
                      keepAliveAt: Date.now()
                    }))()
                """ % AUTOMATION_SCRIPT_VERSION,
                timeout_ms=4000,
            )
        except RuntimeError as error:
            self.browser_keepalive_failures += 1
            log_exception("browser.keepalive_failed", error, count=self.browser_keepalive_failures)

            if self.browser_keepalive_failures >= 2 and not self.page_loading:
                self.browser_keepalive_failures = 0
                self.automation_ready = False
                self._set_live_status("A ChatGPT oldal felébresztése miatt újratöltés történt.")
                self.browser.reload()
                log_event("browser.keepalive_reloaded", reason="consecutive_failures")

            return

        self.browser_keepalive_failures = 0

        if isinstance(keepalive_result, dict) and keepalive_result.get("hasAutomation") is True:
            return

        self.automation_ready = False

        try:
            self._ensure_automation_ready()
        except RuntimeError:
            return

    def _build_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        app = QApplication.instance()

        if app is not None:
            app.setQuitOnLastWindowClosed(False)

        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip(APP_NAME)

        tray_menu = QMenu(self)
        self.tray_toggle_action = QAction("Eltüntetés", self)
        self.tray_toggle_action.triggered.connect(self._toggle_tray_window_visibility)

        quit_action = QAction("Kilépés", self)
        quit_action.triggered.connect(self._quit_from_tray)

        tray_menu.addAction(self.tray_toggle_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._handle_tray_icon_activated)
        self.tray_icon.show()
        self._sync_tray_toggle_action()

    def _handle_tray_icon_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_tray_window_visibility()

    def _toggle_tray_window_visibility(self) -> None:
        if self._is_window_hidden_for_tray():
            self._show_from_tray()
            return

        self._hide_to_tray(show_message=False)

    def _is_window_hidden_for_tray(self) -> bool:
        return not self.isVisible() or self.isMinimized()

    def _sync_tray_toggle_action(self) -> None:
        if self.tray_toggle_action is None:
            return

        self.tray_toggle_action.setText("Megjelenítés" if self._is_window_hidden_for_tray() else "Eltüntetés")

    def _hide_to_tray(self, *, show_message: bool) -> None:
        self.window_was_maximized_before_hide = bool(self.windowState() & Qt.WindowState.WindowMaximized)
        self._sync_browser_host_mode()
        self.hide()
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()
        self._sync_tray_toggle_action()

        if show_message and self.tray_icon is not None and not self.tray_message_shown:
            self.tray_icon.showMessage(
                APP_NAME,
                "Az alkalmazás a tálcán fut tovább. Dupla kattintással visszahozhatod.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
            self.tray_message_shown = True

    def _show_from_tray(self) -> None:
        if self.window_was_maximized_before_hide:
            self.showMaximized()
        else:
            self.showNormal()

        self._sync_browser_host_mode()
        self.raise_()
        self.activateWindow()
        self._sync_window_buttons()
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()
        self._sync_tray_toggle_action()

    def show_from_external_request(self) -> None:
        self._show_from_tray()

    def _quit_from_tray(self) -> None:
        self.exit_requested = True
        app = QApplication.instance()

        if app is not None:
            app.quit()
            return

        self.close()

    def _restart_application(self) -> None:
        restart_command = self._build_restart_command()

        try:
            if sys.platform == "win32":
                self._schedule_windows_restart(restart_command)
            else:
                subprocess.Popen(restart_command, start_new_session=True, close_fds=True)
        except Exception as error:  # noqa: BLE001
            self._set_live_status(f"Az újraindítás nem sikerült: {error}")
            QMessageBox.warning(self, APP_NAME, f"Az újraindítás nem sikerült:\n{error}")
            return

        self.exit_requested = True
        app = QApplication.instance()

        if app is not None:
            app.quit()
            return

        self.close()

    def _build_restart_command(self) -> list[str]:
        if getattr(sys, "frozen", False):
            restart_target = self._resolve_restart_executable_path()
            return [str(restart_target), *sys.argv[1:]]

        if sys.argv:
            return [sys.executable, *sys.argv]

        project_root_main = Path(__file__).resolve().parents[1] / "main.py"
        return [sys.executable, str(project_root_main)]

    def _resolve_restart_executable_path(self) -> Path:
        candidate_paths: list[Path] = []

        if sys.argv and sys.argv[0]:
            candidate_paths.append(Path(sys.argv[0]))

        candidate_paths.append(Path(sys.executable))

        for candidate_path in candidate_paths:
            try:
                resolved_path = candidate_path.resolve()
            except OSError:
                resolved_path = candidate_path

            if "_MEI" in str(resolved_path):
                continue

            if resolved_path.exists():
                return resolved_path

        if sys.argv and sys.argv[0]:
            return Path(sys.argv[0]).resolve()

        return Path(sys.executable).resolve()

    def _schedule_windows_restart(self, restart_command: list[str]) -> None:
        executable = restart_command[0]
        arguments = restart_command[1:]

        if getattr(sys, "frozen", False):
            working_directory = str(Path(executable).resolve().parent)
        else:
            working_directory = str(Path(__file__).resolve().parents[1])

        script_path = Path(tempfile.gettempdir()) / f"gamer_translator_restart_{os.getpid()}_{uuid.uuid4().hex}.ps1"
        script_lines = [
            f"$ParentPid = {os.getpid()}",
            "while (Get-Process -Id $ParentPid -ErrorAction SilentlyContinue) {",
            "    Start-Sleep -Milliseconds 250",
            "}",
            "Start-Sleep -Milliseconds 700",
            "$env:PYINSTALLER_RESET_ENVIRONMENT = '1'",
            "Remove-Item Env:_PYI_APPLICATION_HOME_DIR -ErrorAction SilentlyContinue",
            "Remove-Item Env:_PYI_ARCHIVE_FILE -ErrorAction SilentlyContinue",
            "Remove-Item Env:_PYI_PARENT_PROCESS_LEVEL -ErrorAction SilentlyContinue",
            "Remove-Item Env:_PYI_SPLASH_IPC -ErrorAction SilentlyContinue",
            "Remove-Item Env:_MEIPASS2 -ErrorAction SilentlyContinue",
            "$StartProcessArgs = @{",
            f"    FilePath = {self._powershell_literal(executable)}",
            f"    WorkingDirectory = {self._powershell_literal(working_directory)}",
            "}",
        ]

        if arguments:
            # A Start-Process összefűzi a tömböt; a szóközös útvonalakat előre idézni kell.
            rendered_arguments = self._powershell_literal(subprocess.list2cmdline(arguments))
            script_lines.append(f"$StartProcessArgs.ArgumentList = {rendered_arguments}")

        script_lines.extend(
            [
                "Start-Process @StartProcessArgs",
                "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue",
            ]
        )
        script_path.write_text("\n".join(script_lines), encoding="utf-8-sig")

        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        powershell_executable = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
        powershell_command = str(powershell_executable) if powershell_executable.exists() else "powershell.exe"
        subprocess.Popen(
            [
                powershell_command,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                str(script_path),
            ],
            creationflags=creationflags,
            close_fds=True,
        )

    def _powershell_literal(self, value: str) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    def _apply_native_window_theme(self) -> None:
        if sys.platform != "win32":
            return

        hwnd = int(self.winId())

        if hwnd == 0:
            return

        dark_mode_enabled = ctypes.c_int(1)
        rounded_corners = ctypes.c_int(DWMWCP_ROUND)

        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark_mode_enabled),
            ctypes.sizeof(dark_mode_enabled),
        )
        dwmapi.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(rounded_corners),
            ctypes.sizeof(rounded_corners),
        )

    def _handle_load_started(self) -> None:
        if self.operations_cancelled:
            return
        self.browser_load_started_at = time.monotonic()
        log_event("browser.load_started", request_id=getattr(self, "active_translation_request_id", None))
        self.page_loading = True
        self.automation_ready = False
        self._update_browser_origin_label(self.browser.url())
        self._set_live_status("A ChatGPT oldal betöltése folyamatban.")
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def _handle_load_finished(self, ok: bool) -> None:
        log_event("browser.load_finished", success=ok,
                  duration_ms=round((time.monotonic() - getattr(self, "browser_load_started_at", time.monotonic())) * 1000))
        self.page_loading = False
        if self.operations_cancelled:
            return
        self._update_browser_origin_label(self.browser.url())

        if not ok:
            self._set_live_status("A böngészőoldal nem töltődött be rendesen.")
            QTimer.singleShot(0, self._sync_browser_runtime_state)
            return

        try:
            self._ensure_automation_ready()
            self._set_live_status("A ChatGPT oldal betöltve.")
        except BrowserOperationCancelled:
            log_event("browser.automation_cancelled", cancelled=True)
        except RuntimeError as error:
            log_exception("browser.automation_failed", error)
            self._set_live_status(str(error))
        finally:
            QTimer.singleShot(0, self._sync_browser_runtime_state)

    def _update_browser_origin_label(self, url: QUrl) -> None:
        origin_url = QUrl()
        origin_url.setScheme(url.scheme())
        origin_url.setHost(url.host())
        origin_url.setPort(url.port())
        origin = origin_url.toString(QUrl.ComponentFormattingOption.FullyEncoded)
        prefix = "ChatGPT" if self._is_chatgpt_url(url.toString()) else "Külső oldal – automatizálás kikapcsolva"
        self.current_url_label.setText(f"{prefix}: {origin}")

    def save_settings(self) -> None:
        previous_settings = self.settings
        self.settings = self._read_settings_from_form()
        self.store.save_settings(self.settings)
        log_event("settings.saved", monitoring_enabled=self.settings.monitoring_enabled,
                  ocr_enabled=self.settings.ocr_text_from_clipboard_image,
                  game_mode_enabled=self.settings.game_mode_enabled,
                  gpu_enabled=self.settings.webview_gpu_acceleration_enabled,
                  background=self.settings.keep_chatgpt_in_background)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        self._register_hotkeys()
        self._refresh_system_keep_awake()
        self._sync_browser_host_mode()
        self._update_browser_refresh_timer(force=True)
        QTimer.singleShot(0, self._sync_browser_runtime_state)
        if previous_settings.webview_gpu_acceleration_enabled != self.settings.webview_gpu_acceleration_enabled:
            self._set_live_status(self._hotkey_status_message("Beállítások elmentve. A program újraindul."))
            self._restart_application()
            return

        self._set_live_status(self._hotkey_status_message("Beállítások elmentve."))

    def reset_defaults(self) -> None:
        log_event("settings.defaults_restored")
        previous_settings = self.settings
        self.settings = AppSettings.from_dict(DEFAULT_SETTINGS)
        self._apply_settings_to_form(self.settings)
        self.store.save_settings(self.settings)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        self._register_hotkeys()
        self._refresh_system_keep_awake()
        self._sync_browser_host_mode()
        self._update_browser_refresh_timer(force=True)
        QTimer.singleShot(0, self._sync_browser_runtime_state)
        if previous_settings.webview_gpu_acceleration_enabled != self.settings.webview_gpu_acceleration_enabled:
            self._set_live_status(self._hotkey_status_message("Az alapértékek vissza lettek állítva. A program újraindul."))
            self._restart_application()
            return

        self._set_live_status(self._hotkey_status_message("Az alapértékek vissza lettek állítva."))

    def toggle_drawer(self) -> None:
        self._set_drawer_open(not self.drawer_open)

    def close_drawer(self) -> None:
        self._set_drawer_open(False)

    def _handle_open_chatgpt_button_clicked(self) -> None:
        self.open_chatgpt(show_error_dialog=True)

    def open_chatgpt(self, *, show_error_dialog: bool = False) -> None:
        if self.browser_interaction_active or self.clipboard_translation_in_progress:
            self._set_live_status("Már fut egy másik ChatGPT művelet, várd meg amíg befejeződik.")
            return
        self.settings = self._read_settings_from_form()
        self._begin_browser_interaction()

        try:
            self._ensure_chatgpt_page_loaded(reload_if_open=True)
            self._ensure_automation_ready()
        except BrowserOperationCancelled:
            log_event("browser.open_cancelled", cancelled=True)
        except Exception as error:  # noqa: BLE001
            message = str(error)
            log_exception("browser.open_failed", error)
            self._save_last_run_status(message)
            self._set_live_status(message)

            if show_error_dialog:
                QMessageBox.warning(self, APP_NAME, message)
        finally:
            self._end_browser_interaction()

    def send_prompt_now(self) -> None:
        log_event("prompt.requested", busy=self.browser_interaction_active or self.clipboard_translation_in_progress)
        if self.browser_interaction_active or self.clipboard_translation_in_progress:
            self._set_live_status("Már fut egy másik ChatGPT művelet, várd meg amíg befejeződik.")
            return
        self.settings = self._read_settings_from_form()
        self._set_live_status("Prompt küldése folyamatban.")
        self._begin_browser_interaction()

        try:
            self._ensure_chatgpt_page_loaded(reload_if_open=False)
            self._ensure_automation_ready()
            self._execute_delivery(
                {
                    "prompt": self.settings.prompt_template.strip(),
                    "imageDataUrl": "",
                    "imageMimeType": "",
                    "imageFilename": "",
                    "autoSubmit": True,
                    "copyResponseToClipboard": False,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": DEFAULT_RESPONSE_TIMEOUT_MS,
                }
            )
            self._save_last_run_status("A kézi prompt elküldve a ChatGPT-nek.")
            self._set_live_status("A prompt elküldve.")
        except BrowserOperationCancelled:
            log_event("prompt.cancelled", cancelled=True)
        except Exception as error:  # noqa: BLE001
            log_exception("prompt.failed", error)
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
            QMessageBox.warning(self, APP_NAME, str(error))
        finally:
            self._end_browser_interaction()

    def _ensure_chatgpt_page_loaded(self, *, reload_if_open: bool) -> None:
        if getattr(self, "operations_cancelled", False):
            raise BrowserOperationCancelled()
        current_url = self.browser.url().toString().strip()
        target_url = CHATGPT_URL

        if not self._is_chatgpt_url(current_url):
            # A loadStarted csak a következő Qt eseménykörben érkezhet meg.
            # A várakozásnak már a navigáció elindításakor aktívnak kell lennie.
            self.page_loading = True
            self.browser.load(QUrl(target_url))
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)
        elif self.page_loading:
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)
        elif reload_if_open:
            self._set_live_status("A ChatGPT oldal újratöltése folyamatban.")
            self.page_loading = True
            self.browser.reload()
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)

    def _poll_clipboard(self) -> None:
        if self.clipboard_translation_in_progress:
            return

        if self.browser_interaction_active:
            # Az eseményhurok újra beléphet ide egy folyamatban lévő küldés közben.
            self.clipboard_debounce_timer.start()
            return

        # Csak a saját gyorsgombhoz tartozó eseménynél rögzített képet küldjük.
        # A vágólap a késleltetés alatt már tartalmazhat egy másik, privát képet.
        payload = self.pending_clipboard_payload
        self.pending_clipboard_payload = None

        queue = getattr(self, "pending_clipboard_payload_queue", [])
        if queue:
            self.pending_clipboard_payload = queue.pop(0)

        if payload is None:
            return

        log_event("capture.dequeued", request_id=payload.get("requestId"), pending_count=len(queue))

        self.last_seen_image_signature = str(payload["imageSignature"])
        self._process_clipboard_translation(payload)

    def _handle_clipboard_changed(self, mode) -> None:  # type: ignore[override]
        if mode != self.clipboard.Mode.Clipboard:
            return

        if not self._is_screen_clip_hotkey_armed():
            return

        settings = self._read_settings_from_form()
        if not settings.monitoring_enabled or not settings.screen_clip_hotkey_enabled:
            self._clear_screen_clip_hotkey_arm()
            return

        payload = self._read_clipboard_image_payload()
        if not payload or not payload.get("imageSignature"):
            log_event("capture.clipboard_without_image")
            return

        # Az engedély egyszer használható, és az eseménynél dől el, nem a
        # későbbi küldéskor. Az azonos tartalmú új kivágás is új kérés.
        capture_request_id = getattr(self, "screen_clip_request_id", "")
        self._clear_screen_clip_hotkey_arm()
        queue = getattr(self, "pending_clipboard_payload_queue", None)
        if queue is None:
            queue = self.pending_clipboard_payload_queue = []
        if self.pending_clipboard_payload is not None and len(queue) >= MAX_PENDING_CLIPBOARD_IMAGES - 1:
            log_event("capture.queue_full", level="WARNING", pending_count=len(queue) + 1)
            self._save_last_run_status("A képek várakozási sora megtelt. Várd meg a feldolgozást, majd készíts új kivágást.")
            return
        request_id = capture_request_id or uuid.uuid4().hex
        payload["requestId"] = request_id
        MainWindow._invalidate_translation_result(self, request_id, "image")
        if self.pending_clipboard_payload is None:
            self.pending_clipboard_payload = payload
        else:
            queue.append(payload)
        log_event("capture.accepted", request_id=request_id, image_bytes=len(payload.get("imageBytes") or b""),
                  pending_count=len(queue) + 1)

        self.clipboard_debounce_timer.start()

    def _process_clipboard_translation(self, payload: dict[str, Any]) -> None:
        self.settings = self._read_settings_from_form()

        if not self.settings.monitoring_enabled:
            self._save_last_run_status("A figyelés ki van kapcsolva, ezért a kép kihagyva.")
            return

        if self.clipboard_translation_in_progress:
            self._save_last_run_status("Már fut egy képbeküldés, ezt az új képet most kihagyom.")
            return

        request_id = str(payload.get("requestId") or uuid.uuid4().hex)
        if not payload.get("requestId"):
            MainWindow._invalidate_translation_result(self, request_id, "image")
        self.active_translation_request_id = request_id
        started_at = time.monotonic()
        log_event("translation.started", request_id=request_id, kind="image")

        self.clipboard_translation_in_progress = True
        self._touch_clipboard_translation_heartbeat()
        self._begin_browser_interaction()

        try:
            self._save_last_run_status("Új kép érkezett a vágólapra.")
            self._show_loading_overlay()
            self._ensure_chatgpt_page_loaded(reload_if_open=False)
            self._ensure_automation_ready()
            delivery_payload, success_status_message, empty_response_status_message = self._build_translation_delivery_payload(payload)
            progress_handler = None
            progress_state = {
                "last_text": "",
                "notified": False,
            }

            if delivery_payload.get("waitForResponse"):
                progress_handler, progress_state = self._build_response_progress_handler(
                    copy_to_clipboard=bool(delivery_payload.get("copyResponseToClipboard")),
                    show_overlay=True,
                    play_sound=True,
                    request_id=request_id,
                )

            result = self._execute_delivery(delivery_payload, progress_handler=progress_handler)
            follow_up_progress_call_id = str(result.get("followUpProgressCallId") or "").strip()

            if follow_up_progress_call_id:
                self._start_response_followup_polling(follow_up_progress_call_id, progress_handler)

            translated_text = str(result.get("assistantResponseText") or "").strip()
            if result.get("assistantResponseComplete") is False:
                translated_text = ""

            if self.settings.copy_response_to_clipboard:
                if not translated_text:
                    self._hide_translation_overlay()
                    self._save_last_run_status(empty_response_status_message)
                    return

                if translated_text != str(progress_state["last_text"]):
                    self._store_translation_result(
                        translated_text,
                        copy_to_clipboard=True,
                        show_overlay=True,
                        play_sound=not bool(progress_state["notified"]),
                        request_id=request_id,
                    )
                self._save_last_run_status(f"A fordítás a vágólapra másolva és memóriába mentve. Gyorsbillentyű: {format_hotkey_definition(self.settings.type_out_hotkey)}")
                return

            if translated_text:
                self._store_translation_result(
                    translated_text,
                    copy_to_clipboard=False,
                    show_overlay=True,
                    play_sound=False,
                    request_id=request_id,
                )
            else:
                self._hide_translation_overlay()

            self._save_last_run_status(success_status_message)
        except BrowserOperationCancelled:
            log_event("translation.cancelled", request_id=request_id, kind="image", cancelled=True)
        except Exception as error:  # noqa: BLE001
            log_exception("translation.failed", error, request_id=request_id, kind="image")
            self._hide_translation_overlay()
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
        finally:
            log_event("translation.finished", request_id=request_id, kind="image",
                      duration_ms=round((time.monotonic() - started_at) * 1000),
                      success=getattr(self, "translation_result_request_id", "") == request_id)
            self.active_translation_request_id = ""
            self.clipboard_translation_in_progress = False
            self.clipboard_translation_heartbeat_monotonic = 0.0
            self._end_browser_interaction()

            if self.pending_clipboard_payload is not None:
                self.clipboard_debounce_timer.start()

    def _build_translation_delivery_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        if self.settings.ocr_text_from_clipboard_image:
            self._set_live_status("Szöveg kiolvasása képről folyamatban.")
            extracted_text_candidates = self._run_in_background_with_events(
                lambda: self.ocr_service.extract_text_candidates(
                    bytes(payload.get("imageBytes") or b""),
                    limit=5,
                    request_id=getattr(self, "active_translation_request_id", None),
                ),
                progress_message="Szöveg kiolvasása képről folyamatban.",
            )

            if not extracted_text_candidates:
                raise RuntimeError("A képről nem sikerült kiolvasni szöveget.")

            return (
                {
                    "prompt": self._build_ocr_translation_prompt(extracted_text_candidates),
                    "imageDataUrl": "",
                    "imageMimeType": "",
                    "imageFilename": "",
                    "autoSubmit": True,
                    "copyResponseToClipboard": self.settings.copy_response_to_clipboard,
                    "waitForResponse": True,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": DEFAULT_RESPONSE_TIMEOUT_MS,
                },
                "A képről kiolvasott szöveg elküldve a ChatGPT-nek.",
                "A képről kiolvasott szöveg elküldve, de a ChatGPT válasza nem lett kiolvasható.",
            )

        return (
            {
                "prompt": "",
                "imageDataUrl": str(payload["imageDataUrl"]),
                "imageMimeType": str(payload["imageMimeType"]),
                "imageFilename": str(payload["imageFilename"]),
                "autoSubmit": True,
                "copyResponseToClipboard": self.settings.copy_response_to_clipboard,
                "waitForResponse": True,
                "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                "responseTimeoutMs": DEFAULT_RESPONSE_TIMEOUT_MS,
            },
            "A kép elküldve a ChatGPT-nek.",
            "A kép elküldve, de a ChatGPT válasza nem lett kiolvasható.",
        )

    def _build_ocr_translation_prompt(self, extracted_text_candidates: tuple[str, ...]) -> str:
        numbered_candidates = "\n\n".join(
            f"{index}.\n{candidate}"
            for index, candidate in enumerate(extracted_text_candidates, start=1)
        )
        return f"OCR candidates from the same image:\n\n{numbered_candidates}"

    def _build_quick_chat_translation_prompt(self, text: str) -> str:
        cleaned_text = str(text or "").strip()
        return f"Quick chat text to translate:\n\n{cleaned_text}"

    def _build_response_progress_handler(
        self,
        *,
        copy_to_clipboard: bool,
        show_overlay: bool,
        play_sound: bool,
        request_id: str | None = None,
    ) -> tuple[Callable[[dict[str, Any]], None], dict[str, Any]]:
        state = {
            "last_text": "",
            "notified": False,
        }

        def handle_progress(progress: dict[str, Any]) -> None:
            if str(progress.get("kind") or "") != "assistant_response":
                return
            if progress.get("complete") is not True:
                log_event("response.partial_ignored", request_id=request_id,
                          text_length=len(str(progress.get("text") or "")))
                return

            translated_text = str(progress.get("text") or "").strip()

            if not translated_text or translated_text == str(state["last_text"]):
                return

            if request_id and request_id != getattr(self, "latest_translation_request_id", ""):
                log_event("response.obsolete", request_id=request_id, text_length=len(translated_text))
                return

            self._store_translation_result(
                translated_text,
                copy_to_clipboard=copy_to_clipboard,
                show_overlay=show_overlay,
                play_sound=play_sound and not bool(state["notified"]),
                request_id=request_id,
            )
            state["last_text"] = translated_text
            state["notified"] = True
            self._save_last_run_status("A legújabb fordítás megérkezett és memóriába mentve.")

        return handle_progress, state

    def _start_response_followup_polling(
        self,
        progress_call_id: str,
        progress_handler: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        normalized_progress_call_id = str(progress_call_id or "").strip()
        self._stop_response_followup_polling()

        if not normalized_progress_call_id or progress_handler is None:
            return

        self.response_followup_progress_call_id = normalized_progress_call_id
        self.response_followup_last_sequence = 0
        self.response_followup_handler = progress_handler
        self.response_followup_started_monotonic = time.monotonic()
        self.response_followup_last_activity_monotonic = self.response_followup_started_monotonic
        self.response_followup_error_count = 0
        self.response_followup_request_id = getattr(self, "active_translation_request_id", "")
        self.response_followup_diagnostic_call_id = getattr(self, "last_delivery_diagnostic_call_id", "")
        self.response_followup_waiting_for_first_response = not bool(getattr(self, "last_translated_text", ""))
        log_event("response.followup_started", request_id=self.response_followup_request_id,
                  response_pending=self.response_followup_waiting_for_first_response)
        self.response_followup_timer.start()
        if hasattr(self, "_sync_browser_host_mode"):
            self._sync_browser_host_mode()
            self._sync_browser_runtime_state()

    def _stop_response_followup_polling(self, *, stop_remote: bool = True) -> None:
        current_progress_call_id = str(self.response_followup_progress_call_id or "").strip()
        diagnostic_call_id = getattr(self, "response_followup_diagnostic_call_id", "")
        if current_progress_call_id:
            log_event("response.followup_stopped", request_id=getattr(self, "response_followup_request_id", None))

        self.response_followup_timer.stop()
        self.response_followup_progress_call_id = ""
        self.response_followup_last_sequence = 0
        self.response_followup_handler = None
        self.response_followup_started_monotonic = 0.0
        self.response_followup_last_activity_monotonic = 0.0
        self.response_followup_error_count = 0
        self.response_followup_request_id = ""
        self.response_followup_waiting_for_first_response = False
        self.response_followup_diagnostic_call_id = ""
        if hasattr(self, "_sync_browser_host_mode"):
            self._sync_browser_host_mode()
            self._sync_browser_runtime_state()

        if not current_progress_call_id:
            return

        try:
            self._run_javascript(
                f"""
                    (() => {{
                      if ({str(stop_remote).lower()} && typeof window.__gamerTranslatorStopResponseFollowUp === "function") {{
                        window.__gamerTranslatorStopResponseFollowUp({json.dumps(current_progress_call_id)}, {{ emitDone: false }});
                      }}
                      const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                      delete progressBucket[{json.dumps(current_progress_call_id)}];
                      const diagnosticBucket = window.__gamerTranslatorDiagnostics || Object.create(null);
                      delete diagnosticBucket[{json.dumps(diagnostic_call_id)}];
                      return true;
                    }})()
                """,
                timeout_ms=3000,
            )
        except Exception:
            pass

    def _poll_response_followup_progress(self) -> None:
        progress_call_id = str(self.response_followup_progress_call_id or "").strip()

        if not progress_call_id:
            self._stop_response_followup_polling(stop_remote=False)
            return

        now = time.monotonic()
        request_id = getattr(self, "response_followup_request_id", "")
        if request_id and request_id != getattr(self, "latest_translation_request_id", ""):
            self._stop_response_followup_polling()
            return

        deadline_reached = (
            self.response_followup_started_monotonic > 0.0
            and now - self.response_followup_started_monotonic >= RESPONSE_FOLLOWUP_MAX_TIMEOUT_SECONDS
        )

        idle_reached = (
            not getattr(self, "response_followup_waiting_for_first_response", False)
            and
            self.response_followup_last_activity_monotonic > 0.0
            and now - self.response_followup_last_activity_monotonic >= RESPONSE_FOLLOWUP_IDLE_TIMEOUT_SECONDS
        )

        try:
            diagnostic_call_id = getattr(self, "response_followup_diagnostic_call_id", "")
            progress_json = self._run_javascript(
                f"""
                    (() => {{
                      const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                      const diagnosticBucket = window.__gamerTranslatorDiagnostics || Object.create(null);
                      const diagnostics = diagnosticBucket[{json.dumps(diagnostic_call_id)}] || [];
                      diagnosticBucket[{json.dumps(diagnostic_call_id)}] = [];
                      return JSON.stringify({{ progress: progressBucket[{json.dumps(progress_call_id)}] ?? null, diagnostics }});
                    }})()
                """,
                timeout_ms=3000,
            )
        except BrowserOperationCancelled:
            log_event("response.followup_cancelled", request_id=request_id, cancelled=True)
            self._stop_response_followup_polling(stop_remote=False)
            return
        except Exception as error:
            log_exception("response.followup_poll_failed", error, request_id=request_id)
            self.response_followup_error_count += 1

            if deadline_reached or idle_reached or self.response_followup_error_count >= RESPONSE_FOLLOWUP_MAX_ERROR_COUNT:
                self._stop_response_followup_polling()

            return

        if not isinstance(progress_json, str) or not progress_json:
            if deadline_reached or idle_reached:
                self._stop_response_followup_polling()
            return

        if progress_call_id != self.response_followup_progress_call_id:
            return
        if request_id and request_id != getattr(self, "latest_translation_request_id", ""):
            self._stop_response_followup_polling()
            return

        try:
            progress = json.loads(progress_json)
            if isinstance(progress, dict) and "diagnostics" in progress:
                MainWindow._log_page_diagnostics(self, progress.get("diagnostics"), request_id)
                nested_progress = progress.get("progress")
                progress = json.loads(nested_progress) if isinstance(nested_progress, str) and nested_progress else {}
            if not isinstance(progress, dict):
                if deadline_reached or idle_reached:
                    self._stop_response_followup_polling()
                return
            progress_sequence = int(progress.get("seq") or 0)
        except (ValueError, TypeError, OverflowError):
            if deadline_reached or idle_reached:
                self._stop_response_followup_polling()
            return

        if progress_sequence <= self.response_followup_last_sequence:
            if deadline_reached or idle_reached:
                self._stop_response_followup_polling()
            return

        self.response_followup_last_sequence = progress_sequence
        self.response_followup_last_activity_monotonic = time.monotonic()
        self.response_followup_error_count = 0
        if str(progress.get("kind") or "") == "assistant_response" and progress.get("complete") is True:
            self.response_followup_waiting_for_first_response = False

        progress_handler = self.response_followup_handler
        if progress_handler is not None:
            try:
                progress_handler(progress)
            except Exception as error:
                log_exception("response.followup_handler_failed", error, request_id=request_id)

        if bool(progress.get("done")) or deadline_reached or idle_reached:
            self._stop_response_followup_polling(stop_remote=not bool(progress.get("done")))

    def _process_quick_chat_translation(self, prompt_text: str) -> None:
        cleaned_prompt = str(prompt_text or "").strip()
        self.settings = self._read_settings_from_form()

        if not cleaned_prompt:
            self.quick_chat_overlay.show_error("Írj be legalább egy sort a gyors chat elküldéséhez.")
            return

        if not self.settings.monitoring_enabled:
            message = "A program nincs aktív állapotban, ezért a gyors chat nem küldhető el."
            self._save_last_run_status(message)
            self.quick_chat_overlay.show_error(message)
            return

        if self.clipboard_translation_in_progress or self.browser_interaction_active:
            message = "Már fut egy másik ChatGPT művelet, várd meg amíg befejeződik."
            self._set_live_status(message)
            self.quick_chat_overlay.show_error(message)
            return

        request_id = uuid.uuid4().hex
        MainWindow._invalidate_translation_result(self, request_id, "quick_chat")
        self.active_translation_request_id = request_id
        started_at = time.monotonic()
        log_event("translation.started", request_id=request_id, kind="quick_chat", text_length=len(cleaned_prompt))

        self._begin_browser_interaction()
        self.quick_chat_overlay.hide_overlay()
        self._show_loading_overlay()

        try:
            self._save_last_run_status("A gyors chat szöveg elküldése folyamatban.")
            self._ensure_chatgpt_page_loaded(reload_if_open=False)
            self._ensure_automation_ready()
            progress_handler, progress_state = self._build_response_progress_handler(
                copy_to_clipboard=True,
                show_overlay=True,
                play_sound=True,
                request_id=request_id,
            )
            result = self._execute_delivery(
                {
                    "prompt": self._build_quick_chat_translation_prompt(cleaned_prompt),
                    "imageDataUrl": "",
                    "imageMimeType": "",
                    "imageFilename": "",
                    "autoSubmit": True,
                    "copyResponseToClipboard": True,
                    "waitForResponse": True,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": DEFAULT_RESPONSE_TIMEOUT_MS,
                },
                progress_handler=progress_handler,
            )
            follow_up_progress_call_id = str(result.get("followUpProgressCallId") or "").strip()

            if follow_up_progress_call_id:
                self._start_response_followup_polling(follow_up_progress_call_id, progress_handler)

            translated_text = str(result.get("assistantResponseText") or "").strip()
            if result.get("assistantResponseComplete") is False:
                translated_text = ""

            if not translated_text:
                message = "A gyors chat üzenet elküldve, de a ChatGPT válasza nem lett kiolvasható."
                self._hide_translation_overlay()
                self._save_last_run_status(message)
                return

            if translated_text != str(progress_state["last_text"]):
                self._store_translation_result(
                    translated_text,
                    copy_to_clipboard=True,
                    show_overlay=True,
                    play_sound=not bool(progress_state["notified"]),
                    request_id=request_id,
                )
            self._save_last_run_status(
                f"A gyors chat fordítása a vágólapra másolva és memóriába mentve. Gyorsbillentyű: {format_hotkey_definition(self.settings.type_out_hotkey)}"
            )
        except BrowserOperationCancelled:
            log_event("translation.cancelled", request_id=request_id, kind="quick_chat", cancelled=True)
        except Exception as error:  # noqa: BLE001
            log_exception("translation.failed", error, request_id=request_id, kind="quick_chat")
            self._hide_translation_overlay()
            self._save_last_run_status(str(error))
        finally:
            log_event("translation.finished", request_id=request_id, kind="quick_chat",
                      duration_ms=round((time.monotonic() - started_at) * 1000),
                      success=getattr(self, "translation_result_request_id", "") == request_id)
            self.active_translation_request_id = ""
            self._end_browser_interaction()

    def _invalidate_translation_result(self, request_id: str, kind: str) -> None:
        self.latest_translation_request_id = request_id
        self.translation_result_request_id = ""
        self.translation_result_complete = False
        self.last_translated_text = ""
        store = getattr(self, "store", None)
        if store is not None:
            store.save_last_translated_text("")
        log_event("translation.previous_result_invalidated", request_id=request_id, kind=kind)

    def _store_translation_result(
        self,
        translated_text: str,
        *,
        copy_to_clipboard: bool,
        show_overlay: bool,
        play_sound: bool,
        request_id: str | None = None,
        complete: bool = True,
    ) -> None:
        if not complete:
            log_event("response.partial_ignored", request_id=request_id, text_length=len(translated_text))
            return
        if request_id and request_id != getattr(self, "latest_translation_request_id", ""):
            log_event("translation.obsolete_result_ignored", request_id=request_id, text_length=len(translated_text))
            return
        if request_id:
            self.translation_result_request_id = request_id
        self.translation_result_complete = True
        text_changed = translated_text != self.last_translated_text
        self.last_translated_text = translated_text
        log_event("translation.result_saved", request_id=request_id, text_length=len(translated_text),
                  changed_count=int(text_changed))

        if text_changed:
            self.store.save_last_translated_text(translated_text)

        if copy_to_clipboard:
            clipboard_signal_blocker = QSignalBlocker(self.clipboard)
            self.clipboard.setText(translated_text)
            del clipboard_signal_blocker

        if show_overlay:
            self._show_translation_overlay(translated_text)

        if play_sound:
            self._play_ready_sound()

    def _play_ready_sound(self) -> None:
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except RuntimeError:
            QApplication.beep()

    def _shutdown_background_executor(self) -> None:
        future = self.current_background_future

        if future is not None and not future.done():
            future.cancel()
            last_status_update = 0.0

            while not future.done():
                if time.monotonic() - last_status_update >= 0.35:
                    self._set_live_status("Háttérben futó feldolgozás befejezése kilépés előtt.")
                    last_status_update = time.monotonic()

                self._wait_with_events(BACKGROUND_TASK_EVENT_INTERVAL_MS)

        self.background_executor.shutdown(wait=True, cancel_futures=True)

    def _run_in_background_with_events(self, task: Callable[[], Any], *, progress_message: str | None = None) -> Any:
        if self.current_background_future is not None and not self.current_background_future.done():
            raise RuntimeError("Már fut egy háttérben végzett feldolgozás.")

        future = self.background_executor.submit(self._run_low_priority_background_task, task)
        self.current_background_future = future
        last_status_update = 0.0

        try:
            while not future.done():
                if self.browser_interaction_active:
                    self._touch_browser_interaction_heartbeat()

                if self.clipboard_translation_in_progress:
                    self._touch_clipboard_translation_heartbeat()

                if progress_message and time.monotonic() - last_status_update >= 0.35:
                    self._set_live_status(progress_message)
                    last_status_update = time.monotonic()

                # A GUI-szálon telepített natív hookok az eseményhurokban
                # szolgálják ki a bemenetet. A sleep itt az egeret is megakasztaná.
                self._wait_with_events(BACKGROUND_TASK_EVENT_INTERVAL_MS)

            return future.result()
        finally:
            if self.current_background_future is future:
                self.current_background_future = None

    def _run_low_priority_background_task(self, task: Callable[[], Any]) -> Any:
        if sys.platform != "win32":
            return task()

        try:
            current_thread = kernel32.GetCurrentThread()
            previous_priority = kernel32.GetThreadPriority(current_thread)

            if previous_priority != THREAD_PRIORITY_ERROR_RETURN:
                kernel32.SetThreadPriority(current_thread, THREAD_PRIORITY_LOWEST)
        except Exception:  # noqa: BLE001
            current_thread = None
            previous_priority = THREAD_PRIORITY_ERROR_RETURN

        try:
            return task()
        finally:
            if current_thread is not None and previous_priority != THREAD_PRIORITY_ERROR_RETURN:
                try:
                    kernel32.SetThreadPriority(current_thread, previous_priority)
                except Exception:  # noqa: BLE001
                    pass

    def _save_last_run_status(self, message: str) -> None:
        log_event("status.saved", request_id=getattr(self, "active_translation_request_id", None),
                  text_length=len(message), reason="response_timeout" if message == "A ChatGPT válasza nem érkezett meg időben." else "status_update")
        self.last_run_status = self.store.save_last_run_status(message)
        self._render_last_run_status(self.last_run_status)
        self._set_live_status(message)

    def _render_last_run_status(self, status: LastRunStatus) -> None:
        if not status.message:
            target_text = "Még nincs futási állapot."

            if self.last_run_label.text() != target_text:
                self.last_run_label.setText(target_text)

            self._sync_browser_placeholder()
            return

        target_text = f"{status.at}: {status.message}"

        if self.last_run_label.text() != target_text:
            self.last_run_label.setText(target_text)

        self._sync_browser_placeholder()

    def _set_live_status(self, message: str) -> None:
        if self.status_label.text() != message:
            self.status_label.setText(message)

        if self.top_status_label.text() != message:
            self.top_status_label.setText(message)

        self._sync_browser_placeholder()

    def _should_show_translation_overlay(self) -> bool:
        return self._is_window_hidden_for_tray() or self.browser_background_mode

    def _show_loading_overlay(self) -> None:
        if not self._should_show_translation_overlay():
            return

        self.translation_overlay.show_loading()

    def _show_translation_overlay(self, translated_text: str) -> None:
        if not self._should_show_translation_overlay():
            return

        duration_ms = max(1000, int(self.settings.overlay_duration_seconds) * 1000)
        self.translation_overlay.show_translation(translated_text, duration_ms=duration_ms)

    def _hide_translation_overlay(self) -> None:
        self.translation_overlay.hide_overlay()

    def _sync_browser_placeholder(self) -> None:
        if not hasattr(self, "browser_status_placeholder") or not hasattr(self, "content_surface"):
            return

        self.browser_status_placeholder.hide()

    def _target_browser_refresh_interval_ms(self) -> int:
        hidden_for_tray = self._is_window_hidden_for_tray()
        window_visible = self.isVisible() and not self.isMinimized()

        if self.page_loading:
            return UI_FRAME_INTERVAL_MS

        if self.browser_interaction_active or self.clipboard_translation_in_progress:
            if self.settings.game_mode_enabled and hidden_for_tray:
                return GAME_MODE_BACKGROUND_FRAME_INTERVAL_MS

            return UI_FRAME_INTERVAL_MS

        if window_visible and not self.browser_background_mode:
            return IDLE_FRAME_INTERVAL_MS

        if self.browser_background_mode:
            return BACKGROUND_IDLE_FRAME_INTERVAL_MS

        return SUSPENDED_FRAME_INTERVAL_MS

    def _update_browser_refresh_timer(self, *, force: bool = False) -> None:
        if not hasattr(self, "browser_refresh_timer"):
            return

        target_interval_ms = self._target_browser_refresh_interval_ms()

        if not force and self.current_browser_refresh_interval_ms == target_interval_ms:
            return

        self.current_browser_refresh_interval_ms = target_interval_ms
        self.browser_refresh_timer.setInterval(target_interval_ms)

        if not self.browser_refresh_timer.isActive():
            self.browser_refresh_timer.start()

    def _refresh_browser_view(self) -> None:
        if not hasattr(self, "browser"):
            return

        self._update_browser_refresh_timer()
        foreground_browser_visible = (
            self.isVisible()
            and not self.isMinimized()
            and not self.browser_background_mode
        )

        if foreground_browser_visible:
            return

        if hasattr(self, "frame_pulse_dot") and self.browser_background_mode and self.browser_background_host.isVisible():
            self.frame_pulse_state = not self.frame_pulse_state
            pulse_alpha = 1 if self.frame_pulse_state else 2
            pulse_red = 16 if self.frame_pulse_state else 19
            pulse_green = 18 if self.frame_pulse_state else 21
            pulse_blue = 22 if self.frame_pulse_state else 26
            self.frame_pulse_dot.setStyleSheet(
                f"background: rgba({pulse_red}, {pulse_green}, {pulse_blue}, {pulse_alpha});"
            )
            self.frame_pulse_dot.repaint()

        if not self.browser.isVisible() or not self.browser.updatesEnabled():
            return

        self.browser.update()

        if self.browser_background_mode and self.browser_background_host.isVisible():
            self.browser_background_host.update()

    def _begin_browser_interaction(self) -> None:
        log_event("browser.interaction_started", request_id=getattr(self, "active_translation_request_id", None))
        self.browser_interaction_active = True
        self._touch_browser_interaction_heartbeat()
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()

    def _end_browser_interaction(self) -> None:
        log_event("browser.interaction_finished", request_id=getattr(self, "active_translation_request_id", None))
        self.browser_interaction_active = False
        self.browser_interaction_heartbeat_monotonic = 0.0
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()

    def _touch_browser_interaction_heartbeat(self) -> None:
        self.browser_interaction_heartbeat_monotonic = time.monotonic()

    def _touch_clipboard_translation_heartbeat(self) -> None:
        self.clipboard_translation_heartbeat_monotonic = time.monotonic()

    def _recover_stuck_interaction_flags(self) -> None:
        now = time.monotonic()
        reset_browser_interaction = (
            self.browser_interaction_active
            and not self.page_loading
            and self.browser_interaction_heartbeat_monotonic > 0.0
            and now - self.browser_interaction_heartbeat_monotonic >= INTERACTION_STALE_RESET_SECONDS
        )
        reset_clipboard_translation = (
            self.clipboard_translation_in_progress
            and self.clipboard_translation_heartbeat_monotonic > 0.0
            and now - self.clipboard_translation_heartbeat_monotonic >= INTERACTION_STALE_RESET_SECONDS
        )

        if not reset_browser_interaction and not reset_clipboard_translation:
            return

        log_event("browser.watchdog_recovered", level="WARNING",
                  request_id=getattr(self, "active_translation_request_id", None),
                  busy=reset_browser_interaction, stale=reset_clipboard_translation)

        if reset_browser_interaction:
            self.browser_interaction_active = False
            self.browser_interaction_heartbeat_monotonic = 0.0

        if reset_clipboard_translation:
            self.clipboard_translation_in_progress = False
            self.clipboard_translation_heartbeat_monotonic = 0.0
            self._hide_translation_overlay()

        self._stop_response_followup_polling()
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()
        self._set_live_status("A beragadt ChatGPT művelet állapota visszaállítva lett.")

    def _register_hotkeys(self) -> None:
        log_event("hotkey.registration_started")
        if sys.platform != "win32":
            self.hotkey_errors = {
                "type_out": "A gyorsbillentyűk csak Windowson érhetők el.",
                "screen_clip": "A gyorsbillentyűk csak Windowson érhetők el.",
                "quick_chat": "A gyorsbillentyűk csak Windowson érhetők el.",
            }
            return

        self.hotkey_system_integration_enabled = True
        self._clear_screen_clip_hotkey_arm()
        self.hotkey_generation += 1
        self.settings = self._read_settings_from_form()

        configured_hotkeys: dict[str, tuple[int, int]] = {}
        hotkey_labels = {
            "type_out": "Begépelési gyorsbillentyű",
            "screen_clip": "Képkivágási gyorsbillentyű",
            "quick_chat": "Gyors chat gyorsbillentyű",
        }
        hotkey_values = {
            "type_out": (self.settings.type_out_hotkey_enabled, self.settings.type_out_hotkey),
            "screen_clip": (self.settings.screen_clip_hotkey_enabled, self.settings.screen_clip_hotkey),
            "quick_chat": (self.settings.quick_chat_hotkey_enabled, self.settings.quick_chat_hotkey),
        }

        self.hotkey_errors = {}

        for action, (enabled, hotkey_value) in hotkey_values.items():
            if not enabled:
                continue

            try:
                configured_hotkeys[action] = parse_hotkey_definition(hotkey_value)
            except ValueError as error:
                self.hotkey_errors[action] = f"{hotkey_labels[action]} hiba: {error}"

        duplicates: dict[tuple[int, int], list[str]] = {}

        for action, hotkey in configured_hotkeys.items():
            duplicates.setdefault(hotkey, []).append(action)

        for actions in duplicates.values():
            if len(actions) < 2:
                continue

            duplicate_hotkey_labels = ", ".join(hotkey_labels[action] for action in actions)

            for action in actions:
                self.hotkey_errors[action] = f"Ütközés: {duplicate_hotkey_labels} nem lehet ugyanaz."

        self.registered_hotkeys = {
            action: hotkey for action, hotkey in configured_hotkeys.items() if action not in self.hotkey_errors
        }
        self.hotkey_pressed_states = {
            action: action in self.suppressed_hotkey_presses.values() for action in self.registered_hotkeys
        }
        self.registered_hotkey_primary_keys = {hotkey_key for _hotkey_modifiers, hotkey_key in self.registered_hotkeys.values()}
        self._update_keyboard_hook_state()

    def _unregister_hotkeys(self) -> None:
        self._clear_screen_clip_hotkey_arm()
        self.hotkey_generation += 1

        if sys.platform != "win32":
            return

        self.registered_hotkeys = {}
        self.hotkey_pressed_states = {}
        self.suppressed_hotkey_presses.clear()
        self.registered_hotkey_primary_keys = set()
        self._update_keyboard_hook_state()

    def _update_keyboard_hook_state(self) -> None:
        if sys.platform != "win32":
            return

        # Átkötés/tiltás nem szakíthatja félbe az elnyelt down/up párokat.
        # Az utolsó felengedés után a már nem szükséges hook is megszűnik.
        pending_keyboard = any(key not in MOUSE_KEYCODES for key, _injected in self.suppressed_hotkey_presses)
        pending_mouse = any(key in MOUSE_KEYCODES for key, _injected in self.suppressed_hotkey_presses)
        if self.registered_hotkeys or pending_keyboard:
            self._install_keyboard_hook()
        else:
            self._uninstall_keyboard_hook()
        mouse_hotkeys = any(key in MOUSE_KEYCODES for _modifiers, key in self.registered_hotkeys.values())
        if (mouse_hotkeys or pending_mouse
                or self.hotkey_system_integration_enabled and (active_hotkey_editor() is not None or self.mouse_recording_buttons)):
            self._install_mouse_hook()
        else:
            self._uninstall_mouse_hook()
        if not self.registered_hotkeys and not pending_keyboard:
            self._uninstall_keyboard_hook()

    def _install_keyboard_hook(self) -> None:
        log_event("hotkey.keyboard_hook_installing")
        if sys.platform != "win32" or self.keyboard_hook_handle is not None:
            return

        module_handle = kernel32.GetModuleHandleW(None)
        self.keyboard_hook_callback = HOOKPROC(self._keyboard_hook_proc)
        self.keyboard_hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.keyboard_hook_callback, module_handle, 0)

        if not self.keyboard_hook_handle:
            error_code = int(kernel32.GetLastError())
            log_event("hotkey.keyboard_hook_failed", level="ERROR", code=error_code)
            suffix = f" Windows hibakód: {error_code}" if error_code else ""
            error_message = f"A gyorsbillentyű-hook telepítése nem sikerült.{suffix}"

            for action in self.registered_hotkeys:
                self.hotkey_errors[action] = error_message

            self.registered_hotkeys = {}
            self.hotkey_pressed_states = {}
            self.registered_hotkey_primary_keys = set()
            self.keyboard_hook_handle = None
            self.keyboard_hook_callback = None

    def _uninstall_keyboard_hook(self) -> None:
        log_event("hotkey.keyboard_hook_removing", active=bool(self.keyboard_hook_handle))
        if sys.platform != "win32":
            return

        if self.keyboard_hook_handle is not None:
            user32.UnhookWindowsHookEx(self.keyboard_hook_handle)
            self.keyboard_hook_handle = None

        self.keyboard_hook_callback = None

    def _install_mouse_hook(self) -> None:
        log_event("hotkey.mouse_hook_installing")
        if sys.platform != "win32" or self.mouse_hook_handle is not None:
            return

        module_handle = kernel32.GetModuleHandleW(None)
        self.mouse_hook_callback = HOOKPROC(self._mouse_hook_proc)
        self.mouse_hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, self.mouse_hook_callback, module_handle, 0)

        if not self.mouse_hook_handle:
            error_code = int(kernel32.GetLastError())
            log_event("hotkey.mouse_hook_failed", level="ERROR", code=error_code)
            suffix = f" Windows hibakód: {error_code}" if error_code else ""
            for action, (_modifiers, key) in list(self.registered_hotkeys.items()):
                if key in MOUSE_KEYCODES:
                    self.hotkey_errors[action] = f"Az egérgombfigyelő telepítése nem sikerült.{suffix}"
                    del self.registered_hotkeys[action]
                    self.hotkey_pressed_states.pop(action, None)
            self.registered_hotkey_primary_keys = {key for _modifiers, key in self.registered_hotkeys.values()}
            self.mouse_hook_handle = None
            self.mouse_hook_callback = None

    def _uninstall_mouse_hook(self) -> None:
        log_event("hotkey.mouse_hook_removing", active=bool(self.mouse_hook_handle))
        if sys.platform != "win32":
            return

        if self.mouse_hook_handle is not None:
            user32.UnhookWindowsHookEx(self.mouse_hook_handle)
            self.mouse_hook_handle = None

        self.mouse_hook_callback = None
        self.mouse_recording_buttons.clear()

    def _mouse_hook_proc(self, n_code: int, w_param, l_param):
        message = int(w_param)
        if n_code != HC_ACTION or message not in (WM_XBUTTONDOWN, WM_XBUTTONUP):
            return user32.CallNextHookEx(self.mouse_hook_handle, n_code, w_param, l_param)

        mouse_data = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
        injected = bool(mouse_data.flags & LLMHF_INJECTED)
        if injected and int(mouse_data.dwExtraInfo) == OWN_INPUT_MARKER:
            return user32.CallNextHookEx(self.mouse_hook_handle, n_code, w_param, l_param)

        button = (int(mouse_data.mouseData) >> 16) & 0xFFFF
        vk_code = {1: 0x05, 2: 0x06}.get(button)
        if vk_code is None:
            return user32.CallNextHookEx(self.mouse_hook_handle, n_code, w_param, l_param)

        press = (vk_code, injected)
        if message == WM_XBUTTONUP:
            if press in self.mouse_recording_buttons:
                self.mouse_recording_buttons.discard(press)
                QTimer.singleShot(0, self._update_keyboard_hook_state)
                return 1
            if self._handle_hotkey_keyup(vk_code, injected=injected):
                return 1
        else:
            if press in self.mouse_recording_buttons:
                return 1
            if any(key == vk_code for key, _source in self.suppressed_hotkey_presses):
                self._handle_hotkey_keydown(vk_code, injected=injected)
                return 1
            editor = active_hotkey_editor()
            if editor is not None:
                # Rögzítés közben nem indítunk fordítást és nem navigálunk
                # vissza/előre. A felirat frissítése már az eseményhurok dolga.
                self.mouse_recording_buttons.add(press)
                modifiers = current_hotkey_modifiers()
                QTimer.singleShot(0, lambda: editor.record_mouse_button(vk_code, modifiers))
                return 1
            if self._handle_hotkey_keydown(vk_code, injected=injected):
                return 1

        return user32.CallNextHookEx(self.mouse_hook_handle, n_code, w_param, l_param)

    def _keyboard_hook_proc(self, n_code: int, w_param, l_param):
        if n_code != HC_ACTION:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        message = int(w_param)
        if message not in (WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP):
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)
        key_data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk_code = int(key_data.vkCode)

        injected = bool(key_data.flags & LLKHF_INJECTED)
        if injected and int(key_data.dwExtraInfo) == OWN_INPUT_MARKER:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        if message in (WM_KEYUP, WM_SYSKEYUP):
            if self._handle_hotkey_keyup(vk_code, injected=injected):
                return 1
        elif any(key == vk_code for key, _source in self.suppressed_hotkey_presses):
            # A már elnyelt gomb ismétlése a rögzítőmezőnek sem adható át.
            self._handle_hotkey_keydown(vk_code, injected=injected)
            return 1

        if not self.registered_hotkeys:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        if active_hotkey_editor() is not None:
            # A rögzítés nem folytathat egy korábban megszakított kivágást;
            # az itt lenyomott Esc/Win+Shift+S se hagyhasson küldési engedélyt.
            self._clear_screen_clip_hotkey_arm()
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        if message in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if vk_code in self.registered_hotkey_primary_keys and self._handle_hotkey_keydown(vk_code, injected=injected):
                return 1

            # Az Esc megszakítja a saját kivágást. A külön indított Windows
            # képkivágás sem használhat fel egy korábbról megmaradt engedélyt.
            # Ezeket a billentyűket továbbengedjük a Windowsnak.
            if vk_code == 0x1B or (vk_code == ord("S") and self._current_modifiers_match(MOD_WIN | MOD_SHIFT)):
                self._clear_screen_clip_hotkey_arm()

        return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

    def _handle_hotkey_keydown(self, vk_code: int, *, injected: bool = False) -> bool:
        # Ugyanaz a lenyomva tartott főgomb módosítóváltáskor sem indíthat
        # egy másik, ugyanarra a gombra beállított műveletet.
        for (key, _source), action in list(self.suppressed_hotkey_presses.items()):
            if key == vk_code:
                self.suppressed_hotkey_presses[(vk_code, injected)] = action
                return True

        for action, (hotkey_modifiers, hotkey_key) in self.registered_hotkeys.items():
            if hotkey_key != vk_code:
                continue

            if not self._current_modifiers_match(hotkey_modifiers):
                continue

            self.suppressed_hotkey_presses[(vk_code, injected)] = action
            self.hotkey_pressed_states[action] = True
            typing_context = None
            if action == "type_out":
                target_window = user32.GetForegroundWindow()
                if type(target_window) is int:
                    # A GUI callback késése nem választhat új célablakot vagy új szöveget.
                    typing_context = {"target_window": target_window, "text": self.last_translated_text,
                                      "request_id": getattr(self, "latest_translation_request_id", "")}
            self._mask_hotkey_modifier_menu(hotkey_modifiers)
            generation = self.hotkey_generation
            if typing_context is not None:
                QTimer.singleShot(0, lambda action_name=action, context=typing_context: self._trigger_hotkey_action(
                    action_name, generation, typing_context=context))
            else:
                QTimer.singleShot(0, lambda action_name=action: self._trigger_hotkey_action(action_name, generation))

            return True

        return False

    def _handle_hotkey_keyup(self, vk_code: int, *, injected: bool = False) -> bool:
        action = self.suppressed_hotkey_presses.pop((vk_code, injected), None)
        if action is None:
            return False
        if action in self.hotkey_pressed_states:
            self.hotkey_pressed_states[action] = action in self.suppressed_hotkey_presses.values()
        if vk_code in MOUSE_KEYCODES or not self.registered_hotkeys:
            QTimer.singleShot(0, self._update_keyboard_hook_state)
        return True

    def _trigger_hotkey_action(self, action: str, generation: int | None = None, *, typing_context: dict[str, Any] | None = None) -> None:
        if (action not in self.registered_hotkeys
                or generation is not None and generation != self.hotkey_generation
                or active_hotkey_editor() is not None):
            log_event("hotkey.rejected", action=action, reason="inactive_or_generation", generation=generation or 0)
            return

        if self.hotkey_action_running:
            queue = getattr(self, "pending_hotkey_actions", None)
            if queue is None:
                queue = self.pending_hotkey_actions = []
            if action != "type_out" and len(queue) < 4:
                queue.append((action, self.hotkey_generation))
                log_event("hotkey.queued", action=action, pending_count=len(queue))
            else:
                log_event("hotkey.rejected", action=action, reason="busy", pending_count=len(queue))
            return

        log_event("hotkey.triggered", action=action, generation=self.hotkey_generation)
        self.hotkey_action_running = True
        started_at = time.monotonic()
        try:
            if action == "type_out":
                if typing_context is None:
                    self._trigger_type_out_hotkey()
                else:
                    self._trigger_type_out_hotkey(typing_context=typing_context)
            elif action == "screen_clip":
                self._trigger_screen_clip_hotkey()
            elif action == "quick_chat":
                self._trigger_quick_chat_hotkey()
        except Exception as error:
            log_exception("hotkey.failed", error, action=action)
            raise
        finally:
            self.hotkey_action_running = False
            log_event("hotkey.finished", action=action, duration_ms=round((time.monotonic() - started_at) * 1000))
            queue = getattr(self, "pending_hotkey_actions", [])
            if queue:
                next_action, next_generation = queue.pop(0)
                QTimer.singleShot(0, lambda: self._trigger_hotkey_action(next_action, next_generation))

    def _mask_hotkey_modifier_menu(self, modifiers: int) -> None:
        if sys.platform != "win32":
            return
        if not (modifiers & MOD_WIN or modifiers & MOD_ALT and not modifiers & MOD_CONTROL):
            return
        # Az elnyelt főgomb nélkül az Alt/Win puszta lenyomásnak látszana.
        # A funkció nélküli vkFF pár maszkolja ezt, a valódi módosítók
        # felengedését viszont továbbengedjük, hogy ne maradjanak beragadva.
        inputs = (INPUT * 2)(build_key_input(0xFF), build_key_input(0xFF, key_up=True))
        inserted = user32.SendInput(2, inputs, ctypes.sizeof(INPUT))
        if inserted == 1:
            release = (INPUT * 1)(build_key_input(0xFF, key_up=True))
            user32.SendInput(1, release, ctypes.sizeof(INPUT))
        if inserted != 2:
            QTimer.singleShot(0, lambda: self._set_live_status(
                "A gyorsgomb elnyelve, de a Windows nem engedte az Alt/Win menüaktiválásának maszkolását."
            ))

    def _current_modifiers_match(self, modifiers: int) -> bool:
        if sys.platform != "win32":
            return False

        return current_hotkey_modifiers() == modifiers

    def _hotkey_status_message(self, prefix: str) -> str:
        if not self.hotkey_errors:
            return prefix

        return f"{prefix} {' | '.join(self.hotkey_errors.values())}"

    def _trigger_type_out_hotkey(self, *, typing_context: dict[str, Any] | None = None) -> None:
        if getattr(self, "operations_cancelled", False) or getattr(self, "exit_requested", False):
            log_event("typing.rejected", reason="shutdown", request_id=typing_context["request_id"]
                      if typing_context is not None else getattr(self, "latest_translation_request_id", None))
            return
        typing_generation = getattr(self, "hotkey_generation", None)
        if self.hotkey_errors.get("type_out"):
            self._set_live_status(self.hotkey_errors["type_out"])
            return

        text_snapshot = typing_context["text"] if typing_context is not None else self.last_translated_text
        latest_request_id = typing_context["request_id"] if typing_context is not None else getattr(self, "latest_translation_request_id", "")
        if not text_snapshot:
            log_event("typing.rejected", reason="no_current_translation", request_id=getattr(self, "latest_translation_request_id", None))
            self._set_live_status("Nincs kész fordítás a legutóbbi kéréshez. Várd meg a választ, vagy készíts új kivágást.")
            return

        if latest_request_id and latest_request_id != getattr(self, "translation_result_request_id", ""):
            log_event("typing.rejected", reason="obsolete_translation", request_id=latest_request_id)
            self._set_live_status("A legutóbbi fordítás még nem készült el.")
            return
        if not getattr(self, "translation_result_complete", True):
            log_event("typing.rejected", reason="response_pending", request_id=latest_request_id)
            self._set_live_status("A fordítás még készül. Várd meg a teljes választ, majd nyomd meg újra a gyorsgombot.")
            return
        snapshot_error = _typing_snapshot_error(self, text_snapshot, latest_request_id)
        if snapshot_error:
            log_event("typing.rejected", reason=snapshot_error, request_id=latest_request_id)
            self._set_live_status("A fordítás megváltozott a gyorsgomb lenyomása óta. Nyomd meg újra a gyorsgombot.")
            return

        # A várakozás alatt is válthat ablakot a felhasználó; a cél már a
        # gyorsbillentyű aktiválásakor rögzített, nem a felengedés után.
        target_window = (typing_context["target_window"] if typing_context is not None
                         else user32.GetForegroundWindow() if sys.platform == "win32" else None)
        if not target_window:
            log_event("typing.rejected", reason="no_foreground", request_id=latest_request_id)
            self._set_live_status("A begépeléshez nem azonosítható aktív ablak.")
            return
        modifiers_released = self._wait_for_modifier_release()
        if getattr(self, "operations_cancelled", False) or getattr(self, "exit_requested", False):
            log_event("typing.cancelled", reason="shutdown", request_id=latest_request_id)
            return
        if typing_generation is not None and typing_generation != getattr(self, "hotkey_generation", None):
            log_event("typing.rejected", reason="hotkey_changed", request_id=latest_request_id)
            self._set_live_status("A begépelés nem indult el, mert megváltozott a gyorsbillentyű beállítása. Nyomd meg újra a gyorsgombot.")
            return
        if not modifiers_released:
            log_event("typing.rejected", reason="modifier_timeout", request_id=latest_request_id, timeout_ms=1200)
            self._set_live_status("A begépelés nem indult el, mert a módosító billentyű lenyomva maradt. Engedd fel az Alt/Ctrl/Shift/Win gombokat, majd próbáld újra.")
            return
        if self._type_cached_text_via_hotkey(target_window=target_window, text_snapshot=text_snapshot, request_id=latest_request_id):
            log_event("typing.completed", request_id=latest_request_id, text_length=len(text_snapshot))
            self._set_live_status(f"A mentett fordítás begépelve: {format_hotkey_definition(self.settings.type_out_hotkey)}")

    def _trigger_screen_clip_hotkey(self) -> None:
        if self.hotkey_errors.get("screen_clip"):
            self._set_live_status(self.hotkey_errors["screen_clip"])
            return

        if sys.platform != "win32":
            self._set_live_status("A képkivágási gyorsbillentyű csak Windowson érhető el.")
            return

        self.settings = self._read_settings_from_form()
        if not self.settings.monitoring_enabled or not self.settings.screen_clip_hotkey_enabled:
            self._clear_screen_clip_hotkey_arm()
            self._set_live_status("A program vagy a képkivágási gyorsbillentyű ki van kapcsolva.")
            return

        self._arm_screen_clip_hotkey()

        try:
            os.startfile("ms-screenclip:")
            self._set_live_status(f"A Windows képkivágó megnyitva: {format_hotkey_definition(self.settings.screen_clip_hotkey)}")
        except OSError as error:
            log_exception("capture.launch_failed", error)
            self._clear_screen_clip_hotkey_arm()
            self._set_live_status(f"A képkivágó nem indítható el: {error}")

    def _trigger_quick_chat_hotkey(self) -> None:
        if self.hotkey_errors.get("quick_chat"):
            self._set_live_status(self.hotkey_errors["quick_chat"])
            return

        if self.browser_interaction_active or self.clipboard_translation_in_progress:
            self._set_live_status("Már fut egy másik ChatGPT művelet, várd meg amíg befejeződik.")
            return

        if self.quick_chat_overlay.isVisible():
            self._wait_for_modifier_release()
            self.quick_chat_overlay.hide_overlay()
            self._set_live_status("A gyors chat overlay bezárva.")
            return

        self._hide_translation_overlay()
        self._wait_for_modifier_release()
        self.quick_chat_overlay.show_overlay()
        self._set_live_status(f"A gyors chat overlay megnyitva: {format_hotkey_definition(self.settings.quick_chat_hotkey)}")

    def _wait_for_modifier_release(self) -> bool:
        if sys.platform != "win32":
            return False

        deadline = time.monotonic() + 1.2

        while time.monotonic() < deadline:
            if getattr(self, "operations_cancelled", False) or getattr(self, "exit_requested", False):
                return False
            if not _typing_modifiers_pressed():
                return True

            QGuiApplication.processEvents()
            time.sleep(0.02)

        return False

    def _type_cached_text_via_hotkey(self, *, target_window: int | None = None, text_snapshot: str | None = None, request_id: str | None = None) -> bool:
        text_snapshot = self.last_translated_text if text_snapshot is None else text_snapshot
        if sys.platform != "win32" or not text_snapshot:
            return False

        if target_window is None:
            target_window = user32.GetForegroundWindow()

        typing_request_id = getattr(self, "latest_translation_request_id", "") if request_id is None else request_id
        typing_generation = getattr(self, "hotkey_generation", None)
        event_flags = _typing_event_flags(target_window)
        log_event("typing.started", request_id=typing_request_id, text_length=len(text_snapshot),
                  mode="same_process" if event_flags == QEventLoop.ProcessEventsFlag.AllEvents else "external_process")
        last_caps_lock_state = None
        typed_count = 0
        for character in text_snapshot:
            # A hosszú begépelés alatt is ki kell szolgálni a natív hookot,
            # különben a Windows időtúllépés miatt eltávolíthatja.
            QGuiApplication.processEvents(event_flags)
            snapshot_error = _typing_snapshot_error(self, text_snapshot, typing_request_id, typing_generation)
            if snapshot_error:
                log_event("typing.cancelled", request_id=typing_request_id, reason=snapshot_error, count=typed_count)
                if snapshot_error != "shutdown":
                    self._set_live_status("A begépelés megszakadt, mert megváltozott a gyorsbillentyű beállítása. Nyomd meg újra a gyorsgombot."
                                          if snapshot_error == "hotkey_changed" else
                                          "A begépelés megszakadt, mert a fordítás megváltozott. Nyomd meg újra a gyorsgombot a friss szöveghez.")
                return False
            if not target_window or user32.GetForegroundWindow() != target_window:
                log_event("typing.cancelled", request_id=typing_request_id, reason="focus_changed")
                self._set_live_status("A begépelés megszakadt, mert megváltozott az aktív ablak.")
                return False
            if _typing_modifiers_pressed():
                log_event("typing.cancelled", request_id=typing_request_id, reason="modifier_pressed", count=typed_count)
                self._set_live_status("A begépelés megszakadt, mert módosító billentyűt nyomtál le. Engedd fel az Alt/Ctrl/Shift/Win gombokat, majd próbáld újra.")
                return False
            caps_lock_state = _typing_caps_lock_enabled()
            if caps_lock_state != last_caps_lock_state:
                # A GetKeyState a hívó üzenetsorának állapotát méri; ez nem
                # bizonyítja a másik folyamat célmezőjének CapsLock állapotát.
                log_event("typing.keyboard_state", level="DEBUG", request_id=typing_request_id,
                          kind="caps_lock", source="caller_queue", enabled=caps_lock_state)
                last_caps_lock_state = caps_lock_state
            inputs = build_character_inputs(character, keyboard_layout=_typing_keyboard_layout(target_window), caps_lock=caps_lock_state)

            if not inputs:
                continue

            input_array = (INPUT * len(inputs))(*inputs)
            kernel32.SetLastError(0)
            inserted_count = user32.SendInput(len(inputs), input_array, ctypes.sizeof(INPUT))
            if inserted_count != len(inputs):
                native_error = kernel32.GetLastError()
                error_code = native_error if type(native_error) is int else 0
                log_event("typing.input_rejected", level="ERROR", request_id=typing_request_id,
                          reason="partial_input" if inserted_count else "blocked_input",
                          count=inserted_count, pending_count=max(0, len(inputs) - inserted_count), code=error_code)
                # Részleges bevitel után a szintetikus Shift/Alt/billentyű sem maradhat lenyomva.
                if inserted_count > 0:
                    releases = _partial_input_releases(inputs, inserted_count)
                    # Csak a sikeres saját prefixben lenyomott billentyűket
                    # engedjük fel; nincs általános fizikai módosítófelengedés.
                    for attempt in range(1, 3):
                        if not releases:
                            break
                        release_array = (INPUT * len(releases))(*releases)
                        kernel32.SetLastError(0)
                        released_count = user32.SendInput(len(releases), release_array, ctypes.sizeof(INPUT))
                        if released_count == len(releases):
                            break
                        release_error = kernel32.GetLastError()
                        log_event("typing.release_rejected", level="ERROR", request_id=typing_request_id,
                                  count=released_count, pending_count=max(0, len(releases) - released_count),
                                  code=release_error if type(release_error) is int else 0, attempt=attempt)
                        releases = releases[max(0, released_count):]
                self._set_live_status("A Windows nem engedélyezte a szöveg teljes begépelését.")
                return False
            typed_count += 1
            time.sleep(0.012)

        if event_flags == QEventLoop.ProcessEventsFlag.AllEvents:
            # Az utolsó karakter se maradjon a saját Qt célmező sorában,
            # miközben a státusz már sikeres begépelést jelez.
            QGuiApplication.processEvents(event_flags)
        snapshot_error = _typing_snapshot_error(self, text_snapshot, typing_request_id, typing_generation)
        if snapshot_error:
            log_event("typing.cancelled", request_id=typing_request_id, reason=snapshot_error, count=typed_count)
            if snapshot_error != "shutdown":
                self._set_live_status("A begépelés megszakadt, mert megváltozott a gyorsbillentyű beállítása. Nyomd meg újra a gyorsgombot."
                                      if snapshot_error == "hotkey_changed" else
                                      "A begépelés megszakadt, mert a fordítás megváltozott. Nyomd meg újra a gyorsgombot a friss szöveghez.")
            return False
        if event_flags == QEventLoop.ProcessEventsFlag.AllEvents:
            if user32.GetForegroundWindow() != target_window:
                log_event("typing.cancelled", request_id=typing_request_id, reason="focus_changed", count=typed_count)
                self._set_live_status("A begépelés megszakadt, mert megváltozott az aktív ablak.")
                return False

        return True

    def _apply_settings_to_form(self, settings: AppSettings) -> None:
        self.monitoring_enabled.setChecked(settings.monitoring_enabled)
        self.prompt_template.setPlainText(settings.prompt_template)
        self.copy_response_to_clipboard.setChecked(settings.copy_response_to_clipboard)
        self.ocr_text_from_clipboard_image.setChecked(settings.ocr_text_from_clipboard_image)
        self.webview_gpu_acceleration_enabled.setChecked(settings.webview_gpu_acceleration_enabled)
        self.type_out_hotkey_enabled.setChecked(settings.type_out_hotkey_enabled)
        self.screen_clip_hotkey_enabled.setChecked(settings.screen_clip_hotkey_enabled)
        self.quick_chat_hotkey_enabled.setChecked(settings.quick_chat_hotkey_enabled)
        self.keep_chatgpt_in_background.setChecked(settings.keep_chatgpt_in_background)
        self.game_mode_enabled.setChecked(settings.game_mode_enabled)
        self._set_hotkey_value(self.screen_clip_hotkey, settings.screen_clip_hotkey)
        self._set_hotkey_value(self.type_out_hotkey, settings.type_out_hotkey)
        self._set_hotkey_value(self.quick_chat_hotkey, settings.quick_chat_hotkey)
        self.overlay_opacity_slider.setValue(settings.overlay_opacity_percent)
        self.overlay_duration_seconds.setValue(settings.overlay_duration_seconds)
        self.page_ready_timeout_ms.setValue(settings.page_ready_timeout_ms)

    def _read_settings_from_form(self) -> AppSettings:
        return AppSettings(
            monitoring_enabled=self.monitoring_enabled.isChecked(),
            chatgpt_url=CHATGPT_URL,
            keep_chatgpt_in_background=self.keep_chatgpt_in_background.isChecked(),
            game_mode_enabled=self.game_mode_enabled.isChecked(),
            prompt_template=self.prompt_template.toPlainText().strip() or str(DEFAULT_SETTINGS["promptTemplate"]),
            auto_submit=True,
            copy_response_to_clipboard=self.copy_response_to_clipboard.isChecked(),
            ocr_text_from_clipboard_image=self.ocr_text_from_clipboard_image.isChecked(),
            webview_gpu_acceleration_enabled=self.webview_gpu_acceleration_enabled.isChecked(),
            type_out_hotkey_enabled=self.type_out_hotkey_enabled.isChecked(),
            type_out_hotkey=self._read_hotkey_value(self.type_out_hotkey, str(DEFAULT_SETTINGS["typeOutHotkey"])),
            screen_clip_hotkey_enabled=self.screen_clip_hotkey_enabled.isChecked(),
            screen_clip_hotkey=self._read_hotkey_value(self.screen_clip_hotkey, str(DEFAULT_SETTINGS["screenClipHotkey"])),
            quick_chat_hotkey_enabled=self.quick_chat_hotkey_enabled.isChecked(),
            quick_chat_hotkey=self._read_hotkey_value(self.quick_chat_hotkey, str(DEFAULT_SETTINGS["quickChatHotkey"])),
            overlay_opacity_percent=self.overlay_opacity_slider.value(),
            overlay_duration_seconds=self.overlay_duration_seconds.value(),
            page_ready_timeout_ms=self.page_ready_timeout_ms.value(),
        )

    def _set_drawer_open(self, opened: bool) -> None:
        self.drawer_open = opened
        self._set_browser_blur(opened)
        self._layout_overlay_widgets()

        visible_x, hidden_x, top_margin, _panel_height = self._drawer_positions()
        target_x = visible_x if opened else hidden_x

        self.drawer_animation.stop()
        self.drawer_panel.show()
        self.drawer_animation.setStartValue(self.drawer_panel.pos())
        self.drawer_animation.setEndValue(QPoint(target_x, top_margin))
        self.drawer_animation.start()

        self.backdrop_animation.stop()

        if opened:
            self.drawer_backdrop.show()
            self.drawer_backdrop.raise_()
            self.drawer_panel.raise_()
            self.backdrop_animation.setStartValue(self.drawer_backdrop.get_opacity())
            self.backdrop_animation.setEndValue(1.0)
            self.backdrop_animation.start()
            self.close_drawer_button.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self.backdrop_animation.setStartValue(self.drawer_backdrop.get_opacity())
            self.backdrop_animation.setEndValue(0.0)
            self.backdrop_animation.start()
            self.menu_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_drawer_animation_finished(self) -> None:
        if not self.drawer_open:
            self.drawer_panel.hide()
            self.menu_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_backdrop_animation_finished(self) -> None:
        if not self.drawer_open:
            self.drawer_backdrop.hide()

    def _set_browser_blur(self, enabled: bool) -> None:
        if enabled:
            blur_effect = QGraphicsBlurEffect(self.browser)
            blur_effect.setBlurRadius(18)
            self.browser.setGraphicsEffect(blur_effect)
            self.browser_blur_effect = blur_effect
            return

        self.browser.setGraphicsEffect(None)
        self.browser_blur_effect = None

    def _drawer_positions(self) -> tuple[int, int, int, int]:
        surface_width = max(320, self.content_surface.width())
        surface_height = max(320, self.content_surface.height())
        margin = 0
        panel_width = surface_width
        panel_height = surface_height
        visible_x = 0
        hidden_x = -panel_width
        self.drawer_panel.resize(panel_width, panel_height)
        return visible_x, hidden_x, margin, panel_height

    def _layout_overlay_widgets(self) -> None:
        if not hasattr(self, "content_surface"):
            return

        surface_width = max(320, self.content_surface.width())
        surface_height = max(320, self.content_surface.height())
        placeholder_margin = 24
        self.browser_status_placeholder.setGeometry(
            placeholder_margin,
            placeholder_margin,
            max(160, surface_width - (placeholder_margin * 2)),
            max(160, surface_height - (placeholder_margin * 2)),
        )
        self.drawer_backdrop.setGeometry(0, 0, surface_width, surface_height)

        visible_x, hidden_x, top_margin, panel_height = self._drawer_positions()
        current_x = visible_x if self.drawer_open else hidden_x
        self.drawer_panel.move(current_x, top_margin)
        self.drawer_panel.resize(self.drawer_panel.width(), panel_height)

        if self.drawer_open:
            self.browser_status_placeholder.raise_()
            self.drawer_backdrop.raise_()
            self.drawer_panel.raise_()

        if hasattr(self, "frame_pulse_dot"):
            pulse_x = max(0, surface_width - 1)
            pulse_y = max(0, surface_height - 1)
            self.frame_pulse_dot.setGeometry(pulse_x, pulse_y, 1, 1)
            self.frame_pulse_dot.raise_()

        self._sync_browser_placeholder()

    def _ensure_automation_ready(self) -> None:
        if self.page_loading:
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)

        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()

        ready = self._run_javascript(
            f"typeof window.__gamerTranslatorDeliver === 'function' && window.__gamerTranslatorDeliverVersion === '{AUTOMATION_SCRIPT_VERSION}';",
            timeout_ms=5000,
        )

        if ready is True:
            self.automation_ready = True
            return

        log_event("browser.automation_injected", source="application_world")
        self._run_javascript(self.automation_script, timeout_ms=10000)
        ready = self._run_javascript(
            f"typeof window.__gamerTranslatorDeliver === 'function' && window.__gamerTranslatorDeliverVersion === '{AUTOMATION_SCRIPT_VERSION}';",
            timeout_ms=5000,
        )

        if ready is not True:
            raise RuntimeError("Nem sikerült betölteni az oldalautomatizálást.")

        self.automation_ready = True

    def _execute_delivery(
        self,
        payload: dict[str, Any],
        *,
        progress_handler: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        self._stop_response_followup_polling()
        self._ensure_automation_ready()
        call_id = uuid.uuid4().hex
        request_id = getattr(self, "active_translation_request_id", "") or call_id
        diagnostic_call_id = uuid.uuid4().hex
        self.last_delivery_diagnostic_call_id = diagnostic_call_id
        progress_call_id = f"{call_id}-progress"
        payload_with_progress = dict(payload)
        payload_with_progress["progressCallId"] = progress_call_id
        payload_with_progress["diagnosticCallId"] = diagnostic_call_id
        log_event("delivery.started", request_id=request_id, has_image=bool(payload.get("imageDataUrl")),
                  text_length=len(str(payload.get("prompt") or "")), timeout_ms=int(payload.get("responseTimeoutMs", 0)))
        payload_json = json.dumps(payload_with_progress, ensure_ascii=False).replace("</", "<\\/")
        launch_script = f"""
            (() => {{
              window.__gamerTranslatorResults = window.__gamerTranslatorResults || Object.create(null);
              window.__gamerTranslatorProgress = window.__gamerTranslatorProgress || Object.create(null);
              window.__gamerTranslatorDeliver({payload_json})
                .then((result) => {{
                  window.__gamerTranslatorResults["{call_id}"] = JSON.stringify(result);
                }})
                .catch((error) => {{
                  window.__gamerTranslatorResults["{call_id}"] = JSON.stringify({{
                    ok: false,
                    error: String(error)
                  }});
                }});
              return true;
            }})()
        """
        preserve_diagnostics = False
        try:
            self._run_javascript(launch_script, timeout_ms=5000)

            timeout_ms = (
                int(payload.get("pageReadyTimeoutMs", self.settings.page_ready_timeout_ms))
                + int(payload.get("responseTimeoutMs", DEFAULT_RESPONSE_TIMEOUT_MS))
                + AUTOMATION_SELF_HEAL_TIMEOUT_BUFFER_MS
            )
            started_at = time.monotonic()
            last_progress_sequence = 0

            while (time.monotonic() - started_at) * 1000 < timeout_ms:
                self._touch_browser_interaction_heartbeat()
                state_json = self._run_javascript(
                    f"""
                        (() => {{
                          const resultBucket = window.__gamerTranslatorResults || Object.create(null);
                          const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                          const resultValue = resultBucket["{call_id}"];
                          const progressValue = progressBucket["{progress_call_id}"] ?? null;
                          const diagnosticBucket = window.__gamerTranslatorDiagnostics || Object.create(null);
                          const diagnostics = diagnosticBucket["{diagnostic_call_id}"] || [];
                          diagnosticBucket["{diagnostic_call_id}"] = [];

                          if (resultValue !== undefined) {{
                            delete resultBucket["{call_id}"];
                            delete progressBucket["{progress_call_id}"];
                          }}

                          return JSON.stringify({{
                            result: resultValue === undefined ? null : resultValue,
                            progress: progressValue,
                            diagnostics
                          }});
                        }})()
                    """,
                    timeout_ms=5000,
                )

                state = json.loads(state_json) if isinstance(state_json, str) and state_json else {}
                MainWindow._log_page_diagnostics(self, state.get("diagnostics"), request_id)
                progress_json = state.get("progress")

                if isinstance(progress_json, str) and progress_json and progress_handler is not None:
                    progress = json.loads(progress_json)
                    progress_sequence = int(progress.get("seq") or 0)

                    if progress_sequence > last_progress_sequence:
                        last_progress_sequence = progress_sequence

                        try:
                            progress_handler(progress)
                        except Exception as error:
                            log_exception("response.progress_failed", error, request_id=request_id)

                result_json = state.get("result")

                if isinstance(result_json, str) and result_json:
                    result = json.loads(result_json)
                    preserve_diagnostics = bool(result.get("followUpProgressCallId"))

                    if result.get("ok") is False:
                        followup_id = str(result.get("followUpProgressCallId") or "").strip()
                        if followup_id and progress_handler is not None:
                            self._start_response_followup_polling(followup_id, progress_handler)
                        log_event("delivery.failed", level="ERROR", request_id=request_id,
                                  reason="response_timeout" if result.get("responsePending") else "page_operation",
                                  response_pending=bool(result.get("responsePending")))
                        raise RuntimeError(result.get("error") or "Az oldaloldali művelet hibával tért vissza.")

                    log_event("delivery.completed", request_id=request_id,
                              text_length=len(str(result.get("assistantResponseText") or "")))
                    return result

                self._wait_with_events(UI_FRAME_INTERVAL_MS)

            log_event("delivery.timeout", level="ERROR", request_id=request_id, timeout_ms=timeout_ms)
            raise RuntimeError("A ChatGPT oldaloldali művelete nem fejeződött be időben.")
        finally:
            try:
                self._run_javascript(
                    f"""
                        (() => {{
                          const resultBucket = window.__gamerTranslatorResults || Object.create(null);
                          const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                          delete resultBucket["{call_id}"];
                          delete progressBucket["{progress_call_id}"];
                          if (!{str(preserve_diagnostics).lower()}) {{
                            const diagnosticBucket = window.__gamerTranslatorDiagnostics || Object.create(null);
                            delete diagnosticBucket["{diagnostic_call_id}"];
                          }}
                          return true;
                        }})()
                    """,
                    timeout_ms=3000,
                )
            except Exception:
                pass

    def _wait_for_page_load(self, timeout_ms: int) -> None:
        if getattr(self, "operations_cancelled", False):
            raise BrowserOperationCancelled()
        if not self.page_loading:
            return

        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        heartbeat_timer = QTimer()
        heartbeat_timer.setInterval(INTERACTION_HEARTBEAT_INTERVAL_MS)

        def touch_interaction_heartbeat() -> None:
            if self.browser_interaction_active:
                self._touch_browser_interaction_heartbeat()

            if self.clipboard_translation_in_progress:
                self._touch_clipboard_translation_heartbeat()

        def finish(*_args: object) -> None:
            if loop.isRunning():
                loop.quit()

        timer.timeout.connect(finish)
        self.browser.loadFinished.connect(finish)
        cancel_signal = getattr(self, "browser_operations_cancelled", None)
        if cancel_signal is not None:
            cancel_signal.connect(finish)
        timer.start(timeout_ms)
        heartbeat_timer.timeout.connect(touch_interaction_heartbeat)
        heartbeat_timer.start()
        loop.exec()
        timer.stop()
        heartbeat_timer.stop()

        try:
            self.browser.loadFinished.disconnect(finish)
        except RuntimeError:
            pass

        if cancel_signal is not None:
            cancel_signal.disconnect(finish)
        if getattr(self, "operations_cancelled", False):
            raise BrowserOperationCancelled()

        if self.page_loading:
            raise RuntimeError("A ChatGPT oldal nem töltődött be időben.")

    def _run_javascript(self, script: str, *, timeout_ms: int) -> Any:
        if getattr(self, "operations_cancelled", False):
            raise BrowserOperationCancelled()
        if not self._is_chatgpt_url(self.browser.url().toString()):
            raise RuntimeError("Az automatizálás csak a ChatGPT HTTPS oldalán használható.")

        # A második ellenőrzés a betöltés közbeni címváltást is kezeli. Az elkülönített
        # világ megakadályozza, hogy az oldal felülírja a natív alkalmazás JS függvényeit.
        allowed_hosts = json.dumps(list(CHATGPT_HOSTS))
        guarded_script = f"""
            if (window.top === window && location.protocol === 'https:' &&
                {allowed_hosts}.includes(location.hostname) &&
                (!location.port || location.port === '443') &&
                !location.username && !location.password) {{
                {script}
            }} else {{ null; }}
        """
        result_box: dict[str, Any] = {"done": False}
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        heartbeat_timer = QTimer()
        heartbeat_timer.setInterval(INTERACTION_HEARTBEAT_INTERVAL_MS)

        def touch_interaction_heartbeat() -> None:
            if self.browser_interaction_active:
                self._touch_browser_interaction_heartbeat()

            if self.clipboard_translation_in_progress:
                self._touch_clipboard_translation_heartbeat()

        def handle_result(result: Any) -> None:
            result_box["done"] = True
            result_box["value"] = result
            if loop.isRunning():
                loop.quit()

        def handle_timeout() -> None:
            if loop.isRunning():
                loop.quit()

        timer.timeout.connect(handle_timeout)
        cancel_signal = getattr(self, "browser_operations_cancelled", None)
        if cancel_signal is not None:
            cancel_signal.connect(handle_timeout)
        heartbeat_timer.timeout.connect(touch_interaction_heartbeat)
        timer.start(timeout_ms)
        heartbeat_timer.start()
        self.browser.page().runJavaScript(
            guarded_script, QWebEngineScript.ScriptWorldId.ApplicationWorld, handle_result
        )
        if not result_box["done"]:
            loop.exec()
        timer.stop()
        heartbeat_timer.stop()

        if cancel_signal is not None:
            cancel_signal.disconnect(handle_timeout)
        if getattr(self, "operations_cancelled", False):
            raise BrowserOperationCancelled()

        if not result_box["done"]:
            log_event("browser.javascript_timeout", level="ERROR",
                      request_id=getattr(self, "active_translation_request_id", None), timeout_ms=timeout_ms)
            raise RuntimeError("A JavaScript futtatása időtúllépéssel megszakadt.")

        if not self._is_chatgpt_url(self.browser.url().toString()):
            raise RuntimeError("Az oldal címe megváltozott, az automatizálás megszakadt.")

        return result_box.get("value")

    def _wait_with_events(self, delay_ms: int) -> None:
        if delay_ms <= 0:
            return

        loop = QEventLoop()
        QTimer.singleShot(delay_ms, loop.quit)
        loop.exec()

    def _read_clipboard_image_payload(self) -> dict[str, Any] | None:
        started_at = time.monotonic()
        image = self.clipboard.image()

        if image.isNull():
            return None

        if image.width() * image.height() > MAX_CLIPBOARD_IMAGE_PIXELS:
            log_event("capture.image_rejected", level="WARNING", reason="pixel_limit",
                      image_width=image.width(), image_height=image.height())
            self._set_live_status("A vágólap képe túl nagy (legfeljebb 40 millió képpont lehet).")
            return None

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)

        if not image.save(buffer, "PNG"):
            return None

        raw_bytes = bytes(buffer.data())
        if not raw_bytes:
            return None
        if len(raw_bytes) > MAX_CLIPBOARD_IMAGE_BYTES:
            log_event("capture.image_rejected", level="WARNING", reason="byte_limit", image_bytes=len(raw_bytes))
            self._set_live_status("A vágólap PNG képe túl nagy (legfeljebb 20 MiB lehet).")
            return None

        signature = hashlib.sha256(raw_bytes).hexdigest()
        encoded = base64.b64encode(raw_bytes).decode("ascii")
        log_event("capture.image_encoded", image_width=image.width(), image_height=image.height(),
                  request_id=getattr(self, "screen_clip_request_id", None),
                  image_bytes=len(raw_bytes), image_encoding_ms=round((time.monotonic() - started_at) * 1000))

        return {
            "imageDataUrl": f"data:image/png;base64,{encoded}",
            "imageMimeType": "image/png",
            "imageFilename": "snip.png",
            "imageSignature": signature,
            "imageBytes": raw_bytes,
        }

    def _current_clipboard_signature(self) -> str:
        payload = self._read_clipboard_image_payload()
        return str(payload["imageSignature"]) if payload else ""

    def _arm_screen_clip_hotkey(self) -> None:
        self.screen_clip_request_id = uuid.uuid4().hex
        self.screen_clip_hotkey_armed_until = time.monotonic() + SCREEN_CLIP_ARM_TIMEOUT_SECONDS
        log_event("capture.armed", request_id=self.screen_clip_request_id,
                  timeout_ms=int(SCREEN_CLIP_ARM_TIMEOUT_SECONDS * 1000))

    def _clear_screen_clip_hotkey_arm(self) -> None:
        if self.screen_clip_hotkey_armed_until > 0.0:
            log_event("capture.permission_cleared", request_id=getattr(self, "screen_clip_request_id", None))
        self.screen_clip_hotkey_armed_until = 0.0
        self.screen_clip_request_id = ""

    def _is_screen_clip_hotkey_armed(self) -> bool:
        if self.screen_clip_hotkey_armed_until <= 0.0:
            return False

        if time.monotonic() >= self.screen_clip_hotkey_armed_until:
            self.screen_clip_hotkey_armed_until = 0.0
            log_event("capture.permission_expired", level="WARNING", request_id=getattr(self, "screen_clip_request_id", None))
            self.screen_clip_request_id = ""
            self._set_live_status("A képkivágásra várás lejárt. Indíts új kivágást a saját gyorsgombbal.")
            return False

        return True

    def _focus_window(self) -> None:
        if self.isMinimized():
            self.showNormal()

        self.raise_()
        self.activateWindow()

    def _open_log_directory(self) -> None:
        directory = self.store.root_dir / "logs"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            os.startfile(str(directory))
            log_event("diagnostics.directory_opened")
        except OSError as error:
            log_exception("diagnostics.directory_open_failed", error)
            self._set_live_status("A naplómappa megnyitása nem sikerült.")

    def _record_runtime_diagnostics(self) -> None:
        now = time.monotonic()
        lag_ms = max(0, round((now - self.diagnostics_last_tick) * 1000) - 15000)
        self.diagnostics_last_tick = now
        try:
            renderer_pid = int(self.page.renderProcessPid())
        except RuntimeError:
            renderer_pid = 0
        log_event("runtime.snapshot", **resource_snapshot(renderer_pid=renderer_pid), lag_ms=lag_ms,
                  request_id=getattr(self, "active_translation_request_id", None),
                  loading=self.page_loading, busy=self.browser_interaction_active,
                  background=self.browser_background_mode, visible=self.isVisible(), minimized=self.isMinimized(),
                  pending_count=len(self.pending_clipboard_payload_queue) + int(self.pending_clipboard_payload is not None),
                  followup=bool(self.response_followup_progress_call_id))

    def _handle_renderer_terminated(self, status, exit_code: int) -> None:
        log_event("browser.renderer_terminated", level="ERROR", exit_code=exit_code,
                  state=status.name, request_id=getattr(self, "active_translation_request_id", None))
        MainWindow._invalidate_translation_result(self, uuid.uuid4().hex, "renderer_crash")
        self.automation_ready = False
        self._save_last_run_status("A ChatGPT böngészőfolyamata leállt. Nyisd meg újra a ChatGPT oldalt.")

    def _log_page_diagnostics(self, entries: Any, request_id: str) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries[:100]:
            if not isinstance(entry, dict) or not isinstance(entry.get("fields"), dict):
                continue
            event = entry.get("event")
            if isinstance(event, str) and event.isascii() and len(event) <= 80 and all(char.isalnum() or char in "._" for char in event):
                fields = {key: value for key, value in entry["fields"].items()
                          if isinstance(key, str) and key not in {"event", "request_id", "level"}}
                log_event(f"page.{event}", request_id=request_id, **fields)

    def _is_chatgpt_url(self, url: str) -> bool:
        if not url:
            return False

        try:
            parsed = urlparse(url)
            return (
                parsed.scheme == "https"
                and parsed.hostname in CHATGPT_HOSTS
                and parsed.port in (None, 443)
                and parsed.username is None
                and parsed.password is None
            )
        except ValueError:
            return False

    def _set_web_attribute(self, settings: QWebEngineSettings, attribute_name: str, value: bool) -> None:
        attribute = getattr(QWebEngineSettings.WebAttribute, attribute_name, None)

        if attribute is not None:
            settings.setAttribute(attribute, value)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationDisplayName(APP_NAME)
    window = MainWindow()
    window.show()
    return app.exec()
