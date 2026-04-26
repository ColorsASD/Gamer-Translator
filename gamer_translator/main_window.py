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
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QGuiApplication, QIcon, QKeySequence, QMouseEvent, QPixmap
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
    QKeySequenceEdit,
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
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from .defaults import APP_NAME, CHATGPT_HOSTS, CHATGPT_URL, DEFAULT_RESPONSE_TIMEOUT_MS, DEFAULT_SETTINGS, WINDOW_TITLE
from .ocr_service import OCRService
from .settings_store import AppSettings, LastRunStatus, SettingsStore

BROWSER_CONSOLE_DEBUG = os.environ.get("GAMER_TRANSLATOR_DEBUG_BROWSER", "").strip() == "1"
UI_FRAME_INTERVAL_MS = 20
UI_FRAME_INTERVAL_SECONDS = UI_FRAME_INTERVAL_MS / 1000.0
GAME_MODE_BACKGROUND_FRAME_INTERVAL_MS = 40
IDLE_FRAME_INTERVAL_MS = 60
BACKGROUND_IDLE_FRAME_INTERVAL_MS = 250
SUSPENDED_FRAME_INTERVAL_MS = 1200
BACKGROUND_TASK_EVENT_INTERVAL_SECONDS = 0.04
SCREEN_CLIP_ARM_TIMEOUT_SECONDS = 45.0
AUTOMATION_SELF_HEAL_TIMEOUT_BUFFER_MS = 70000
AUTOMATION_SCRIPT_VERSION = "2026-04-12-4"
INTERACTION_HEARTBEAT_INTERVAL_MS = 250
INTERACTION_STALE_RESET_SECONDS = 8.0
RESPONSE_FOLLOWUP_IDLE_TIMEOUT_SECONDS = 20.0
RESPONSE_FOLLOWUP_MAX_TIMEOUT_SECONDS = 120.0
RESPONSE_FOLLOWUP_MAX_ERROR_COUNT = 5

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
    WM_KEYDOWN = 0x0100
    WM_KEYUP = 0x0101
    WM_SYSKEYDOWN = 0x0104
    WM_SYSKEYUP = 0x0105
    LLKHF_INJECTED = 0x10
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

    HOTKEY_MODIFIER_ALIASES = {
        "CTRL": MOD_CONTROL,
        "CONTROL": MOD_CONTROL,
        "ALT": MOD_ALT,
        "SHIFT": MOD_SHIFT,
        "WIN": MOD_WIN,
        "WINDOWS": MOD_WIN,
        "META": MOD_WIN,
    }

    HOTKEY_KEYCODES = {
        "SPACE": 0x20,
        "TAB": VK_TAB,
        "ENTER": VK_RETURN,
        "RETURN": VK_RETURN,
        "ESC": 0x1B,
        "ESCAPE": 0x1B,
        "BACKSPACE": 0x08,
        "DELETE": 0x2E,
        "DEL": 0x2E,
        "INSERT": 0x2D,
        "INS": 0x2D,
        "HOME": 0x24,
        "END": 0x23,
        "PAGEUP": 0x21,
        "PGUP": 0x21,
        "PAGEDOWN": 0x22,
        "PGDOWN": 0x22,
        "LEFT": 0x25,
        "UP": 0x26,
        "RIGHT": 0x27,
        "DOWN": 0x28,
    }

    for offset in range(1, 25):
        HOTKEY_KEYCODES[f"F{offset}"] = 0x6F + offset

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
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


def parse_hotkey_definition(hotkey: str) -> tuple[int, int]:
    if sys.platform != "win32":
        raise ValueError("A globális gyorsbillentyű csak Windowson támogatott.")

    tokens = [part.strip().upper() for part in str(hotkey).replace("-", "+").split("+") if part.strip()]

    if not tokens:
        raise ValueError("Adj meg egy fő billentyűt, például: Alt+C vagy Alt+V")

    modifiers = 0

    for token in tokens[:-1]:
        modifier = HOTKEY_MODIFIER_ALIASES.get(token)

        if modifier is None:
            raise ValueError(f"Ismeretlen módosító billentyű: {token}")

        modifiers |= modifier

    key_token = tokens[-1]

    if len(key_token) == 1 and "A" <= key_token <= "Z":
        vk = ord(key_token)
    elif len(key_token) == 1 and "0" <= key_token <= "9":
        vk = ord(key_token)
    else:
        vk = HOTKEY_KEYCODES.get(key_token)

    if vk is None:
        raise ValueError(f"Nem támogatott gyorsbillentyű: {key_token}")

    return modifiers, vk


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

        scan_code = ord(character)
        inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0)))
        inputs.append(INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wVk=0, wScan=scan_code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)))

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
            dwExtraInfo=0,
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


