"""Alt/Win menümaszkolás és hook-kiszolgálás valódi bevitel nélkül."""
from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from gamer_translator import main_window as module
from test_mouse_hotkeys import hotkey_window


class ModifierMenuTests(unittest.TestCase):
    def setUp(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.window._set_live_status = Mock()
        self.native = patch.object(module, "user32", Mock()).start()
        self.native.SendInput.return_value = 2
        self.native.CallNextHookEx.return_value = 73
        self.editor = patch.object(module, "active_hotkey_editor", return_value=None).start()
        self.modifiers = patch.object(module, "current_hotkey_modifiers", return_value=module.MOD_ALT).start()
        self.single_shot = patch.object(module.QTimer, "singleShot").start()
        self.addCleanup(patch.stopall)

    def mask(self, modifiers):
        module.MainWindow._mask_hotkey_modifier_menu(self.window, modifiers)

    def key(self, vk, message=module.WM_KEYDOWN, *, flags=0, marker=0):
        data = module.KBDLLHOOKSTRUCT(vkCode=vk, flags=flags, dwExtraInfo=marker)
        return self.window._keyboard_hook_proc(module.HC_ACTION, message, ctypes.pointer(data))

    def test_alt_and_win_mask_uses_tagged_no_mapping_down_up_pair(self):
        for modifiers in (module.MOD_ALT, module.MOD_ALT | module.MOD_SHIFT,
                          module.MOD_WIN, module.MOD_WIN | module.MOD_CONTROL):
            with self.subTest(modifiers=modifiers):
                self.native.SendInput.reset_mock()
                self.mask(modifiers)
                self.native.SendInput.assert_called_once()
                count, inputs, structure_size = self.native.SendInput.call_args.args
                self.assertEqual(count, 2)
                self.assertEqual(structure_size, ctypes.sizeof(module.INPUT))
                self.assertEqual([entry.ki.wVk for entry in inputs], [0xFF, 0xFF])
                self.assertEqual([entry.ki.dwFlags for entry in inputs], [0, module.KEYEVENTF_KEYUP])
                self.assertTrue(all(entry.ki.dwExtraInfo == module.OWN_INPUT_MARKER for entry in inputs))
                self.assertTrue(all(entry.ki.wScan == 0 for entry in inputs))
        self.single_shot.assert_not_called()

    def test_control_alt_altgr_and_nonmenu_modifiers_do_not_inject_mask(self):
        for modifiers in (0, module.MOD_CONTROL, module.MOD_SHIFT,
                          module.MOD_ALT | module.MOD_CONTROL, module.MOD_ALTGR,
                          module.MOD_ALTGR | module.MOD_SHIFT):
            self.mask(modifiers)
        self.native.SendInput.assert_not_called()

    def test_partial_mask_releases_its_key_and_reports_limitation(self):
        self.native.SendInput.side_effect = [1, 1]
        self.mask(module.MOD_ALT)
        self.assertEqual(self.native.SendInput.call_count, 2)
        count, releases, _ = self.native.SendInput.call_args.args
        self.assertEqual(count, 1)
        self.assertEqual(releases[0].ki.wVk, 0xFF)
        self.assertEqual(releases[0].ki.dwFlags, module.KEYEVENTF_KEYUP)
        self.assertEqual(releases[0].ki.dwExtraInfo, module.OWN_INPUT_MARKER)
        self.single_shot.assert_called_once()
        self.single_shot.call_args.args[1]()
        self.assertIn("nem engedte", self.window._set_live_status.call_args.args[0])

    def test_rejected_mask_does_not_release_real_modifiers(self):
        self.native.SendInput.return_value = 0
        self.mask(module.MOD_WIN)
        self.native.SendInput.assert_called_once()
        self.single_shot.assert_called_once()

    def test_mask_is_sent_once_for_matching_primary_not_for_repeat_or_release(self):
        self.assertEqual(self.key(ord("C")), 1)
        self.assertEqual(self.key(ord("C")), 1)
        self.assertEqual(self.key(ord("C"), module.WM_KEYUP), 1)
        self.window._mask_hotkey_modifier_menu.assert_called_once_with(module.MOD_ALT)

    def test_mouse_binding_also_requests_modifier_menu_mask(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, 0x05)})
        data = module.MSLLHOOKSTRUCT(mouseData=1 << 16)
        self.assertEqual(self.window._mouse_hook_proc(module.HC_ACTION, module.WM_XBUTTONDOWN, ctypes.pointer(data)), 1)
        self.window._mask_hotkey_modifier_menu.assert_called_once_with(module.MOD_ALT)

    def test_modifier_down_and_up_still_pass_to_avoid_stuck_keys(self):
        self.assertEqual(self.key(0xA4, module.WM_SYSKEYDOWN), 73)
        self.assertEqual(self.key(ord("C"), module.WM_SYSKEYDOWN), 1)
        self.assertEqual(self.key(0xA4, module.WM_SYSKEYUP), 73)
        self.assertEqual(self.key(ord("C"), module.WM_KEYUP), 1)
        self.assertEqual(self.native.CallNextHookEx.call_count, 2)

    def test_unbound_combinations_and_standalone_modifiers_do_not_request_mask(self):
        for key in (0xA4, 0x5B, ord("Z")):
            self.assertEqual(self.key(key), 73)
            self.assertEqual(self.key(key, module.WM_KEYUP), 73)
        self.window._mask_hotkey_modifier_menu.assert_not_called()
        self.single_shot.assert_not_called()

    def test_mask_key_cannot_trigger_an_action_even_if_manually_bound(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, 0xFF)})
        self.assertEqual(self.key(0xFF, flags=module.LLKHF_INJECTED, marker=module.OWN_INPUT_MARKER), 73)
        self.assertEqual(self.key(0xFF, module.WM_KEYUP, flags=module.LLKHF_INJECTED, marker=module.OWN_INPUT_MARKER), 73)
        self.single_shot.assert_not_called()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_typing_services_event_loop_before_sending_each_character(self):
        window = SimpleNamespace(last_translated_text="ab", _set_live_status=Mock())
        self.native.GetForegroundWindow.return_value = 111
        with patch.object(module, "build_character_inputs", return_value=[module.build_key_input(ord("A")), module.build_key_input(ord("A"), key_up=True)]), \
                patch.object(module.QGuiApplication, "processEvents") as events, patch.object(module.time, "sleep"):
            self.assertTrue(module.MainWindow._type_cached_text_via_hotkey(window, target_window=111))
        self.assertEqual(events.call_count, 2)
        events.assert_called_with(module.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)
        self.assertEqual(self.native.SendInput.call_count, 2)


if __name__ == "__main__":
    unittest.main()
