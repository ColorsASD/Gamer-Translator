"""Natív billentyűazonosítók és billentyűzetkiosztást követő gyorsgombmező."""
from __future__ import annotations

import ctypes
import re
import sys

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_ALTGR = 0x0010
MOUSE_KEYCODES = {0x05, 0x06}

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
if user32 is not None:
    from ctypes import wintypes

    user32.GetKeyboardLayout.argtypes = (wintypes.DWORD,)
    user32.GetKeyboardLayout.restype = wintypes.HANDLE
    user32.MapVirtualKeyExW.argtypes = (wintypes.UINT, wintypes.UINT, wintypes.HANDLE)
    user32.MapVirtualKeyExW.restype = wintypes.UINT
    user32.VkKeyScanExW.argtypes = (wintypes.WCHAR, wintypes.HANDLE)
    user32.VkKeyScanExW.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = (ctypes.c_int,)
    user32.GetAsyncKeyState.restype = ctypes.c_short

_MODIFIER_ALIASES = {
    "CTRL": MOD_CONTROL, "CONTROL": MOD_CONTROL,
    "ALT": MOD_ALT, "ALTGR": MOD_ALTGR, "ALT GR": MOD_ALTGR,
    "SHIFT": MOD_SHIFT,
    "WIN": MOD_WIN, "WINDOWS": MOD_WIN, "META": MOD_WIN,
}
_MODIFIER_LABELS = (
    (MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_ALTGR, "AltGr"),
    (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"),
)
_KEY_LABELS = {
    0x05: "Mouse 4", 0x06: "Mouse 5",
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause",
    0x14: "CapsLock", 0x1B: "Esc", 0x20: "Space", 0x21: "PageUp",
    0x22: "PageDown", 0x23: "End", 0x24: "Home", 0x25: "Left",
    0x26: "Up", 0x27: "Right", 0x28: "Down", 0x2C: "PrintScreen",
    0x2D: "Insert", 0x2E: "Delete", 0x5D: "Menu",
    0x6A: "Num *", 0x6B: "Num +", 0x6C: "Num Separator",
    0x6D: "Num -", 0x6E: "Num Decimal", 0x6F: "Num /",
    0x90: "NumLock", 0x91: "ScrollLock",
    0xAD: "VolumeMute", 0xAE: "VolumeDown", 0xAF: "VolumeUp",
    0xB0: "MediaNext", 0xB1: "MediaPrevious", 0xB2: "MediaStop", 0xB3: "MediaPlayPause",
}
_KEY_LABELS.update({0x60 + number: f"Num {number}" for number in range(10)})
_KEY_LABELS.update({0x6F + number: f"F{number}" for number in range(1, 25)})
_KEYCODES = {label.upper(): vk for vk, label in _KEY_LABELS.items()}
_KEYCODES.update({
    "RETURN": 0x0D, "ESCAPE": 0x1B, "DEL": 0x2E, "INS": 0x2D,
    "PGUP": 0x21, "PGDOWN": 0x22, "PGDN": 0x22,
    "PRINT": 0x2C, "PRTSC": 0x2C, "PAUSE/BREAK": 0x13,
    "MOUSE4": 0x05, "MOUSE5": 0x06, "MOUSE 4": 0x05, "MOUSE 5": 0x06,
    "XBUTTON1": 0x05, "XBUTTON2": 0x06, "BACKBUTTON": 0x05, "FORWARDBUTTON": 0x06,
    "NUM .": 0x6E, "NUM ,": 0x6E, "NUM DECIMAL": 0x6E,
    "VOLUME MUTE": 0xAD, "VOLUME DOWN": 0xAE, "VOLUME UP": 0xAF,
    "MEDIA NEXT": 0xB0, "MEDIA PREVIOUS": 0xB1, "MEDIA STOP": 0xB2,
    "MEDIA PLAY": 0xB3, "MEDIA PAUSE": 0xB3, "MEDIA TOGGLE PLAY/PAUSE": 0xB3,
})
_OEM_KEYCODES = {0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF, 0xE2}
_MODIFIER_KEYCODES = {0x10, 0x11, 0x12, 0x5B, 0x5C, 0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5}
_QT_MODIFIER_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_AltGr, Qt.Key.Key_Meta}
_QT_KEYCODES = {
    Qt.Key.Key_Backspace: 0x08, Qt.Key.Key_Tab: 0x09, Qt.Key.Key_Backtab: 0x09,
    Qt.Key.Key_Return: 0x0D, Qt.Key.Key_Enter: 0x0D, Qt.Key.Key_Pause: 0x13,
    Qt.Key.Key_CapsLock: 0x14, Qt.Key.Key_Escape: 0x1B, Qt.Key.Key_Space: 0x20,
    Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22, Qt.Key.Key_End: 0x23,
    Qt.Key.Key_Home: 0x24, Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26,
    Qt.Key.Key_Right: 0x27, Qt.Key.Key_Down: 0x28, Qt.Key.Key_Print: 0x2C,
    Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E, Qt.Key.Key_Menu: 0x5D,
    Qt.Key.Key_NumLock: 0x90, Qt.Key.Key_ScrollLock: 0x91,
    Qt.Key.Key_VolumeMute: 0xAD, Qt.Key.Key_VolumeDown: 0xAE, Qt.Key.Key_VolumeUp: 0xAF,
    Qt.Key.Key_MediaNext: 0xB0, Qt.Key.Key_MediaPrevious: 0xB1, Qt.Key.Key_MediaStop: 0xB2,
    Qt.Key.Key_MediaPlay: 0xB3, Qt.Key.Key_MediaPause: 0xB3, Qt.Key.Key_MediaTogglePlayPause: 0xB3,
}
_PREFIX_PATTERN = re.compile(r"^(Control|Ctrl|Alt\s*Gr|Alt|Shift|Windows|Win|Meta)\s*[+\-]\s*", re.IGNORECASE)


