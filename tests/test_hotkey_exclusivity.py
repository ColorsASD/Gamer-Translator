"""Kizárólagos gyorsgombok regressziói valódi rendszerbevitel nélkül."""
from __future__ import annotations

import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from test_mouse_hotkeys import hotkey_window

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow


class HotkeyExclusivityTests(unittest.TestCase):
    def setUp(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.native = self.patch(module, "user32", Mock())
        self.native.CallNextHookEx.return_value = 73
        self.native.SetWindowsHookExW.return_value = 789
        self.kernel = self.patch(module, "kernel32", Mock())
        self.kernel.GetModuleHandleW.return_value = 1000
        self.editor = self.patch(module, "active_hotkey_editor", Mock(return_value=None))
        self.modifiers = self.patch(module, "current_hotkey_modifiers", Mock(return_value=module.MOD_ALT))
        self.single_shot = self.patch(module.QTimer, "singleShot", Mock())
        self.patch(module, "HOOKPROC", Mock(side_effect=lambda callback: callback))

    def patch(self, target, name, replacement):
        patcher = patch.object(target, name, replacement)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def key_event(self, key=ord("C"), *, up=False, injected=False, extra_info=0):
        event = module.KBDLLHOOKSTRUCT()
        event.vkCode = key
        event.flags = module.LLKHF_INJECTED if injected else 0
        event.dwExtraInfo = extra_info
        return self.window._keyboard_hook_proc(
            module.HC_ACTION,
            module.WM_KEYUP if up else module.WM_KEYDOWN,
            ctypes.pointer(event),
        )

    def mouse_event(self, key=0x05, *, up=False, injected=False, extra_info=0):
        event = module.MSLLHOOKSTRUCT()
        event.mouseData = {0x05: 1, 0x06: 2}[key] << 16
        event.flags = module.LLMHF_INJECTED if injected else 0
        event.dwExtraInfo = extra_info
        return self.window._mouse_hook_proc(
            module.HC_ACTION,
            module.WM_XBUTTONUP if up else module.WM_XBUTTONDOWN,
            ctypes.pointer(event),
        )

    def run_queued_actions(self):
        queued = list(self.single_shot.call_args_list)
        self.single_shot.reset_mock()
        for scheduled in queued:
            self.assertEqual(scheduled.args[0], 0)
            scheduled.args[1]()

    def reconfigure(self, bindings):
        settings = SimpleNamespace(
            type_out_hotkey_enabled="type_out" in bindings,
            type_out_hotkey=bindings.get("type_out", "Alt+V"),
            screen_clip_hotkey_enabled="screen_clip" in bindings,
            screen_clip_hotkey=bindings.get("screen_clip", "Alt+C"),
            quick_chat_hotkey_enabled="quick_chat" in bindings,
            quick_chat_hotkey=bindings.get("quick_chat", "Alt+Q"),
        )
        self.window._read_settings_from_form = Mock(return_value=settings)
        MainWindow._register_hotkeys(self.window)
        self.window._read_settings_from_form.assert_called_once_with()

    def assert_no_actions(self):
        self.window._trigger_type_out_hotkey.assert_not_called()
        self.window._trigger_screen_clip_hotkey.assert_not_called()
        self.window._trigger_quick_chat_hotkey.assert_not_called()

    def test_consumed_keyboard_repeat_stays_private_when_recorder_gains_focus(self):
        self.assertEqual(self.key_event(), 1)
        self.editor.return_value = Mock()
        self.modifiers.return_value = 0
        self.assertEqual(self.key_event(), 1)
        self.assertEqual(self.key_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})
        self.assertEqual(self.key_event(), 73)

    def test_disabling_keyboard_binding_drains_its_existing_press_before_unhooking(self):
        self.assertEqual(self.key_event(), 1)
        previous_generation = self.window.hotkey_generation
        self.reconfigure({})
        self.assertGreater(self.window.hotkey_generation, previous_generation)
        self.assertEqual(self.window.registered_hotkeys, {})
        self.assertIsNotNone(self.window.keyboard_hook_handle)
        self.modifiers.return_value = 0
        self.assertEqual(self.key_event(), 1)
        self.assertEqual(self.key_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})
        self.assertIsNone(self.window.keyboard_hook_handle)

    def test_disabling_mouse_binding_drains_its_existing_press_before_unhooking(self):
        self.window = hotkey_window({"screen_clip": (0, 0x05)})
        self.modifiers.return_value = 0
        self.assertEqual(self.mouse_event(), 1)
        self.reconfigure({})
        self.assertEqual(self.window.registered_hotkeys, {})
        self.assertIsNotNone(self.window.mouse_hook_handle)
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})
        self.assertIsNone(self.window.mouse_hook_handle)

    def test_keyboard_rebinding_keeps_old_press_private_without_replaying_action(self):
        self.assertEqual(self.key_event(), 1)
        self.reconfigure({"screen_clip": "Alt+D"})
        self.assertEqual(self.key_event(), 1)
        self.assertEqual(self.key_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.key_event(), 73)
        self.assertEqual(self.key_event(ord("D")), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.key_event(ord("D"), up=True), 1)

    def test_mouse_rebinding_keeps_old_press_private_without_replaying_action(self):
        self.window = hotkey_window({"screen_clip": (0, 0x05)})
        self.modifiers.return_value = 0
        self.assertEqual(self.mouse_event(), 1)
        self.reconfigure({"screen_clip": "Mouse 5"})
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.mouse_event(), 73)
        self.assertEqual(self.mouse_event(0x06), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.mouse_event(0x06, up=True), 1)

    def test_queued_action_is_cancelled_even_when_same_binding_is_registered_again(self):
        self.assertEqual(self.key_event(), 1)
        self.reconfigure({"screen_clip": "Alt+C"})
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.key_event(up=True), 1)
        self.assertEqual(self.key_event(), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()

    def test_shutdown_cancels_queued_action_and_discards_all_press_state(self):
        self.assertEqual(self.key_event(), 1)
        previous_generation = self.window.hotkey_generation
        self.window._unregister_hotkeys()
        self.assertGreater(self.window.hotkey_generation, previous_generation)
        self.assertEqual(self.window.suppressed_hotkey_presses, {})
        self.assertIsNone(self.window.keyboard_hook_handle)
        self.assertIsNone(self.window.mouse_hook_handle)
        self.run_queued_actions()
        self.assert_no_actions()

    def test_running_action_prevents_reentrant_actions_and_releases_its_guard(self):
        self.window = hotkey_window({
            "screen_clip": (module.MOD_ALT, ord("C")),
            "quick_chat": (module.MOD_ALT, ord("Q")),
        })

        def during_action():
            self.assertTrue(self.window.hotkey_action_running)
            self.window._trigger_hotkey_action("quick_chat", self.window.hotkey_generation)

        self.window._trigger_screen_clip_hotkey.side_effect = during_action
        self.window._trigger_hotkey_action("screen_clip", self.window.hotkey_generation)
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.window._trigger_quick_chat_hotkey.assert_not_called()
        self.assertFalse(self.window.hotkey_action_running)
        self.window._trigger_hotkey_action("quick_chat", self.window.hotkey_generation)
        self.window._trigger_quick_chat_hotkey.assert_called_once_with()
        self.assertFalse(self.window.hotkey_action_running)

    def test_action_exception_does_not_leave_reentrancy_guard_stuck(self):
        self.window._trigger_screen_clip_hotkey.side_effect = RuntimeError("Teszt")
        with self.assertRaisesRegex(RuntimeError, "Teszt"):
            self.window._trigger_hotkey_action("screen_clip", self.window.hotkey_generation)
        self.assertFalse(self.window.hotkey_action_running)
        self.window._trigger_screen_clip_hotkey.side_effect = None
        self.window._trigger_hotkey_action("screen_clip", self.window.hotkey_generation)
        self.assertEqual(self.window._trigger_screen_clip_hotkey.call_count, 2)

    def test_disabling_bindings_keeps_both_pending_input_cycles_private(self):
        self.window = hotkey_window({
            "screen_clip": (module.MOD_ALT, ord("C")),
            "quick_chat": (module.MOD_ALT, 0x05),
        })
        self.assertEqual(self.key_event(), 1)
        self.assertEqual(self.mouse_event(), 1)
        self.reconfigure({})
        self.assertEqual(self.key_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertIsNotNone(self.window.mouse_hook_handle)
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(up=True), 1)
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})
        self.assertIsNone(self.window.keyboard_hook_handle)
        self.assertIsNone(self.window.mouse_hook_handle)

    def test_unrelated_input_and_unmatched_releases_pass_through(self):
        for injected in (False, True):
            with self.subTest(injected=injected):
                self.assertEqual(self.key_event(ord("D"), injected=injected), 73)
                self.assertEqual(self.key_event(up=True, injected=injected), 73)
                self.assertEqual(self.mouse_event(injected=injected), 73)
                self.assertEqual(self.mouse_event(up=True, injected=injected), 73)
                self.modifiers.return_value = module.MOD_ALT | module.MOD_SHIFT
                self.assertEqual(self.key_event(injected=injected), 73)
                self.modifiers.return_value = module.MOD_ALT
        self.run_queued_actions()
        self.assert_no_actions()
        self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_external_injected_keyboard_binding_is_consumed_once_until_release(self):
        self.assertEqual(self.key_event(injected=True), 1)
        self.assertEqual(self.key_event(injected=True), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.modifiers.return_value = 0
        self.assertEqual(self.key_event(up=True, injected=True), 1)
        self.assertEqual(self.key_event(up=True, injected=True), 73)
        self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_external_injected_mouse_binding_is_consumed_once_until_release(self):
        self.window = hotkey_window({"screen_clip": (0, 0x05)})
        self.modifiers.return_value = 0
        self.assertEqual(self.mouse_event(injected=True), 1)
        self.assertEqual(self.mouse_event(injected=True), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.mouse_event(up=True, injected=True), 1)
        self.assertEqual(self.mouse_event(up=True, injected=True), 73)
        self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_own_marked_injected_input_never_activates_or_releases_a_binding(self):
        for key, event_method in ((ord("C"), self.key_event), (0x05, self.mouse_event)):
            with self.subTest(key=key):
                self.window = hotkey_window({"screen_clip": (module.MOD_ALT, key)})
                self.assertEqual(event_method(key, injected=True, extra_info=module.OWN_INPUT_MARKER), 73)
                self.assertEqual(event_method(key), 1)
                self.assertEqual(event_method(key, up=True, injected=True, extra_info=module.OWN_INPUT_MARKER), 73)
                self.assertIn((key, False), self.window.suppressed_hotkey_presses)
                self.assertEqual(event_method(key, up=True), 1)
                self.run_queued_actions()
                self.window._trigger_screen_clip_hotkey.assert_called_once_with()
                self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_marker_without_injected_flag_does_not_bypass_exclusivity(self):
        self.assertEqual(self.key_event(extra_info=module.OWN_INPUT_MARKER), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.key_event(up=True, extra_info=module.OWN_INPUT_MARKER), 1)

    def test_foreign_marker_does_not_bypass_exclusivity(self):
        self.assertEqual(self.key_event(injected=True, extra_info=module.OWN_INPUT_MARKER ^ 1), 1)
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.key_event(up=True, injected=True, extra_info=module.OWN_INPUT_MARKER ^ 1), 1)

    def test_physical_and_injected_presses_drain_independently_without_duplicate_action(self):
        for key, event_method in ((ord("C"), self.key_event), (0x05, self.mouse_event)):
            for first_injected in (False, True):
                with self.subTest(key=key, first_injected=first_injected):
                    self.window = hotkey_window({"screen_clip": (module.MOD_ALT, key)})
                    self.assertEqual(event_method(key, injected=first_injected), 1)
                    self.assertEqual(event_method(key, injected=not first_injected), 1)
                    self.run_queued_actions()
                    self.window._trigger_screen_clip_hotkey.assert_called_once_with()
                    self.assertEqual(set(self.window.suppressed_hotkey_presses), {(key, False), (key, True)})
                    self.assertEqual(event_method(key, up=True, injected=not first_injected), 1)
                    self.assertEqual(event_method(key, injected=first_injected), 1)
                    self.run_queued_actions()
                    self.window._trigger_screen_clip_hotkey.assert_called_once_with()
                    self.assertEqual(set(self.window.suppressed_hotkey_presses), {(key, first_injected)})
                    self.assertEqual(event_method(key, up=True, injected=first_injected), 1)
                    self.assertEqual(self.window.suppressed_hotkey_presses, {})

    def test_unmatched_source_release_cannot_release_a_consumed_press(self):
        for key, event_method in ((ord("C"), self.key_event), (0x05, self.mouse_event)):
            with self.subTest(key=key):
                self.window = hotkey_window({"screen_clip": (module.MOD_ALT, key)})
                self.assertEqual(event_method(key), 1)
                self.assertEqual(event_method(key, up=True, injected=True), 73)
                self.assertIn((key, False), self.window.suppressed_hotkey_presses)
                self.assertEqual(event_method(key, up=True), 1)
                self.run_queued_actions()
                self.window._trigger_screen_clip_hotkey.assert_called_once_with()


