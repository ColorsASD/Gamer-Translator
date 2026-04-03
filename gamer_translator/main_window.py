from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import sys
import time
import uuid
import winsound
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import QBuffer, QEasingCurve, QEvent, QEventLoop, QIODevice, QPoint, Property, QPropertyAnimation, QTimer, Qt, QUrl, Signal
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

from .defaults import APP_NAME, CHATGPT_HOSTS, CHATGPT_URL, DEFAULT_SETTINGS, WINDOW_TITLE
from .settings_store import AppSettings, LastRunStatus, SettingsStore

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
    VK_CONTROL = 0x11
    VK_MENU = 0x12
    VK_SHIFT = 0x10
    VK_LWIN = 0x5B
    VK_RWIN = 0x5C
    VK_RETURN = 0x0D
    VK_TAB = 0x09
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
    dwmapi.DwmSetWindowAttribute.argtypes = (wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE


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
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0013)

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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(1080, 720)

        self.store = SettingsStore()
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
        self.keyboard_hook_handle = None
        self.keyboard_hook_callback = None
        self.native_window_theme_applied = False
        self.exit_requested = False
        self.window_was_maximized_before_hide = False
        self.tray_message_shown = False
        self.browser_background_mode = False
        self.tray_icon: QSystemTrayIcon | None = None
        self.tray_toggle_action: QAction | None = None
        self.browser_background_host = BrowserBackgroundHost()
        self.translation_overlay = TranslationOverlay()

        self._build_browser()
        self._build_ui()
        self._apply_styles()
        self._apply_settings_to_form(self.settings)
        self._render_last_run_status(self.last_run_status)
        self._set_live_status("Indulásra kész.")
        self._layout_overlay_widgets()

        self.clipboard = QGuiApplication.clipboard()
        self.last_seen_image_signature = self._current_clipboard_signature()
        self.clipboard_debounce_timer = QTimer(self)
        self.clipboard_debounce_timer.setSingleShot(True)
        self.clipboard_debounce_timer.setInterval(120)
        self.clipboard_debounce_timer.timeout.connect(self._poll_clipboard)
        self.clipboard.changed.connect(self._handle_clipboard_changed)

        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1680, 980)
        self._apply_window_icon()
        self._build_tray_icon()
        self._sync_window_buttons()
        self._install_keyboard_hook()
        QTimer.singleShot(0, self._register_hotkeys)
        QTimer.singleShot(0, self.open_chatgpt)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self.exit_requested and self.tray_icon is not None and self.tray_icon.isVisible():
            event.ignore()
            self._hide_to_tray(show_message=True)
            return

        self.store.save_settings(self._read_settings_from_form())
        self._unregister_hotkeys()
        self._uninstall_keyboard_hook()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        self.browser_background_host.close()
        self.translation_overlay.hide()
        super().closeEvent(event)

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)

        if not self.native_window_theme_applied:
            self._apply_native_window_theme()
            self.native_window_theme_applied = True

        if self.isVisible() and not self.isMinimized():
            self._deactivate_background_browser_host()

        self._sync_tray_toggle_action()
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        self._sync_tray_toggle_action()
        QTimer.singleShot(0, self._sync_browser_runtime_state)

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._layout_overlay_widgets()

    def changeEvent(self, event) -> None:  # type: ignore[override]
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_window_buttons()
            self._sync_tray_toggle_action()

            if self.isMinimized():
                self._activate_background_browser_host()
            elif self.isVisible():
                self._deactivate_background_browser_host()

            QTimer.singleShot(0, self._sync_browser_runtime_state)

        super().changeEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if event.key() == Qt.Key.Key_Escape and self.drawer_open:
            self.close_drawer()
            event.accept()
            return

        super().keyPressEvent(event)

    def _build_browser(self) -> None:
        self.profile = QWebEngineProfile(APP_NAME, self)
        self.profile.setCachePath(str(self.store.browser_dir / "cache"))
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
        self._set_web_attribute(browser_settings, "ScrollAnimatorEnabled", True)
        self._set_web_attribute(browser_settings, "FullScreenSupportEnabled", True)

    def _build_ui(self) -> None:
        self.monitoring_enabled = QCheckBox("A program legyen aktív")
        self.chatgpt_url = QLineEdit()
        self.prompt_template = QPlainTextEdit()
        self.prompt_template.setPlaceholderText("Ide kerül a kézi prompt.")
        self.prompt_template.setMinimumHeight(180)
        self.copy_response_to_clipboard = QCheckBox("A ChatGPT válasza kerüljön a vágólapra")
        self.type_out_hotkey_enabled = QCheckBox("A memóriába mentett fordítás legyen begépelhető gyorsbillentyűvel")
        self.type_out_hotkey = self._build_hotkey_edit()
        self.screen_clip_hotkey_enabled = QCheckBox("A Windows képkivágó nyíljon meg gyorsbillentyűvel")
        self.screen_clip_hotkey = self._build_hotkey_edit()
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
        self.page_load_delay_ms = self._build_spin_box()
        self.page_ready_timeout_ms = self._build_spin_box(maximum=120000, step=1000)
        self.before_submit_delay_ms = self._build_spin_box()
        self.after_attach_delay_ms = self._build_spin_box()

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
        form_layout.addRow("", self.screen_clip_hotkey_enabled)
        form_layout.addRow("Képkivágási gyorsbillentyű", self.screen_clip_hotkey)
        form_layout.addRow("", self.type_out_hotkey_enabled)
        form_layout.addRow("Begépelési gyorsbillentyű", self.type_out_hotkey)
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

        self.open_chatgpt_button.clicked.connect(self.open_chatgpt)
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

    def _sync_browser_runtime_state(self) -> None:
        if not hasattr(self, "browser"):
            return

        page = self.browser.page()

        try:
            page.setLifecycleState(QWebEnginePage.LifecycleState.Active)

            if self._is_window_hidden_for_tray():
                page.setVisible(True)
            elif self.browser.isVisible():
                page.setVisible(True)
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
        self._activate_background_browser_host()
        self.hide()
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

        self._deactivate_background_browser_host()
        self.raise_()
        self.activateWindow()
        self._sync_window_buttons()
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

    def _handle_load_finished(self, ok: bool) -> None:
        self.page_loading = False
        self.current_url_label.setText(self.browser.url().toString())

        if not ok:
            self._set_live_status("A böngészőoldal nem töltődött be rendesen.")
            return

        try:
            self._ensure_automation_ready()
            self._set_live_status("A ChatGPT oldal betöltve.")
        except RuntimeError as error:
            self._set_live_status(str(error))

    def save_settings(self) -> None:
        self.settings = self._read_settings_from_form()
        self.store.save_settings(self.settings)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        self._register_hotkeys()
        self._set_live_status(self._hotkey_status_message("Beállítások elmentve."))

    def reset_defaults(self) -> None:
        self.settings = AppSettings.from_dict(DEFAULT_SETTINGS)
        self._apply_settings_to_form(self.settings)
        self.store.save_settings(self.settings)
        self.translation_overlay.set_overlay_opacity_percent(self.settings.overlay_opacity_percent)
        self._register_hotkeys()
        self._set_live_status(self._hotkey_status_message("Az alapértékek vissza lettek állítva."))

    def toggle_drawer(self) -> None:
        self._set_drawer_open(not self.drawer_open)

    def close_drawer(self) -> None:
        self._set_drawer_open(False)

    def open_chatgpt(self) -> None:
        self.settings = self._read_settings_from_form()
        self._ensure_chatgpt_page_loaded(reload_if_open=True)
        self._ensure_automation_ready()

    def send_prompt_now(self) -> None:
        self.settings = self._read_settings_from_form()
        self._set_live_status("Prompt küldése folyamatban.")

        try:
            self._ensure_chatgpt_page_loaded(reload_if_open=False)
            self._ensure_automation_ready()
            self._wait_with_events(self.settings.page_load_delay_ms)
            self._execute_delivery(
                {
                    "prompt": self.settings.prompt_template.strip(),
                    "imageDataUrl": "",
                    "imageMimeType": "",
                    "imageFilename": "",
                    "autoSubmit": True,
                    "copyResponseToClipboard": False,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": 45000,
                    "beforeSubmitDelayMs": self.settings.before_submit_delay_ms,
                    "afterAttachDelayMs": self.settings.after_attach_delay_ms,
                }
            )
            self._save_last_run_status("A kézi prompt elküldve a ChatGPT-nek.")
            self._set_live_status("A prompt elküldve.")
        except Exception as error:  # noqa: BLE001
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
            QMessageBox.warning(self, APP_NAME, str(error))

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

        if not payload:
            return

        signature = str(payload["imageSignature"])

        if not signature or signature == self.last_seen_image_signature:
            return

        self.last_seen_image_signature = signature
        self._process_clipboard_translation(payload)

    def _handle_clipboard_changed(self, mode) -> None:  # type: ignore[override]
        if mode != self.clipboard.Mode.Clipboard:
            return

        if self.clipboard_translation_in_progress:
            return

        self.clipboard_debounce_timer.start()

    def _process_clipboard_translation(self, payload: dict[str, str]) -> None:
        self.settings = self._read_settings_from_form()

        if not self.settings.monitoring_enabled:
            self._save_last_run_status("A figyelés ki van kapcsolva, ezért a kép kihagyva.")
            return

        if self.clipboard_translation_in_progress:
            self._save_last_run_status("Már fut egy képbeküldés, ezt az új képet most kihagyom.")
            return

        self.clipboard_translation_in_progress = True

        try:
            self._save_last_run_status("Új kép érkezett a vágólapra.")
            self._show_loading_overlay()
            self._ensure_chatgpt_page_loaded(reload_if_open=False)
            self._ensure_automation_ready()
            self._wait_with_events(self.settings.page_load_delay_ms)

            result = self._execute_delivery(
                {
                    "prompt": "",
                    "imageDataUrl": payload["imageDataUrl"],
                    "imageMimeType": payload["imageMimeType"],
                    "imageFilename": payload["imageFilename"],
                    "autoSubmit": True,
                    "copyResponseToClipboard": self.settings.copy_response_to_clipboard,
                    "pageReadyTimeoutMs": self.settings.page_ready_timeout_ms,
                    "responseTimeoutMs": 45000,
                    "beforeSubmitDelayMs": self.settings.before_submit_delay_ms,
                    "afterAttachDelayMs": self.settings.after_attach_delay_ms,
                }
            )

            translated_text = str(result.get("assistantResponseText") or "").strip()

            if self.settings.copy_response_to_clipboard:
                if not translated_text:
                    self._hide_translation_overlay()
                    self._save_last_run_status("A kép elküldve, de a ChatGPT válasza nem lett kiolvasható.")
                    return

                self.last_translated_text = translated_text
                self.store.save_last_translated_text(translated_text)
                self.clipboard.setText(translated_text)
                self._show_translation_overlay(translated_text)
                self._play_ready_sound()
                self._save_last_run_status(f"A fordítás a vágólapra másolva és memóriába mentve. Gyorsbillentyű: {self.settings.type_out_hotkey}")
                return

            if translated_text:
                self.last_translated_text = translated_text
                self.store.save_last_translated_text(translated_text)
                self._show_translation_overlay(translated_text)
            else:
                self._hide_translation_overlay()

            self._save_last_run_status("A kép elküldve a ChatGPT-nek.")
        except Exception as error:  # noqa: BLE001
            self._hide_translation_overlay()
            self._save_last_run_status(str(error))
            self._set_live_status(str(error))
        finally:
            self.clipboard_translation_in_progress = False

    def _play_ready_sound(self) -> None:
        try:
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except RuntimeError:
            QApplication.beep()

    def _save_last_run_status(self, message: str) -> None:
        self.last_run_status = self.store.save_last_run_status(message)
        self._render_last_run_status(self.last_run_status)
        self._set_live_status(message)

    def _render_last_run_status(self, status: LastRunStatus) -> None:
        if not status.message:
            self.last_run_label.setText("Még nincs futási állapot.")
            return

        self.last_run_label.setText(f"{status.at}: {status.message}")

    def _set_live_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.top_status_label.setText(message)

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

    def _register_hotkeys(self) -> None:
        if sys.platform != "win32":
            self.hotkey_errors = {
                "type_out": "A gyorsbillentyűk csak Windowson érhetők el.",
                "screen_clip": "A gyorsbillentyűk csak Windowson érhetők el.",
            }
            return

        self._unregister_hotkeys()
        self.settings = self._read_settings_from_form()

        configured_hotkeys: dict[str, tuple[int, int]] = {}
        hotkey_labels = {
            "type_out": "Begépelési gyorsbillentyű",
            "screen_clip": "Képkivágási gyorsbillentyű",
        }
        hotkey_values = {
            "type_out": (self.settings.type_out_hotkey_enabled, self.settings.type_out_hotkey),
            "screen_clip": (self.settings.screen_clip_hotkey_enabled, self.settings.screen_clip_hotkey),
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

            for action in actions:
                self.hotkey_errors[action] = "A képkivágási és a begépelési gyorsbillentyű nem lehet ugyanaz."

        self.registered_hotkeys = {
            action: hotkey for action, hotkey in configured_hotkeys.items() if action not in self.hotkey_errors
        }
        self.hotkey_pressed_states = {action: False for action in self.registered_hotkeys}

    def _unregister_hotkeys(self) -> None:
        if sys.platform != "win32":
            return

        self.registered_hotkeys = {}
        self.hotkey_pressed_states = {}

    def _install_keyboard_hook(self) -> None:
        if sys.platform != "win32" or self.keyboard_hook_handle is not None:
            return

        module_handle = kernel32.GetModuleHandleW(None)
        self.keyboard_hook_callback = HOOKPROC(self._keyboard_hook_proc)
        self.keyboard_hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.keyboard_hook_callback, module_handle, 0)

        if not self.keyboard_hook_handle:
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

        self.last_seen_image_signature = self._current_clipboard_signature()

        try:
            os.startfile("ms-screenclip:")
            self._set_live_status(f"A Windows képkivágó megnyitva: {self.settings.screen_clip_hotkey}")
        except OSError as error:
            self._set_live_status(f"A képkivágó nem indítható el: {error}")

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
        self.type_out_hotkey_enabled.setChecked(settings.type_out_hotkey_enabled)
        self.screen_clip_hotkey_enabled.setChecked(settings.screen_clip_hotkey_enabled)
        self._set_hotkey_value(self.screen_clip_hotkey, settings.screen_clip_hotkey)
        self._set_hotkey_value(self.type_out_hotkey, settings.type_out_hotkey)
        self.overlay_opacity_slider.setValue(settings.overlay_opacity_percent)
        self.overlay_duration_seconds.setValue(settings.overlay_duration_seconds)
        self.page_load_delay_ms.setValue(settings.page_load_delay_ms)
        self.page_ready_timeout_ms.setValue(settings.page_ready_timeout_ms)
        self.before_submit_delay_ms.setValue(settings.before_submit_delay_ms)
        self.after_attach_delay_ms.setValue(settings.after_attach_delay_ms)

    def _read_settings_from_form(self) -> AppSettings:
        return AppSettings(
            monitoring_enabled=True,
            chatgpt_url=CHATGPT_URL,
            keep_chatgpt_in_background=True,
            prompt_template=self.prompt_template.toPlainText().strip() or str(DEFAULT_SETTINGS["promptTemplate"]),
            auto_submit=True,
            copy_response_to_clipboard=self.copy_response_to_clipboard.isChecked(),
            type_out_hotkey_enabled=self.type_out_hotkey_enabled.isChecked(),
            type_out_hotkey=self._read_hotkey_value(self.type_out_hotkey, str(DEFAULT_SETTINGS["typeOutHotkey"])),
            screen_clip_hotkey_enabled=self.screen_clip_hotkey_enabled.isChecked(),
            screen_clip_hotkey=self._read_hotkey_value(self.screen_clip_hotkey, str(DEFAULT_SETTINGS["screenClipHotkey"])),
            overlay_opacity_percent=self.overlay_opacity_slider.value(),
            overlay_duration_seconds=self.overlay_duration_seconds.value(),
            page_load_delay_ms=self.page_load_delay_ms.value(),
            page_ready_timeout_ms=self.page_ready_timeout_ms.value(),
            before_submit_delay_ms=self.before_submit_delay_ms.value(),
            after_attach_delay_ms=self.after_attach_delay_ms.value(),
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
        self.drawer_backdrop.setGeometry(0, 0, surface_width, surface_height)

        visible_x, hidden_x, top_margin, panel_height = self._drawer_positions()
        current_x = visible_x if self.drawer_open else hidden_x
        self.drawer_panel.move(current_x, top_margin)
        self.drawer_panel.resize(self.drawer_panel.width(), panel_height)

        if self.drawer_open:
            self.drawer_backdrop.raise_()
            self.drawer_panel.raise_()

    def _ensure_automation_ready(self) -> None:
        if self.page_loading:
            self._wait_for_page_load(self.settings.page_ready_timeout_ms + 5000)

        ready = self._run_javascript("typeof window.__gamerTranslatorDeliver === 'function';", timeout_ms=5000)

        if ready is True:
            self.automation_ready = True
            return

        self._run_javascript(self.automation_script, timeout_ms=10000)
        ready = self._run_javascript("typeof window.__gamerTranslatorDeliver === 'function';", timeout_ms=5000)

        if ready is not True:
            raise RuntimeError("Nem sikerült betölteni az oldalautomatizálást.")

        self.automation_ready = True

    def _execute_delivery(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_automation_ready()
        call_id = uuid.uuid4().hex
        payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
        launch_script = f"""
            (() => {{
              window.__gamerTranslatorResults = window.__gamerTranslatorResults || Object.create(null);
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
        self._run_javascript(launch_script, timeout_ms=5000)

        timeout_ms = int(payload.get("pageReadyTimeoutMs", self.settings.page_ready_timeout_ms)) + int(payload.get("responseTimeoutMs", 45000)) + 10000
        started_at = time.monotonic()

        while (time.monotonic() - started_at) * 1000 < timeout_ms:
            result_json = self._run_javascript(
                f"""
                    (() => {{
                      const bucket = window.__gamerTranslatorResults || Object.create(null);
                      const value = bucket["{call_id}"];

                      if (value === undefined) {{
                        return null;
                      }}

                      delete bucket["{call_id}"];
                      return value;
                    }})()
                """,
                timeout_ms=5000,
            )

            if isinstance(result_json, str) and result_json:
                result = json.loads(result_json)

                if result.get("ok") is False:
                    raise RuntimeError(result.get("error") or "Az oldaloldali művelet hibával tért vissza.")

                return result

            self._wait_with_events(120)

        raise RuntimeError("A ChatGPT oldaloldali művelete nem fejeződött be időben.")

    def _wait_for_page_load(self, timeout_ms: int) -> None:
        if not self.page_loading:
            return

        loop = QEventLoop(self)
        timer = QTimer(self)
        timer.setSingleShot(True)

        def finish(*_args: object) -> None:
            if loop.isRunning():
                loop.quit()

        timer.timeout.connect(finish)
        self.browser.loadFinished.connect(finish)
        timer.start(timeout_ms)
        loop.exec()

        try:
            self.browser.loadFinished.disconnect(finish)
        except RuntimeError:
            pass

        if self.page_loading:
            raise RuntimeError("A ChatGPT oldal nem töltődött be időben.")

    def _run_javascript(self, script: str, *, timeout_ms: int) -> Any:
        result_box: dict[str, Any] = {"done": False}
        loop = QEventLoop(self)
        timer = QTimer(self)
        timer.setSingleShot(True)

        def handle_result(result: Any) -> None:
            result_box["done"] = True
            result_box["value"] = result
            if loop.isRunning():
                loop.quit()

        def handle_timeout() -> None:
            if loop.isRunning():
                loop.quit()

        timer.timeout.connect(handle_timeout)
        timer.start(timeout_ms)
        self.browser.page().runJavaScript(script, handle_result)
        loop.exec()

        if not result_box["done"]:
            raise RuntimeError("A JavaScript futtatása időtúllépéssel megszakadt.")

        return result_box.get("value")

    def _wait_with_events(self, delay_ms: int) -> None:
        if delay_ms <= 0:
            return

        loop = QEventLoop(self)
        QTimer.singleShot(delay_ms, loop.quit)
        loop.exec()

    def _read_clipboard_image_payload(self) -> dict[str, str] | None:
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
        }

    def _current_clipboard_signature(self) -> str:
        payload = self._read_clipboard_image_payload()
        return str(payload["imageSignature"]) if payload else ""

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