def _is_supported_key(vk: int) -> bool:
    return vk in _KEY_LABELS or vk in _OEM_KEYCODES or 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A


def _base_key_character(vk: int) -> str:
    if user32 is None:
        return ""
    # MAPVK_VK_TO_CHAR: a Shift/AltGr által előállított jel helyett az alapbillentyű.
    mapped = int(user32.MapVirtualKeyExW(vk, 2, user32.GetKeyboardLayout(0))) & 0x7FFFFFFF
    if not 0 < mapped <= 0x10FFFF:
        return ""
    character = chr(mapped)
    return character.upper() if character.isprintable() else ""


def _character_keycode(character: str) -> int | None:
    upper = character.upper()
    if len(upper) == 1 and ("A" <= upper <= "Z" or "0" <= upper <= "9"):
        return ord(upper)
    # Elsőként a kiosztás módosító nélküli jelét keressük, így pl. a magyar '-'
    # nem a numerikus kivonásra, hanem a valóban lenyomott OEM gombra mutat.
    for vk in sorted(_OEM_KEYCODES):
        if _base_key_character(vk) == upper:
            return vk
    if user32 is not None and len(character) == 1:
        mapped = int(user32.VkKeyScanExW(character, user32.GetKeyboardLayout(0)))
        if mapped != -1 and _is_supported_key(mapped & 0xFF):
            return mapped & 0xFF
    return None


def parse_hotkey_definition(value: str) -> tuple[int, int]:
    remaining = str(value).strip()
    modifiers = 0
    while match := _PREFIX_PATTERN.match(remaining):
        modifier_name = re.sub(r"\s+", "", match.group(1).upper())
        modifiers |= _MODIFIER_ALIASES[modifier_name]
        remaining = remaining[match.end():].strip()

    if not remaining or remaining.upper() in _MODIFIER_ALIASES:
        raise ValueError("Adj meg egy fő billentyűt vagy egérgombot, például: Alt+C vagy Mouse 4")

    key_token = remaining.upper()
    # A Qt korábbi Num+0 / Num++ formája is betölthető marad.
    if key_token.startswith("NUM+"):
        key_token = "NUM " + key_token[4:]
    elif key_token.startswith("NUMPAD"):
        key_token = "NUM " + key_token[6:].lstrip(" +")
    elif re.fullmatch(r"NUM[0-9]", key_token):
        key_token = "NUM " + key_token[3:]

    if re.fullmatch(r"VK_[0-9A-F]{2}", key_token):
        vk = int(key_token[3:], 16)
    else:
        vk = _KEYCODES.get(key_token)
        if vk is None and len(remaining) == 1:
            vk = _character_keycode(remaining)

    if vk is None or not _is_supported_key(vk):
        if key_token == "FN":
            raise ValueError("Az Fn gombot a legtöbb eszköz nem továbbítja külön a Windowsnak.")
        raise ValueError(f"Nem támogatott gyorsbillentyű: {remaining}")
    return modifiers, vk


def _key_token(vk: int) -> str:
    if vk in _KEY_LABELS:
        return _KEY_LABELS[vk]
    if 0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A:
        return chr(vk)
    return f"VK_{vk:02X}"


def _join_hotkey(modifiers: int, key: str) -> str:
    return "+".join([label for flag, label in _MODIFIER_LABELS if modifiers & flag] + [key])


def format_hotkey_definition(value: str) -> str:
    try:
        modifiers, vk = parse_hotkey_definition(value)
    except ValueError:
        return str(value)
    key = (_base_key_character(vk) or _key_token(vk)) if vk in _OEM_KEYCODES else _key_token(vk)
    return _join_hotkey(modifiers, key)