def build_scan_code_input(virtual_key: int, *, key_up: bool = False) -> INPUT:
    scan_code = user32.MapVirtualKeyW(virtual_key, MAPVK_VK_TO_VSC)
    flags = KEYEVENTF_SCANCODE

    if key_up:
        flags |= KEYEVENTF_KEYUP

    if is_extended_virtual_key(virtual_key):
        flags |= KEYEVENTF_EXTENDEDKEY

    if scan_code == 0:
        return build_key_input(virtual_key, key_up=key_up)

    return INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )


def build_modified_key_inputs(modifier_virtual_key: int, key_virtual_key: int) -> list[INPUT]:
    return [
        build_key_input(modifier_virtual_key),
        build_key_input(key_virtual_key),
        build_key_input(key_virtual_key, key_up=True),
        build_key_input(modifier_virtual_key, key_up=True),
    ]


def build_character_inputs(character: str) -> list[INPUT]:
    if sys.platform != "win32":
        return []

    if character == "\r":
        return []

    if character == "\n":
        return build_virtual_key_inputs(VK_RETURN)

    if character == "\t":
        return build_virtual_key_inputs(VK_TAB)

    keyboard_layout = user32.GetKeyboardLayout(0)
    mapping = user32.VkKeyScanExW(ord(character), keyboard_layout)

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
        inputs.append(build_scan_code_input(modifier_key))

    inputs.append(build_scan_code_input(virtual_key))
    inputs.append(build_scan_code_input(virtual_key, key_up=True))

    for modifier_key in reversed(modifier_keys):
        inputs.append(build_scan_code_input(modifier_key, key_up=True))

    return inputs