class OwnInputMarkerTests(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(module, "user32", Mock())
        self.native = patcher.start()
        self.addCleanup(patcher.stop)
        self.native.MapVirtualKeyW.return_value = 0x1E
        self.native.GetKeyboardLayout.return_value = 0x040E
        self.native.VkKeyScanExW.return_value = ord("A") | (7 << 8)

    def assert_own_input(self, inputs):
        self.assertTrue(inputs)
        self.assertTrue(module.OWN_INPUT_MARKER)
        for entry in inputs:
            self.assertEqual(entry.type, module.INPUT_KEYBOARD)
            self.assertEqual(entry.ki.dwExtraInfo, module.OWN_INPUT_MARKER)

    def test_key_scan_and_modified_input_builders_mark_every_event(self):
        for key_up in (False, True):
            with self.subTest(key_up=key_up):
                self.assert_own_input([module.build_key_input(ord("A"), key_up=key_up)])
                self.assert_own_input([module.build_scan_code_input(ord("A"), key_up=key_up)])
        self.assert_own_input(module.build_virtual_key_inputs(ord("A")))
        self.assert_own_input(module.build_modified_key_inputs(module.VK_CONTROL, ord("A")))
        self.native.MapVirtualKeyW.return_value = 0
        self.assert_own_input([module.build_scan_code_input(ord("A"))])
        self.assert_own_input([module.build_scan_code_input(ord("A"), key_up=True)])

    def test_unicode_newline_tab_and_surrogate_inputs_are_all_marked(self):
        self.assert_own_input(module.build_unicode_inputs("Ő\n\t🎮"))

    def test_character_input_modifiers_and_fallback_are_all_marked(self):
        for character in ("A", "\n", "\t", "🎮"):
            with self.subTest(character=character):
                self.assert_own_input(module.build_character_inputs(character))
        self.native.VkKeyScanExW.return_value = -1
        self.assert_own_input(module.build_character_inputs("ő"))


if __name__ == "__main__":
    unittest.main()