def current_hotkey_modifiers() -> int:
    if user32 is None:
        return 0
    pressed = lambda vk: bool(user32.GetAsyncKeyState(vk) & 0x8000)
    right_alt = pressed(0xA5)
    modifiers = MOD_ALTGR if right_alt else 0
    # Windows AltGr esetén szintetikus bal Ctrl-t is jelez. A jobb Ctrl ettől
    # függetlenül megkülönböztethető; a valódi bal Ctrl+bal Alt továbbra is külön kombináció.
    if pressed(0xA3) or (not right_alt and (pressed(0x11) or pressed(0xA2))):
        modifiers |= MOD_CONTROL
    if pressed(0xA4) or (not right_alt and pressed(0x12)):
        modifiers |= MOD_ALT
    if pressed(0x10) or pressed(0xA0) or pressed(0xA1):
        modifiers |= MOD_SHIFT
    if pressed(0x5B) or pressed(0x5C):
        modifiers |= MOD_WIN
    return modifiers


def _event_modifiers(event: QKeyEvent | QMouseEvent) -> int:
    native = current_hotkey_modifiers()
    qt = event.modifiers()
    altgr = bool(native & MOD_ALTGR or qt & Qt.KeyboardModifier.GroupSwitchModifier)
    modifiers = native
    if altgr:
        modifiers |= MOD_ALTGR
    else:
        if qt & Qt.KeyboardModifier.ControlModifier:
            modifiers |= MOD_CONTROL
        if qt & Qt.KeyboardModifier.AltModifier:
            modifiers |= MOD_ALT
    if qt & Qt.KeyboardModifier.ShiftModifier:
        modifiers |= MOD_SHIFT
    if qt & Qt.KeyboardModifier.MetaModifier:
        modifiers |= MOD_WIN
    return modifiers


def _event_keycode(event: QKeyEvent) -> int | None:
    native = int(event.nativeVirtualKey())
    if native:
        return native if _is_supported_key(native) and native not in MOUSE_KEYCODES else None
    key = event.key()
    if event.modifiers() & Qt.KeyboardModifier.KeypadModifier:
        if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return 0x60 + key - Qt.Key.Key_0
        keypad_keys = {Qt.Key.Key_Asterisk: 0x6A, Qt.Key.Key_Plus: 0x6B, Qt.Key.Key_Minus: 0x6D,
                       Qt.Key.Key_Period: 0x6E, Qt.Key.Key_Comma: 0x6E, Qt.Key.Key_Slash: 0x6F}
        if key in keypad_keys:
            return keypad_keys[key]
    if key in _QT_KEYCODES:
        return _QT_KEYCODES[key]
    if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
        return 0x70 + key - Qt.Key.Key_F1
    if 0 < key < 0x1000000:
        return _character_keycode(chr(key))
    return None


def active_hotkey_editor() -> HotkeyEdit | None:
    widget = QApplication.focusWidget()
    if isinstance(widget, HotkeyEdit) and widget.isEnabled() and widget.isVisible() and widget.isActiveWindow():
        return widget
    return None


class HotkeyEdit(QLineEdit):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._hotkey_value = ""
        self.setReadOnly(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setPlaceholderText("Nyomd le a kívánt gyorsgombot")
        self.setToolTip(
            "Kattints ide, majd nyomd le a kívánt billentyűkombinációt vagy a Mouse 4 / Mouse 5 oldalsó egérgombot. "
            "Az AltGr külön módosítóként használható. Az Fn gombot a legtöbb billentyűzet nem továbbítja külön "
            "a Windowsnak; ilyenkor a gyártó programjában rendelj hozzá például egy F13–F24 billentyűt."
        )

    def set_hotkey_value(self, value: str) -> None:
        raw = str(value).strip()
        try:
            modifiers, vk = parse_hotkey_definition(raw)
        except ValueError:
            self._hotkey_value = raw
        else:
            self._hotkey_value = _join_hotkey(modifiers, _key_token(vk))
        self.setText(format_hotkey_definition(self._hotkey_value))

    def hotkey_value(self) -> str:
        return self._hotkey_value

    def record_mouse_button(self, vk: int, modifiers: int) -> None:
        if vk in MOUSE_KEYCODES:
            self.set_hotkey_value(_join_hotkey(modifiers, _key_token(vk)))

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        # Tab is lehessen fő billentyű; a QWidget alapból fókuszváltásra használná.
        if event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        event.accept()
        if event.isAutoRepeat() or event.key() in _QT_MODIFIER_KEYS or event.nativeVirtualKey() in _MODIFIER_KEYCODES:
            return
        vk = _event_keycode(event)
        if vk is not None:
            self.set_hotkey_value(_join_hotkey(_event_modifiers(event), _key_token(vk)))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        buttons = {Qt.MouseButton.BackButton: 0x05, Qt.MouseButton.ForwardButton: 0x06}
        vk = buttons.get(event.button())
        if vk is not None:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.record_mouse_button(vk, _event_modifiers(event))
            event.accept()
            return
        super().mousePressEvent(event)