class BrowserPage(QWebEnginePage):
    def javaScriptConsoleMessage(
        self,
        level: QWebEnginePage.JavaScriptConsoleMessageLevel,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:
        if BROWSER_CONSOLE_DEBUG:
            print(f"[browser:{level.name}] {source_id}:{line_number} {message}")


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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(1080, 720)

        self.store = SettingsStore()
        self.ocr_service = OCRService()
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
        self.registered_hotkeys: dict[str, tuple[int, int]] = {}
        self.hotkey_errors: dict[str, str] = {}
        self.hotkey_pressed_states: dict[str, bool] = {}
        self.registered_hotkey_primary_keys: set[int] = set()
        self.keyboard_hook_handle = None
        self.keyboard_hook_callback = None
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

        self.clipboard = QGuiApplication.clipboard()
        self.last_seen_image_signature = self._current_clipboard_signature()
        self.pending_clipboard_payload: dict[str, Any] | None = None
        self.pending_clipboard_check_requested = False
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

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1680, 980)
        self._apply_window_icon()
        self._build_tray_icon()
        self._sync_window_buttons()
        app = QApplication.instance()

        if app is not None:
            app.applicationStateChanged.connect(self._handle_application_state_changed)

        QTimer.singleShot(0, self._register_hotkeys)
        QTimer.singleShot(0, self.open_chatgpt)
        QTimer.singleShot(0, self._refresh_system_keep_awake)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.exit_requested and self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self._hide_to_tray(show_message=True)
            return

        self.store.save_settings(self._read_settings_from_form())
        self._unregister_hotkeys()
        self._uninstall_keyboard_hook()
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

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and self.drawer_open:
            self.close_drawer()
            event.accept()
            return

        super().keyPressEvent(event)

    def _build_browser(self) -> None:
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

        browser_settings = self.browser.settings()
        self._set_web_attribute(browser_settings, "JavascriptEnabled", True)
        self._set_web_attribute(browser_settings, "LocalStorageEnabled", True)
        self._set_web_attribute(browser_settings, "JavascriptCanAccessClipboard", True)
        self._set_web_attribute(browser_settings, "JavascriptCanPaste", True)
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

        overlay_opacity_row = QWidget()
        overlay_opacity_layout = QHBoxLayout(overlay_opacity_row)
        overlay_opacity_layout.setContentsMargins(0, 0, 0, 0)
        overlay_opacity_layout.setSpacing(10)
        overlay_opacity_layout.addWidget(self.overlay_opacity_slider, 1)
        overlay_opacity_layout.addWidget(self.overlay_opacity_value_label)

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
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
        self.top_status_label = QLabel("Indulásra kész.")
        self.top_status_label.setObjectName("topStatusLabel")
        self.top_status_label.setWordWrap(False)

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
            QLineEdit, QKeySequenceEdit, QPlainTextEdit, QSpinBox {
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

    def _build_hotkey_edit(self) -> QKeySequenceEdit:
        hotkey_edit = QKeySequenceEdit()

        if hasattr(hotkey_edit, "setMaximumSequenceLength"):
            hotkey_edit.setMaximumSequenceLength(1)

        hotkey_edit.setToolTip("Kattints ide, majd nyomd le a kívánt billentyűkombinációt.")
        return hotkey_edit

    def _set_hotkey_value(self, hotkey_edit: QKeySequenceEdit, value: str) -> None:
        hotkey_edit.setKeySequence(QKeySequence(value))

    def _read_hotkey_value(self, hotkey_edit: QKeySequenceEdit, fallback: str) -> str:
        hotkey_value = hotkey_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText).strip()
        return hotkey_value or fallback

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
        interaction_active = self.browser_interaction_active or self.page_loading or self.clipboard_translation_in_progress

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
        )
        background_keepalive_active = (
            self.browser_background_mode
            and self._is_window_hidden_for_tray()
            and self.settings.keep_chatgpt_in_background
            and self.settings.monitoring_enabled
        )
        should_render_page = visible_main_window_render or background_interaction_active or background_keepalive_active
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
        except RuntimeError:
            self.browser_keepalive_failures += 1

            if self.browser_keepalive_failures >= 2 and not self.page_loading:
                self.browser_keepalive_failures = 0
                self.automation_ready = False
                self._set_live_status("A ChatGPT oldal felébresztése miatt újratöltés történt.")
                self.browser.reload()

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
            rendered_arguments = ", ".join(self._powershell_literal(argument) for argument in arguments)
            script_lines.append(f"$StartProcessArgs.ArgumentList = @({rendered_arguments})")

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
        self.page_loading = True
        self.automation_ready = False
        self.current_url_label.setText(self.browser.url().toString())
        self._set_live_status("A ChatGPT oldal betöltése folyamatban.")
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def _handle_load_finished(self, ok: bool) -> None:
        self.page_loading = False
        self.current_url_label.setText(self.browser.url().toString())

        if not ok:
            self._set_live_status("A böngészőoldal nem töltődött be rendesen.")
            QTimer.singleShot(0, self._sync_browser_runtime_state)
            return

        try:
            self._ensure_automation_ready()
            self._set_live_status("A ChatGPT oldal betöltve.")
        except RuntimeError as error:
            self._set_live_status(str(error))
        finally:
            QTimer.singleShot(0, self._sync_browser_runtime_state)

    def save_settings(self) -> None:
        previous_settings = self.settings
        self.settings = self._read_settings_from_form()
        self.store.save_settings(self.settings)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        if self.settings.game_mode_enabled:
            self._hide_translation_overlay()
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
        previous_settings = self.settings
        self.settings = AppSettings.from_dict(DEFAULT_SETTINGS)
        self._apply_settings_to_form(self.settings)
        self.store.save_settings(self.settings)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        if self.settings.game_mode_enabled:
            self._hide_translation_overlay()
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
        self.settings = self._read_settings_from_form()
        self._begin_browser_interaction()

        try:
            self._ensure_chatgpt_page_loaded(reload_if_open=True)
            self._ensure_automation_ready()
        except Exception as error:  # noqa: BLE001
            message = str(error)
            self._save_last_run_status(message)
            self._set_live_status(message)

            if show_error_dialog:
                QMessageBox.warning(self, APP_NAME, message)
        finally:
            self._end_browser_interaction()

    def send_prompt_now(self) -> None:
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
        except Exception as error:  # noqa: BLE001
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
            QMessageBox.warning(self, APP_NAME, str(error))
        finally:
            self._end_browser_interaction()

    def _ensure_chatgpt_page_loaded(self, *, reload_if_open: bool) -> None:
        current_url = self.browser.url().toString().strip()
        target_url = CHATGPT_URL

        if not self._is_chatgpt_url(current_url):
            self.browser.load(QUrl(target_url))
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)
        elif self.page_loading:
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)
        elif reload_if_open:
            self._set_live_status("A ChatGPT oldal újratöltése folyamatban.")
            self.browser.reload()
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)

    def _poll_clipboard(self) -> None:
        if self.clipboard_translation_in_progress:
            return

        payload = self._read_clipboard_image_payload()
        screen_clip_hotkey_armed = self._is_screen_clip_hotkey_armed()

        if not payload:
            return

        signature = str(payload["imageSignature"])

        if screen_clip_hotkey_armed and signature:
            self._clear_screen_clip_hotkey_arm()
            self.last_seen_image_signature = signature
            self._process_clipboard_translation(payload)
            return

        if not signature or signature == self.last_seen_image_signature:
            return

        self.last_seen_image_signature = signature
        self._process_clipboard_translation(payload)

    def _handle_clipboard_changed(self, mode) -> None:  # type: ignore[override]
        if mode != self.clipboard.Mode.Clipboard:
            return

        if self.clipboard_translation_in_progress:
            self.pending_clipboard_check_requested = True
            pending_payload = self._read_clipboard_image_payload()

            if pending_payload:
                self.pending_clipboard_payload = pending_payload

                if self._is_screen_clip_hotkey_armed():
                    self._clear_screen_clip_hotkey_arm()

            return

        self.clipboard_debounce_timer.start()

    def _process_clipboard_translation(self, payload: dict[str, Any]) -> None:
        self.settings = self._read_settings_from_form()

        if not self.settings.monitoring_enabled:
            self._save_last_run_status("A figyelés ki van kapcsolva, ezért a kép kihagyva.")
            return

        if self.clipboard_translation_in_progress:
            self._save_last_run_status("Már fut egy képbeküldés, ezt az új képet most kihagyom.")
            return

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

            if delivery_payload.get("copyResponseToClipboard"):
                progress_handler, progress_state = self._build_response_progress_handler(
                    copy_to_clipboard=True,
                    show_overlay=True,
                    play_sound=True,
                )

            result = self._execute_delivery(delivery_payload, progress_handler=progress_handler)
            follow_up_progress_call_id = str(result.get("followUpProgressCallId") or "").strip()

            if follow_up_progress_call_id:
                self._start_response_followup_polling(follow_up_progress_call_id, progress_handler)

            translated_text = str(result.get("assistantResponseText") or "").strip()

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
                    )
                self._save_last_run_status(f"A fordítás a vágólapra másolva és memóriába mentve. Gyorsbillentyű: {self.settings.type_out_hotkey}")
                return

            if translated_text:
                self._store_translation_result(
                    translated_text,
                    copy_to_clipboard=False,
                    show_overlay=True,
                    play_sound=False,
                )
            else:
                self._hide_translation_overlay()

            self._save_last_run_status(success_status_message)
        except Exception as error:  # noqa: BLE001
            self._hide_translation_overlay()
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
        finally:
            self.clipboard_translation_in_progress = False
            self.clipboard_translation_heartbeat_monotonic = 0.0
            self._end_browser_interaction()

            pending_payload = self.pending_clipboard_payload
            self.pending_clipboard_payload = None
            pending_check_requested = self.pending_clipboard_check_requested
            self.pending_clipboard_check_requested = False

            if pending_payload:
                pending_signature = str(pending_payload.get("imageSignature") or "")

                if pending_signature and pending_signature != self.last_seen_image_signature:
                    self.last_seen_image_signature = pending_signature
                    QTimer.singleShot(
                        0,
                        lambda queued_payload=pending_payload: self._process_clipboard_translation(queued_payload),
                    )
                return

            if pending_check_requested:
                self.clipboard_debounce_timer.start()

    def _build_translation_delivery_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
        if self.settings.ocr_text_from_clipboard_image:
            self._set_live_status("Szöveg kiolvasása képről folyamatban.")
            extracted_text_candidates = self._run_in_background_with_events(
                lambda: self.ocr_service.extract_text_candidates(
                    bytes(payload.get("imageBytes") or b""),
                    limit=5,
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
    ) -> tuple[Callable[[dict[str, Any]], None], dict[str, Any]]:
        state = {
            "last_text": "",
            "notified": False,
        }

        def handle_progress(progress: dict[str, Any]) -> None:
            if str(progress.get("kind") or "") != "assistant_response":
                return

            translated_text = str(progress.get("text") or "").strip()

            if not translated_text or translated_text == str(state["last_text"]):
                return

            self._store_translation_result(
                translated_text,
                copy_to_clipboard=copy_to_clipboard,
                show_overlay=show_overlay,
                play_sound=play_sound and not bool(state["notified"]),
            )
            state["last_text"] = translated_text
            state["notified"] = True

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
        self.response_followup_timer.start()

    def _stop_response_followup_polling(self, *, stop_remote: bool = True) -> None:
        current_progress_call_id = str(self.response_followup_progress_call_id or "").strip()

        self.response_followup_timer.stop()
        self.response_followup_progress_call_id = ""
        self.response_followup_last_sequence = 0
        self.response_followup_handler = None
        self.response_followup_started_monotonic = 0.0
        self.response_followup_last_activity_monotonic = 0.0
        self.response_followup_error_count = 0

        if not current_progress_call_id:
            return

        try:
            self._run_javascript(
                f"""
                    (() => {{
                      if ({str(stop_remote).lower()} && typeof window.__gamerTranslatorStopResponseFollowUp === "function") {{
                        window.__gamerTranslatorStopResponseFollowUp("{current_progress_call_id}", {{ emitDone: false }});
                      }}
                      const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                      delete progressBucket["{current_progress_call_id}"];
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

        if (
            self.response_followup_started_monotonic > 0.0
            and now - self.response_followup_started_monotonic >= RESPONSE_FOLLOWUP_MAX_TIMEOUT_SECONDS
        ):
            self._stop_response_followup_polling()
            return

        if (
            self.response_followup_last_activity_monotonic > 0.0
            and now - self.response_followup_last_activity_monotonic >= RESPONSE_FOLLOWUP_IDLE_TIMEOUT_SECONDS
        ):
            self._stop_response_followup_polling()
            return

        try:
            progress_json = self._run_javascript(
                f"""
                    (() => {{
                      const progressBucket = window.__gamerTranslatorProgress || Object.create(null);
                      return progressBucket["{progress_call_id}"] ?? null;
                    }})()
                """,
                timeout_ms=3000,
            )
        except Exception:
            self.response_followup_error_count += 1

            if self.response_followup_error_count >= RESPONSE_FOLLOWUP_MAX_ERROR_COUNT:
                self._stop_response_followup_polling()

            return

        if not isinstance(progress_json, str) or not progress_json:
            return

        try:
            progress = json.loads(progress_json)
        except Exception:
            return

        progress_sequence = int(progress.get("seq") or 0)

        if progress_sequence <= self.response_followup_last_sequence:
            return

        self.response_followup_last_sequence = progress_sequence
        self.response_followup_last_activity_monotonic = time.monotonic()
        self.response_followup_error_count = 0

        if bool(progress.get("done")):
            self._stop_response_followup_polling(stop_remote=False)
            return

        progress_handler = self.response_followup_handler

        if progress_handler is None:
            return

        try:
            progress_handler(progress)
        except Exception:
            pass

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
            )
            result = self._execute_delivery(
                {
                    "prompt": self._build_quick_chat_translation_prompt(cleaned_prompt),
                    "imageDataUrl": "",
                    "imageMimeType": "",
                    "imageFilename": "",
                    "autoSubmit": True,
                    "copyResponseToClipboard": True,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": DEFAULT_RESPONSE_TIMEOUT_MS,
                },
                progress_handler=progress_handler,
            )
            follow_up_progress_call_id = str(result.get("followUpProgressCallId") or "").strip()

            if follow_up_progress_call_id:
                self._start_response_followup_polling(follow_up_progress_call_id, progress_handler)

            translated_text = str(result.get("assistantResponseText") or "").strip()

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
                )
            self._save_last_run_status(
                f"A gyors chat fordítása a vágólapra másolva és memóriába mentve. Gyorsbillentyű: {self.settings.type_out_hotkey}"
            )
        except Exception as error:  # noqa: BLE001
            self._hide_translation_overlay()
            self._save_last_run_status(str(error))
        finally:
            self._end_browser_interaction()

    def _store_translation_result(
        self,
        translated_text: str,
        *,
        copy_to_clipboard: bool,
        show_overlay: bool,
        play_sound: bool,
    ) -> None:
        text_changed = translated_text != self.last_translated_text
        self.last_translated_text = translated_text

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

                QGuiApplication.processEvents()
                time.sleep(BACKGROUND_TASK_EVENT_INTERVAL_SECONDS)

        self.background_executor.shutdown(wait=True, cancel_futures=True)

    def _run_in_background_with_events(self, task: Callable[[], Any], *, progress_message: str | None = None) -> Any:
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

                QGuiApplication.processEvents()
                time.sleep(BACKGROUND_TASK_EVENT_INTERVAL_SECONDS)

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
        if self.settings.game_mode_enabled:
            return False

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
        self.browser_interaction_active = True
        self._touch_browser_interaction_heartbeat()
        self._sync_browser_host_mode()
        self._sync_browser_runtime_state()

    def _end_browser_interaction(self) -> None:
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
        if sys.platform != "win32":
            self.hotkey_errors = {
                "type_out": "A gyorsbillentyűk csak Windowson érhetők el.",
                "screen_clip": "A gyorsbillentyűk csak Windowson érhetők el.",
                "quick_chat": "A gyorsbillentyűk csak Windowson érhetők el.",
            }
            return

        self._unregister_hotkeys()
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
        self.hotkey_pressed_states = {action: False for action in self.registered_hotkeys}
        self.registered_hotkey_primary_keys = {hotkey_key for _hotkey_modifiers, hotkey_key in self.registered_hotkeys.values()}
        self._update_keyboard_hook_state()

    def _unregister_hotkeys(self) -> None:
        if sys.platform != "win32":
            return

        self.registered_hotkeys = {}
        self.hotkey_pressed_states = {}
        self.registered_hotkey_primary_keys = set()
        self._update_keyboard_hook_state()

    def _update_keyboard_hook_state(self) -> None:
        if sys.platform != "win32":
            return

        if self.registered_hotkeys:
            self._install_keyboard_hook()
            return

        self._uninstall_keyboard_hook()

    def _install_keyboard_hook(self) -> None:
        if sys.platform != "win32" or self.keyboard_hook_handle is not None:
            return

        module_handle = kernel32.GetModuleHandleW(None)
        self.keyboard_hook_callback = HOOKPROC(self._keyboard_hook_proc)
        self.keyboard_hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.keyboard_hook_callback, module_handle, 0)

        if not self.keyboard_hook_handle:
            error_code = int(kernel32.GetLastError())
            suffix = f" Windows hibakód: {error_code}" if error_code else ""
            error_message = f"A gyorsbillentyű-hook telepítése nem sikerült.{suffix}"

            for action in self.registered_hotkeys:
                self.hotkey_errors[action] = error_message

            self.registered_hotkeys = {}
            self.hotkey_pressed_states = {}
            self.registered_hotkey_primary_keys = set()
            self.keyboard_hook_callback = None

    def _uninstall_keyboard_hook(self) -> None:
        if sys.platform != "win32":
            return

        if self.keyboard_hook_handle is not None:
            user32.UnhookWindowsHookEx(self.keyboard_hook_handle)
            self.keyboard_hook_handle = None

        self.keyboard_hook_callback = None

    def _keyboard_hook_proc(self, n_code: int, w_param, l_param):
        if n_code != HC_ACTION or not self.registered_hotkeys:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        message = int(w_param)
        key_data = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk_code = int(key_data.vkCode)

        if key_data.flags & LLKHF_INJECTED:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        if vk_code not in self.registered_hotkey_primary_keys:
            return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

        if message in (WM_KEYDOWN, WM_SYSKEYDOWN) and self._handle_hotkey_keydown(vk_code):
            return 1

        if message in (WM_KEYUP, WM_SYSKEYUP) and self._handle_hotkey_keyup(vk_code):
            return 1

        return user32.CallNextHookEx(self.keyboard_hook_handle, n_code, w_param, l_param)

    def _handle_hotkey_keydown(self, vk_code: int) -> bool:
        for action, (hotkey_modifiers, hotkey_key) in self.registered_hotkeys.items():
            if hotkey_key != vk_code:
                continue

            if not self._current_modifiers_match(hotkey_modifiers):
                continue

            if not self.hotkey_pressed_states.get(action, False):
                self.hotkey_pressed_states[action] = True
                QTimer.singleShot(0, lambda action_name=action: self._trigger_hotkey_action(action_name))

            return True

        return False

    def _handle_hotkey_keyup(self, vk_code: int) -> bool:
        for action, (_hotkey_modifiers, hotkey_key) in self.registered_hotkeys.items():
            if hotkey_key != vk_code:
                continue

            if self.hotkey_pressed_states.get(action, False):
                self.hotkey_pressed_states[action] = False
                return True

        return False

    def _trigger_hotkey_action(self, action: str) -> None:
        if action == "type_out":
            self._trigger_type_out_hotkey()
            return

        if action == "screen_clip":
            self._trigger_screen_clip_hotkey()
            return

        if action == "quick_chat":
            self._trigger_quick_chat_hotkey()
            return

    def _current_modifiers_match(self, modifiers: int) -> bool:
        if sys.platform != "win32":
            return False

        ctrl_down = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
        alt_down = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
        shift_down = bool(user32.GetAsyncKeyState(VK_SHIFT) & 0x8000)
        win_down = bool((user32.GetAsyncKeyState(VK_LWIN) | user32.GetAsyncKeyState(VK_RWIN)) & 0x8000)

        return (
            ctrl_down == bool(modifiers & MOD_CONTROL)
            and alt_down == bool(modifiers & MOD_ALT)
            and shift_down == bool(modifiers & MOD_SHIFT)
            and win_down == bool(modifiers & MOD_WIN)
        )

    def _hotkey_status_message(self, prefix: str) -> str:
        if not self.hotkey_errors:
            return prefix

        return f"{prefix} {' | '.join(self.hotkey_errors.values())}"

    def _trigger_type_out_hotkey(self) -> None:
        if self.hotkey_errors.get("type_out"):
            self._set_live_status(self.hotkey_errors["type_out"])
            return

        if not self.last_translated_text:
            self._set_live_status("Nincs memóriában eltárolt fordítás a begépeléshez.")
            return

        if self._wait_for_modifier_release():
            self._type_cached_text_via_hotkey()
            self._set_live_status(f"A mentett fordítás begépelve: {self.settings.type_out_hotkey}")

    def _trigger_screen_clip_hotkey(self) -> None:
        if self.hotkey_errors.get("screen_clip"):
            self._set_live_status(self.hotkey_errors["screen_clip"])
            return

        if sys.platform != "win32":
            self._set_live_status("A képkivágási gyorsbillentyű csak Windowson érhető el.")
            return

        self._arm_screen_clip_hotkey()

        try:
            os.startfile("ms-screenclip:")
            self._set_live_status(f"A Windows képkivágó megnyitva: {self.settings.screen_clip_hotkey}")
        except OSError as error:
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
        self._set_live_status(f"A gyors chat overlay megnyitva: {self.settings.quick_chat_hotkey}")

    def _wait_for_modifier_release(self) -> bool:
        if sys.platform != "win32":
            return False

        modifier_keys = (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)
        deadline = time.monotonic() + 1.2

        while time.monotonic() < deadline:
            if not any(user32.GetAsyncKeyState(key_code) & 0x8000 for key_code in modifier_keys):
                return True

            QGuiApplication.processEvents()
            time.sleep(0.02)

        return True

    def _type_cached_text_via_hotkey(self) -> None:
        if sys.platform != "win32" or not self.last_translated_text:
            return

        for character in self.last_translated_text:
            inputs = build_character_inputs(character)

            if not inputs:
                continue

            input_array = (INPUT * len(inputs))(*inputs)
            user32.SendInput(len(inputs), input_array, ctypes.sizeof(INPUT))
            time.sleep(0.012)

    def _apply_settings_to_form(self, settings: AppSettings) -> None:
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
            monitoring_enabled=True,
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
        progress_call_id = f"{call_id}-progress"
        payload_with_progress = dict(payload)
        payload_with_progress["progressCallId"] = progress_call_id
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

                          if (resultValue !== undefined) {{
                            delete resultBucket["{call_id}"];
                            delete progressBucket["{progress_call_id}"];
                          }}

                          return JSON.stringify({{
                            result: resultValue === undefined ? null : resultValue,
                            progress: progressValue
                          }});
                        }})()
                    """,
                    timeout_ms=5000,
                )

                state = json.loads(state_json) if isinstance(state_json, str) and state_json else {}
                progress_json = state.get("progress")

                if isinstance(progress_json, str) and progress_json and progress_handler is not None:
                    progress = json.loads(progress_json)
                    progress_sequence = int(progress.get("seq") or 0)

                    if progress_sequence > last_progress_sequence:
                        last_progress_sequence = progress_sequence

                        try:
                            progress_handler(progress)
                        except Exception:
                            pass

                result_json = state.get("result")

                if isinstance(result_json, str) and result_json:
                    result = json.loads(result_json)

                    if result.get("ok") is False:
                        raise RuntimeError(result.get("error") or "Az oldaloldali művelet hibával tért vissza.")

                    return result

                self._wait_with_events(UI_FRAME_INTERVAL_MS)

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
                          return true;
                        }})()
                    """,
                    timeout_ms=3000,
                )
            except Exception:
                pass

    def _wait_for_page_load(self, timeout_ms: int) -> None:
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

        if self.page_loading:
            raise RuntimeError("A ChatGPT oldal nem töltődött be időben.")

    def _run_javascript(self, script: str, *, timeout_ms: int) -> Any:
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
        heartbeat_timer.timeout.connect(touch_interaction_heartbeat)
        timer.start(timeout_ms)
        heartbeat_timer.start()
        self.browser.page().runJavaScript(script, handle_result)
        loop.exec()
        timer.stop()
        heartbeat_timer.stop()

        if not result_box["done"]:
            raise RuntimeError("A JavaScript futtatása időtúllépéssel megszakadt.")

        return result_box.get("value")

    def _wait_with_events(self, delay_ms: int) -> None:
        if delay_ms <= 0:
            return

        loop = QEventLoop()
        QTimer.singleShot(delay_ms, loop.quit)
        loop.exec()

    def _read_clipboard_image_payload(self) -> dict[str, Any] | None:
        image = self.clipboard.image()

        if image.isNull():
            return None

        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)

        if not image.save(buffer, "PNG"):
            return None

        raw_bytes = bytes(buffer.data())
        if not raw_bytes:
            return None

        signature = hashlib.sha256(raw_bytes).hexdigest()
        encoded = base64.b64encode(raw_bytes).decode("ascii")

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
        self.screen_clip_hotkey_armed_until = time.monotonic() + SCREEN_CLIP_ARM_TIMEOUT_SECONDS

    def _clear_screen_clip_hotkey_arm(self) -> None:
        self.screen_clip_hotkey_armed_until = 0.0

    def _is_screen_clip_hotkey_armed(self) -> bool:
        if self.screen_clip_hotkey_armed_until <= 0.0:
            return False

        if time.monotonic() >= self.screen_clip_hotkey_armed_until:
            self.screen_clip_hotkey_armed_until = 0.0
            return False

        return True

    def _focus_window(self) -> None:
        if self.isMinimized():
            self.showNormal()

        self.raise_()
        self.activateWindow()

    def _is_chatgpt_url(self, url: str) -> bool:
        if not url:
            return False

        host = urlparse(url).hostname or ""
        return any(host == allowed_host for allowed_host in CHATGPT_HOSTS)

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
