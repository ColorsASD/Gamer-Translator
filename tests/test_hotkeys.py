"""Gyorsgomb rögzítési regressziók valódi hook, vágólap és billentyűküldés nélkül."""
from __future__ import annotations

import ctypes
import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QLineEdit

from gamer_translator import hotkeys as module
from gamer_translator.hotkeys import (
    HotkeyEdit, MOD_ALT, MOD_ALTGR, MOD_CONTROL, MOD_SHIFT, MOD_WIN,
    active_hotkey_editor, current_hotkey_modifiers, format_hotkey_definition, parse_hotkey_definition,
)


def hungarian_keyboard():
    native = Mock()
    native.GetKeyboardLayout.return_value = 0x040E040E
    # A Windows magyar (0000040E) kiosztásának MapVirtualKeyExW alapkarakterei.
    base_characters = {0xBA: "É", 0xBB: "Ó", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "Ü",
                       0xC0: "Ö", 0xDB: "Ő", 0xDC: "Ű", 0xDD: "Ú", 0xDE: "Á", 0xE2: "Í"}
    native.MapVirtualKeyExW.side_effect = lambda vk, mode, layout: ord(base_characters[vk]) if vk in base_characters else 0
    native.VkKeyScanExW.side_effect = lambda char, layout: {"+": 0x0133, "*": 0x06BD}.get(char, -1)
    native.GetAsyncKeyState.return_value = 0
    return native


class HotkeyDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.native = hungarian_keyboard()
        patch.object(module, "user32", self.native).start()
        self.addCleanup(patch.stopall)

    def test_existing_letters_functions_and_aliases_are_preserved(self):
        cases = {
            "Alt+C": (MOD_ALT, ord("C")),
            "Ctrl+Alt+Shift+V": (MOD_CONTROL | MOD_ALT | MOD_SHIFT, ord("V")),
            "Control+Windows+PageUp": (MOD_CONTROL | MOD_WIN, 0x21),
            "Meta+PgDown": (MOD_WIN, 0x22),
            "Alt-Esc": (MOD_ALT, 0x1B),
            "F1": (0, 0x70), "F13": (0, 0x7C), "F24": (0, 0x87),
            "Del": (0, 0x2E), "Return": (0, 0x0D),
        }
        for definition, expected in cases.items():
            with self.subTest(definition=definition):
                self.assertEqual(parse_hotkey_definition(definition), expected)

    def test_plus_and_minus_are_not_consumed_as_separators(self):
        cases = {
            "AltGr+-": (MOD_ALTGR, 0xBD), "-": (0, 0xBD),
            "Ctrl++": (MOD_CONTROL, 0x33), "+": (0, 0x33),
            "Ctrl+Alt+-": (MOD_CONTROL | MOD_ALT, 0xBD),
            "Ctrl--": (MOD_CONTROL, 0xBD), "AltGr+VK_BD": (MOD_ALTGR, 0xBD),
            "Ctrl+,": (MOD_CONTROL, 0xBC), "Alt+ö": (MOD_ALT, 0xC0),
        }
        for definition, expected in cases.items():
            with self.subTest(definition=definition):
                self.assertEqual(parse_hotkey_definition(definition), expected)

    def test_legacy_shifted_symbol_remains_loadable(self):
        self.assertEqual(parse_hotkey_definition("Ctrl+Alt+*"), (MOD_CONTROL | MOD_ALT, 0xBD))

    def test_oem_identity_has_layout_aware_label(self):
        self.assertEqual(format_hotkey_definition("AltGr+VK_BD"), "AltGr+-")
        self.assertEqual(format_hotkey_definition("Ctrl+VK_C0"), "Ctrl+Ö")
        self.native.MapVirtualKeyExW.assert_any_call(0xBD, 2, 0x040E040E)
        self.native.MapVirtualKeyExW.side_effect = lambda vk, mode, layout: ord("/") if vk == 0xBD else 0
        self.assertEqual(parse_hotkey_definition("AltGr+VK_BD"), (MOD_ALTGR, 0xBD))
        self.assertEqual(format_hotkey_definition("AltGr+VK_BD"), "AltGr+/")

    def test_dead_key_uses_base_character_without_dead_marker(self):
        self.native.MapVirtualKeyExW.side_effect = lambda vk, mode, layout: 0x80000000 | ord("^")
        self.assertEqual(format_hotkey_definition("Alt+VK_BA"), "Alt+^")

    def test_mouse_buttons_and_modifiers_are_supported(self):
        for definition, expected in {
            "Mouse 4": (0, 5), "MOUSE5": (0, 6), "Ctrl+Mouse 5": (MOD_CONTROL, 6),
            "AltGr+Shift+XBUTTON1": (MOD_ALTGR | MOD_SHIFT, 5),
        }.items():
            with self.subTest(definition=definition):
                self.assertEqual(parse_hotkey_definition(definition), expected)

    def test_keypad_digits_and_operators_are_distinct(self):
        for definition, expected in {
            "Num 0": (0, 0x60), "Num+9": (0, 0x69), "NumPad3": (0, 0x63),
            "Num4": (0, 0x64), "Alt+Num +": (MOD_ALT, 0x6B),
            "Num++": (0, 0x6B), "Num+-": (0, 0x6D), "Num+/": (0, 0x6F),
            "Num+*": (0, 0x6A), "Num+.": (0, 0x6E), "Num Decimal": (0, 0x6E),
        }.items():
            with self.subTest(definition=definition):
                self.assertEqual(parse_hotkey_definition(definition), expected)
        self.assertNotEqual(parse_hotkey_definition("0"), parse_hotkey_definition("Num 0"))
        self.assertNotEqual(parse_hotkey_definition("-"), parse_hotkey_definition("Num -"))

    def test_unknown_or_modifier_only_values_are_rejected(self):
        for value in ("", "Ctrl", "AltGr", "Ctrl+", "Alt+Fn", "Fn", "F25", "Mouse 6", "Ctrl+Alt+C, Alt+V", "VK_FF", "VK_11"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_hotkey_definition(value)
        self.assertEqual(format_hotkey_definition("Fn"), "Fn")

    def test_media_keys_generated_by_fn_combinations_can_be_named(self):
        cases = {"VolumeMute": 0xAD, "Volume Down": 0xAE, "VolumeUp": 0xAF,
                 "MediaNext": 0xB0, "MediaPrevious": 0xB1, "MediaStop": 0xB2,
                 "MediaPlayPause": 0xB3, "Media Toggle Play/Pause": 0xB3}
        for value, vk in cases.items():
            with self.subTest(value=value):
                self.assertEqual(parse_hotkey_definition("Ctrl+" + value), (MOD_CONTROL, vk))
                self.assertEqual(parse_hotkey_definition(format_hotkey_definition("Ctrl+" + value)), (MOD_CONTROL, vk))


class HotkeyModifierTests(unittest.TestCase):
    def assert_modifiers(self, pressed, expected):
        native = hungarian_keyboard()
        native.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk in pressed else 0
        with patch.object(module, "user32", native):
            self.assertEqual(current_hotkey_modifiers(), expected)

    def test_right_alt_suppresses_windows_synthetic_left_control(self):
        self.assert_modifiers({0xA5, 0x12, 0xA2, 0x11}, MOD_ALTGR)

    def test_genuine_left_control_left_alt_stays_separate(self):
        self.assert_modifiers({0xA2, 0x11, 0xA4, 0x12}, MOD_CONTROL | MOD_ALT)

    def test_right_control_can_be_combined_with_altgr(self):
        self.assert_modifiers({0xA3, 0xA5, 0xA2, 0x11, 0x12}, MOD_CONTROL | MOD_ALTGR)

    def test_shift_windows_and_altgr_combine(self):
        self.assert_modifiers({0xA5, 0xA0, 0x5C}, MOD_ALTGR | MOD_SHIFT | MOD_WIN)


class HotkeyEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.native = hungarian_keyboard()
        patch.object(module, "user32", self.native).start()
        self.addCleanup(patch.stopall)
        self.editor = HotkeyEdit()
        self.editor.set_hotkey_value("Alt+C")
        self.addCleanup(self.editor.close)
        self.addCleanup(self.editor.deleteLater)

    def key_event(self, key, *, vk=0, modifiers=Qt.KeyboardModifier.NoModifier, text="", repeat=False):
        event = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, 0, vk, 0, text, repeat)
        self.editor.keyPressEvent(event)
        return event

    def test_native_altgr_minus_records_base_key_not_resulting_asterisk(self):
        self.native.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk in {0xA5, 0xA2, 0x11, 0x12} else 0
        self.key_event(Qt.Key.Key_Asterisk, vk=0xBD,
                       modifiers=Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier, text="*")
        self.assertEqual(self.editor.text(), "AltGr+-")
        self.assertEqual(self.editor.hotkey_value(), "AltGr+VK_BD")

    def test_real_ctrl_alt_keeps_modifiers_even_with_same_character(self):
        self.native.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk in {0xA4, 0xA2, 0x11, 0x12} else 0
        self.key_event(Qt.Key.Key_Asterisk, vk=0xBD,
                       modifiers=Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier, text="*")
        self.assertEqual(self.editor.text(), "Ctrl+Alt+-")
        self.assertEqual(self.editor.hotkey_value(), "Ctrl+Alt+VK_BD")

    def test_qt_groupswitch_is_also_recognized_as_altgr(self):
        self.key_event(Qt.Key.Key_Asterisk, vk=0xBD,
                       modifiers=Qt.KeyboardModifier.GroupSwitchModifier | Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        self.assertEqual(self.editor.text(), "AltGr+-")

    def test_serialized_hotkey_roundtrips_through_a_new_editor(self):
        for definition in ("Alt+C", "F13", "Ctrl+Alt+VK_BD", "AltGr+VK_BD", "Shift+Mouse 5", "Num *"):
            with self.subTest(definition=definition):
                self.editor.set_hotkey_value(definition)
                another = HotkeyEdit()
                another.set_hotkey_value(self.editor.hotkey_value())
                self.assertEqual(another.hotkey_value(), definition)
                self.assertEqual(another.text(), self.editor.text())
                another.deleteLater()

    def test_modifier_keys_autorepeat_and_fn_do_not_replace_value(self):
        cases = ((Qt.Key.Key_Control, 0xA2), (Qt.Key.Key_Shift, 0xA0), (Qt.Key.Key_Alt, 0xA4),
                 (Qt.Key.Key_AltGr, 0xA5), (Qt.Key.Key_Meta, 0x5B), (Qt.Key.Key_unknown, 0),
                 (Qt.Key.Key_unknown, 0xFF))
        for key, vk in cases:
            with self.subTest(key=key, vk=vk):
                self.key_event(key, vk=vk)
                self.assertEqual(self.editor.hotkey_value(), "Alt+C")
        self.key_event(Qt.Key.Key_V, vk=ord("V"), repeat=True)
        self.assertEqual(self.editor.hotkey_value(), "Alt+C")

    def test_mouse_hook_can_record_both_side_buttons_and_modifiers(self):
        self.editor.record_mouse_button(5, MOD_CONTROL)
        self.assertEqual(self.editor.hotkey_value(), "Ctrl+Mouse 4")
        self.editor.record_mouse_button(6, MOD_ALTGR | MOD_SHIFT)
        self.assertEqual(self.editor.text(), "AltGr+Shift+Mouse 5")
        self.editor.record_mouse_button(1, 0)
        self.assertEqual(self.editor.hotkey_value(), "AltGr+Shift+Mouse 5")

    def test_qt_mouse_event_can_record_a_side_button(self):
        event = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(2, 2), QPointF(2, 2),
                            Qt.MouseButton.BackButton, Qt.MouseButton.BackButton, Qt.KeyboardModifier.ShiftModifier)
        self.editor.mousePressEvent(event)
        self.assertEqual(self.editor.hotkey_value(), "Shift+Mouse 4")

    def test_native_keypad_uses_own_keycode(self):
        self.key_event(Qt.Key.Key_5, vk=0x65, modifiers=Qt.KeyboardModifier.KeypadModifier)
        self.assertEqual(self.editor.hotkey_value(), "Num 5")
        self.key_event(Qt.Key.Key_Minus, vk=0x6D, modifiers=Qt.KeyboardModifier.KeypadModifier)
        self.assertEqual(self.editor.hotkey_value(), "Num -")

    def test_native_media_key_records_the_windows_key_not_invisible_fn(self):
        for key, vk, label in (
            (Qt.Key.Key_VolumeMute, 0xAD, "VolumeMute"), (Qt.Key.Key_VolumeDown, 0xAE, "VolumeDown"),
            (Qt.Key.Key_VolumeUp, 0xAF, "VolumeUp"), (Qt.Key.Key_MediaNext, 0xB0, "MediaNext"),
            (Qt.Key.Key_MediaPrevious, 0xB1, "MediaPrevious"), (Qt.Key.Key_MediaStop, 0xB2, "MediaStop"),
            (Qt.Key.Key_MediaTogglePlayPause, 0xB3, "MediaPlayPause"),
        ):
            with self.subTest(vk=vk):
                self.key_event(key, vk=vk)
                self.assertEqual(self.editor.hotkey_value(), label)
                self.assertEqual(self.editor.text(), label)

    def test_tab_is_recorded_instead_of_moving_focus(self):
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.editor.event(event))
        self.assertEqual(self.editor.hotkey_value(), "Ctrl+Tab")

    def test_shortcut_override_is_accepted_before_application_shortcuts(self):
        event = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        event.ignore()
        self.assertTrue(self.editor.event(event))
        self.assertTrue(event.isAccepted())

    def test_only_active_visible_enabled_hotkey_field_is_recording(self):
        with patch.object(module.QApplication, "focusWidget", return_value=self.editor), \
             patch.object(self.editor, "isVisible", return_value=True), \
             patch.object(self.editor, "isActiveWindow", return_value=True):
            self.assertIs(active_hotkey_editor(), self.editor)
            self.editor.setEnabled(False)
            self.assertIsNone(active_hotkey_editor())
            self.editor.setEnabled(True)
            with patch.object(self.editor, "isVisible", return_value=False):
                self.assertIsNone(active_hotkey_editor())
            with patch.object(self.editor, "isActiveWindow", return_value=False):
                self.assertIsNone(active_hotkey_editor())
        with patch.object(module.QApplication, "focusWidget", return_value=QLineEdit()):
            self.assertIsNone(active_hotkey_editor())


class NativeHungarianLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @unittest.skipIf(module.user32 is None, "A natív kiosztásellenőrzés Windowson fut.")
    def test_altgr_minus_uses_real_loaded_hungarian_layout_without_switching_it(self):
        native = module.user32
        native.GetKeyboardLayoutList.argtypes = (ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        native.GetKeyboardLayoutList.restype = ctypes.c_int
        count = native.GetKeyboardLayoutList(0, None)
        layouts = (ctypes.c_void_p * count)()
        loaded = native.GetKeyboardLayoutList(count, layouts)
        hungarian = next((layout for layout in layouts[:loaded] if layout and layout & 0xFFFF == 0x040E), None)
        if hungarian is None:
            self.skipTest("Nincs betöltött magyar billentyűzetkiosztás.")

        minus_vk = native.VkKeyScanExW("-", hungarian) & 0xFF
        self.assertEqual(native.MapVirtualKeyExW(minus_vk, 2, hungarian) & 0x7FFFFFFF, ord("-"))
        # Csak a módosítók állapota szimulált: a leképezést a valódi Windows API
        # végzi a már betöltött magyar kiosztással. Nincs kiosztásváltás vagy SendInput.
        keyboard = Mock()
        keyboard.GetKeyboardLayout.return_value = hungarian
        keyboard.MapVirtualKeyExW.side_effect = native.MapVirtualKeyExW
        keyboard.VkKeyScanExW.side_effect = native.VkKeyScanExW
        keyboard.GetAsyncKeyState.side_effect = lambda vk: 0x8000 if vk in {0xA5, 0xA2, 0x11, 0x12} else 0
        editor = HotkeyEdit()
        self.addCleanup(editor.close)
        self.addCleanup(editor.deleteLater)
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Asterisk,
                          Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
                          0, minus_vk, 0, "*")
        with patch.object(module, "user32", keyboard):
            editor.keyPressEvent(event)
            self.assertEqual(editor.text(), "AltGr+-")
            self.assertEqual(editor.hotkey_value(), f"AltGr+VK_{minus_vk:02X}")
            self.assertEqual(parse_hotkey_definition(editor.hotkey_value()), (MOD_ALTGR, minus_vk))


if __name__ == "__main__":
    unittest.main()
