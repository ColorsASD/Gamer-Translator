"""Egér- és billentyűhook regressziók valódi bemenet, vágólap és küldés nélkül."""
from __future__ import annotations

import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMainWindow

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow


def hotkey_window(bindings=None) -> SimpleNamespace:
    bindings = dict(bindings if bindings is not None else {"screen_clip": (0, 0x05)})
    window = SimpleNamespace(
        registered_hotkeys=bindings,
        registered_hotkey_primary_keys={key for _modifiers, key in bindings.values()},
        hotkey_pressed_states={action: False for action in bindings},
        suppressed_hotkey_presses={},
        hotkey_generation=0,
        hotkey_action_running=False,
        hotkey_errors={},
        keyboard_hook_handle=123,
        keyboard_hook_callback=Mock(),
        mouse_hook_handle=456,
        mouse_hook_callback=Mock(),
        mouse_recording_buttons=set(),
        hotkey_system_integration_enabled=False,
        screen_clip_hotkey_armed_until=0.0,
        _trigger_type_out_hotkey=Mock(),
        _trigger_screen_clip_hotkey=Mock(),
        _trigger_quick_chat_hotkey=Mock(),
        _mask_hotkey_modifier_menu=Mock(),
    )
    for name in (
        "_mouse_hook_proc", "_keyboard_hook_proc", "_handle_hotkey_keydown",
        "_handle_hotkey_keyup", "_trigger_hotkey_action", "_current_modifiers_match",
        "_clear_screen_clip_hotkey_arm", "_register_hotkeys", "_unregister_hotkeys", "_update_keyboard_hook_state",
        "_handle_hotkey_focus_changed",
        "_install_keyboard_hook", "_uninstall_keyboard_hook", "_install_mouse_hook",
        "_uninstall_mouse_hook",
    ):
        setattr(window, name, getattr(MainWindow, name).__get__(window, SimpleNamespace))
    return window


class MouseHotkeyTests(unittest.TestCase):
    def setUp(self):
        self.window = hotkey_window()
        self.native = patch.object(module, "user32", Mock()).start()
        self.native.CallNextHookEx.return_value = 73
        self.kernel = patch.object(module, "kernel32", Mock()).start()
        self.kernel.GetModuleHandleW.return_value = 1000
        self.kernel.GetLastError.return_value = 5
        self.editor = patch.object(module, "active_hotkey_editor", return_value=None).start()
        self.modifiers = patch.object(module, "current_hotkey_modifiers", return_value=0).start()
        self.single_shot = patch.object(module.QTimer, "singleShot").start()
        self.hookproc = patch.object(module, "HOOKPROC", side_effect=lambda callback: callback).start()
        self.addCleanup(patch.stopall)

    def mouse_event(self, button=1, *, message=None, flags=0, n_code=None, low_word=0, extra_info=0):
        event = module.MSLLHOOKSTRUCT()
        event.mouseData = (button << 16) | low_word
        event.flags = flags
        event.dwExtraInfo = extra_info
        return self.window._mouse_hook_proc(
            module.HC_ACTION if n_code is None else n_code,
            module.WM_XBUTTONDOWN if message is None else message,
            ctypes.pointer(event),
        )

    def key_event(self, key, *, message=None, flags=0, extra_info=0):
        event = module.KBDLLHOOKSTRUCT()
        event.vkCode = key
        event.flags = flags
        event.dwExtraInfo = extra_info
        return self.window._keyboard_hook_proc(
            module.HC_ACTION,
            module.WM_KEYDOWN if message is None else message,
            ctypes.pointer(event),
        )

    def run_queued_actions(self):
        queued = list(self.single_shot.call_args_list)
        self.single_shot.reset_mock()
        for scheduled in queued:
            self.assertEqual(scheduled.args[0], 0)
            scheduled.args[1]()

    def assert_no_actions(self):
        self.window._trigger_type_out_hotkey.assert_not_called()
        self.window._trigger_screen_clip_hotkey.assert_not_called()
        self.window._trigger_quick_chat_hotkey.assert_not_called()

    def test_mouse4_and_mouse5_map_high_word_to_distinct_primary_keys(self):
        for button, key in ((1, 0x05), (2, 0x06)):
            with self.subTest(button=button):
                self.window = hotkey_window({"screen_clip": (0, key)})
                self.assertEqual(self.mouse_event(button, low_word=0x4321), 1)
                self.assertTrue(self.window.hotkey_pressed_states["screen_clip"])
                self.assert_no_actions()
                self.run_queued_actions()
                self.window._trigger_screen_clip_hotkey.assert_called_once_with()
                self.assertEqual(self.mouse_event(button, message=module.WM_XBUTTONUP), 1)
                self.assertFalse(self.window.hotkey_pressed_states["screen_clip"])
        self.native.CallNextHookEx.assert_not_called()

    def test_configured_mouse_action_dispatches_only_once_until_release(self):
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(), 1)
        self.single_shot.assert_called_once()
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.mouse_event(), 1)
        self.run_queued_actions()
        self.assertEqual(self.window._trigger_screen_clip_hotkey.call_count, 2)

    def test_mouse_binding_requires_exact_modifiers(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, 0x05)})
        for modifiers in (0, module.MOD_CONTROL, module.MOD_ALT | module.MOD_SHIFT):
            with self.subTest(modifiers=modifiers):
                self.modifiers.return_value = modifiers
                self.assertEqual(self.mouse_event(), 73)
        self.single_shot.assert_not_called()
        self.modifiers.return_value = module.MOD_ALT
        self.assertEqual(self.mouse_event(), 1)
        self.single_shot.assert_called_once()

    def test_mouse_button_release_is_consumed_even_after_modifier_release(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_CONTROL, 0x06)})
        self.modifiers.return_value = module.MOD_CONTROL
        self.assertEqual(self.mouse_event(2), 1)
        self.modifiers.return_value = 0
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 1)
        self.assertFalse(self.window.hotkey_pressed_states["screen_clip"])
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 73)

    def test_unconfigured_mouse_button_and_unmatched_release_pass_through(self):
        self.assertEqual(self.mouse_event(2), 73)
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 73)
        self.assertEqual(self.mouse_event(1, message=module.WM_XBUTTONUP), 73)
        self.single_shot.assert_not_called()
        self.assert_no_actions()

    def test_mouse_move_and_nonaction_event_do_not_dereference_input(self):
        for n_code, message in ((-1, module.WM_XBUTTONDOWN), (1, module.WM_XBUTTONDOWN), (0, 0x0200)):
            with self.subTest(n_code=n_code, message=message):
                self.assertEqual(self.window._mouse_hook_proc(n_code, message, 0), 73)
        self.single_shot.assert_not_called()
        self.modifiers.assert_not_called()

    def test_unknown_xbutton_identifiers_pass_through(self):
        for button in (0, 3, 0xFFFF):
            with self.subTest(button=button):
                self.assertEqual(self.mouse_event(button), 73)
        self.single_shot.assert_not_called()

    def test_own_injected_mouse_events_never_activate_or_release_real_binding(self):
        self.assertEqual(self.mouse_event(flags=module.LLMHF_INJECTED, extra_info=module.OWN_INPUT_MARKER), 73)
        self.single_shot.assert_not_called()
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP, flags=module.LLMHF_INJECTED, extra_info=module.OWN_INPUT_MARKER), 73)
        self.assertTrue(self.window.hotkey_pressed_states["screen_clip"])
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP), 1)

    def test_recording_mouse_button_is_queued_and_does_not_activate_binding(self):
        recorder = Mock()
        self.editor.return_value = recorder
        self.modifiers.return_value = module.MOD_ALTGR | module.MOD_SHIFT
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(), 1)
        recorder.record_mouse_button.assert_not_called()
        self.single_shot.assert_called_once()
        self.assertEqual(self.window.mouse_recording_buttons, {(0x05, False)})
        self.assertFalse(self.window.hotkey_pressed_states["screen_clip"])
        self.modifiers.return_value = 0
        self.run_queued_actions()
        recorder.record_mouse_button.assert_called_once_with(0x05, module.MOD_ALTGR | module.MOD_SHIFT)
        self.assert_no_actions()
        self.native.CallNextHookEx.assert_not_called()

    def test_recorded_mouse_release_remains_consumed_after_focus_changes(self):
        self.editor.return_value = Mock()
        self.assertEqual(self.mouse_event(2), 1)
        self.editor.return_value = None
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.window.mouse_recording_buttons, set())
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 73)
        self.assert_no_actions()

    def test_both_recorded_mouse_buttons_keep_independent_release_state(self):
        recorder = Mock()
        self.editor.return_value = recorder
        self.assertEqual(self.mouse_event(1), 1)
        self.assertEqual(self.mouse_event(2), 1)
        self.assertEqual(self.window.mouse_recording_buttons, {(0x05, False), (0x06, False)})
        self.run_queued_actions()
        self.assertEqual(recorder.record_mouse_button.call_args_list, [call(0x05, 0), call(0x06, 0)])
        self.assertEqual(self.mouse_event(1, message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.window.mouse_recording_buttons, {(0x06, False)})
        self.assertEqual(self.mouse_event(2, message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.window.mouse_recording_buttons, set())

    def test_external_mouse_release_cannot_end_physical_recording(self):
        self.editor.return_value = Mock()
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP, flags=module.LLMHF_INJECTED), 73)
        self.assertEqual(self.window.mouse_recording_buttons, {(0x05, False)})
        self.editor.return_value = None
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.window.mouse_recording_buttons, set())
        self.assert_no_actions()

    def test_physical_and_injected_mouse_recording_drain_separately(self):
        self.editor.return_value = Mock()
        self.assertEqual(self.mouse_event(), 1)
        self.assertEqual(self.mouse_event(flags=module.LLMHF_INJECTED), 1)
        self.assertEqual(self.window.mouse_recording_buttons, {(0x05, False), (0x05, True)})
        self.editor.return_value = None
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP), 1)
        self.assertEqual(self.window.mouse_recording_buttons, {(0x05, True)})
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP, flags=module.LLMHF_INJECTED), 1)
        self.assertEqual(self.window.mouse_recording_buttons, set())
        self.assert_no_actions()

    def test_brief_recorder_focus_cancels_queued_action_even_after_focus_leaves(self):
        self.window.hotkey_system_integration_enabled = True
        self.assertEqual(self.mouse_event(), 1)
        self.editor.return_value = Mock()
        self.window._handle_hotkey_focus_changed()
        self.editor.return_value = None
        self.run_queued_actions()
        self.assert_no_actions()

    def test_keyboard_recording_cancels_stale_capture_without_activating_actions(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.window.screen_clip_hotkey_armed_until = 145.0
        self.editor.return_value = Mock()
        self.modifiers.return_value = module.MOD_ALT
        self.assertEqual(self.key_event(ord("C")), 73)
        self.assertEqual(self.key_event(0x1B), 73)
        self.modifiers.return_value = module.MOD_WIN | module.MOD_SHIFT
        self.assertEqual(self.key_event(ord("S")), 73)
        self.assertEqual(self.window.screen_clip_hotkey_armed_until, 0.0)
        self.single_shot.assert_not_called()
        self.assert_no_actions()

    def test_queued_action_is_cancelled_if_recorder_gains_focus(self):
        self.assertEqual(self.mouse_event(), 1)
        self.editor.return_value = Mock()
        self.run_queued_actions()
        self.assert_no_actions()

    def test_primary_keyboard_repeat_after_modifier_release_stays_consumed_once(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.modifiers.return_value = module.MOD_ALT
        self.assertEqual(self.key_event(ord("C"), message=module.WM_SYSKEYDOWN), 1)
        self.modifiers.return_value = 0
        self.assertEqual(self.key_event(ord("C")), 1)
        self.assertEqual(self.key_event(ord("C")), 1)
        self.single_shot.assert_called_once()
        self.run_queued_actions()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.key_event(ord("C"), message=module.WM_KEYUP), 1)
        self.assertFalse(self.window.hotkey_pressed_states["screen_clip"])
        self.assertEqual(self.key_event(ord("C")), 73)
        self.single_shot.assert_not_called()

    def test_pressed_keyboard_release_clears_state_even_if_recorder_gains_focus(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.modifiers.return_value = module.MOD_ALT
        self.assertEqual(self.key_event(ord("C")), 1)
        self.editor.return_value = Mock()
        self.assertEqual(self.key_event(ord("C"), message=module.WM_SYSKEYUP), 1)
        self.assertFalse(self.window.hotkey_pressed_states["screen_clip"])
        self.run_queued_actions()
        self.assert_no_actions()

    def test_altgr_matcher_is_distinct_from_control_alt(self):
        self.modifiers.return_value = module.MOD_ALTGR
        self.assertTrue(self.window._current_modifiers_match(module.MOD_ALTGR))
        self.assertFalse(self.window._current_modifiers_match(module.MOD_CONTROL | module.MOD_ALT))
        self.modifiers.return_value = module.MOD_CONTROL | module.MOD_ALT
        self.assertFalse(self.window._current_modifiers_match(module.MOD_ALTGR))

    def test_mouse_binding_can_dispatch_each_existing_action(self):
        for action in ("type_out", "screen_clip", "quick_chat"):
            with self.subTest(action=action):
                self.window = hotkey_window({action: (0, 0x06)})
                self.assertEqual(self.mouse_event(2), 1)
                self.run_queued_actions()
                getattr(self.window, f"_trigger_{action}_hotkey").assert_called_once_with()

    def test_mouse_hook_install_retains_callback_and_avoids_duplicate_hook(self):
        self.window.mouse_hook_handle = None
        self.window.mouse_hook_callback = None
        self.native.SetWindowsHookExW.return_value = 789
        self.window._install_mouse_hook()
        self.assertEqual(self.window.mouse_hook_handle, 789)
        self.assertIsNotNone(self.window.mouse_hook_callback)
        self.native.SetWindowsHookExW.assert_called_once_with(
            module.WH_MOUSE_LL, self.window.mouse_hook_callback, 1000, 0
        )
        self.window._install_mouse_hook()
        self.native.SetWindowsHookExW.assert_called_once()

    def test_failed_mouse_hook_prunes_only_mouse_actions_and_allows_retry(self):
        self.window = hotkey_window({
            "screen_clip": (0, 0x05), "quick_chat": (module.MOD_ALT, 0x06),
            "type_out": (module.MOD_ALT, ord("V")),
        })
        self.window.mouse_hook_handle = None
        self.native.SetWindowsHookExW.return_value = 0
        self.window._install_mouse_hook()
        self.assertEqual(self.window.registered_hotkeys, {"type_out": (module.MOD_ALT, ord("V"))})
        self.assertEqual(self.window.registered_hotkey_primary_keys, {ord("V")})
        self.assertEqual(self.window.hotkey_pressed_states, {"type_out": False})
        self.assertEqual(set(self.window.hotkey_errors), {"screen_clip", "quick_chat"})
        self.assertIn("5", self.window.hotkey_errors["screen_clip"])
        self.assertIsNone(self.window.mouse_hook_handle)
        self.assertIsNone(self.window.mouse_hook_callback)
        self.assertEqual(self.window.keyboard_hook_handle, 123)
        self.native.SetWindowsHookExW.return_value = 999
        self.window._install_mouse_hook()
        self.assertEqual(self.native.SetWindowsHookExW.call_count, 2)
        self.assertEqual(self.window.mouse_hook_handle, 999)

    def test_keyboard_only_bindings_still_install_mouse_hook_for_recording(self):
        self.window = hotkey_window({"screen_clip": (module.MOD_ALT, ord("C"))})
        self.window.mouse_hook_handle = None
        self.native.SetWindowsHookExW.return_value = 888
        self.window._update_keyboard_hook_state()
        self.native.SetWindowsHookExW.assert_called_once()
        self.assertEqual(self.native.SetWindowsHookExW.call_args.args[0], module.WH_MOUSE_LL)
        self.assertEqual(self.window.mouse_hook_handle, 888)

    def test_recording_installs_mouse_hook_even_with_all_actions_disabled(self):
        self.window = hotkey_window({})
        self.window.hotkey_system_integration_enabled = True
        self.window.mouse_hook_handle = None
        self.editor.return_value = Mock()
        self.native.SetWindowsHookExW.return_value = 888
        self.window._update_keyboard_hook_state()
        self.assertIsNone(self.window.keyboard_hook_handle)
        self.assertEqual(self.window.mouse_hook_handle, 888)
        self.assertEqual(self.native.SetWindowsHookExW.call_args.args[0], module.WH_MOUSE_LL)
        self.assertEqual(self.mouse_event(), 1)
        self.run_queued_actions()
        self.editor.return_value.record_mouse_button.assert_called_once_with(0x05, 0)
        self.assert_no_actions()

    def test_recording_hook_survives_focus_loss_until_mouse_release(self):
        self.window = hotkey_window({})
        self.window.hotkey_system_integration_enabled = True
        self.window.mouse_recording_buttons.add((0x05, False))
        self.window._update_keyboard_hook_state()
        self.assertEqual(self.window.mouse_hook_handle, 456)
        self.assertEqual(self.mouse_event(message=module.WM_XBUTTONUP), 1)
        self.run_queued_actions()
        self.assertIsNone(self.window.mouse_hook_handle)
        self.assertFalse(self.window.mouse_recording_buttons)
        self.assert_no_actions()

    def test_focus_never_enables_system_hooks_in_isolated_mode(self):
        self.window = hotkey_window({})
        self.editor.return_value = Mock()
        self.window._handle_hotkey_focus_changed(None, self.editor.return_value)
        self.single_shot.assert_not_called()
        self.window._update_keyboard_hook_state()
        self.native.SetWindowsHookExW.assert_not_called()
        self.assertIsNone(self.window.mouse_hook_handle)

    def test_normal_focus_change_refreshes_capture_hook(self):
        self.window.hotkey_system_integration_enabled = True
        self.window._handle_hotkey_focus_changed(None, None)
        self.single_shot.assert_called_once_with(0, self.window._update_keyboard_hook_state)

    def test_focusing_recorder_cancels_previous_screen_clip_permission(self):
        self.window.hotkey_system_integration_enabled = True
        self.window.screen_clip_hotkey_armed_until = 145.0
        self.editor.return_value = Mock()
        self.window._handle_hotkey_focus_changed(None, self.editor.return_value)
        self.assertEqual(self.window.screen_clip_hotkey_armed_until, 0.0)
        self.assert_no_actions()

    def test_held_primary_key_cannot_switch_actions_when_modifiers_change(self):
        self.window = hotkey_window({
            "type_out": (module.MOD_CONTROL, ord("C")),
            "screen_clip": (module.MOD_ALT, ord("C")),
        })
        self.modifiers.return_value = module.MOD_ALT
        self.assertEqual(self.key_event(ord("C")), 1)
        self.run_queued_actions()
        self.modifiers.return_value = module.MOD_CONTROL
        self.assertEqual(self.key_event(ord("C")), 1)
        self.single_shot.assert_not_called()
        self.window._trigger_type_out_hotkey.assert_not_called()
        self.window._trigger_screen_clip_hotkey.assert_called_once_with()
        self.assertEqual(self.key_event(ord("C"), message=module.WM_KEYUP), 1)
        self.assertEqual(self.key_event(ord("C")), 1)
        self.run_queued_actions()
        self.window._trigger_type_out_hotkey.assert_called_once_with()

    def test_unregister_clears_bindings_capture_and_both_hooks(self):
        self.window.screen_clip_hotkey_armed_until = 145.0
        self.window.mouse_recording_buttons = {(0x05, False), (0x06, False)}
        self.window._unregister_hotkeys()
        self.assertEqual(self.window.screen_clip_hotkey_armed_until, 0.0)
        self.assertEqual(self.window.registered_hotkeys, {})
        self.assertEqual(self.window.registered_hotkey_primary_keys, set())
        self.assertEqual(self.window.hotkey_pressed_states, {})
        self.assertEqual(self.window.mouse_recording_buttons, set())
        self.assertIsNone(self.window.keyboard_hook_handle)
        self.assertIsNone(self.window.mouse_hook_handle)
        self.assertIsNone(self.window.keyboard_hook_callback)
        self.assertIsNone(self.window.mouse_hook_callback)
        self.assertEqual(self.native.UnhookWindowsHookEx.call_args_list, [call(123), call(456)])
        self.window._unregister_hotkeys()
        self.assertEqual(self.native.UnhookWindowsHookEx.call_count, 2)

    def test_mouse_hook_cleanup_clears_recording_even_without_native_handle(self):
        self.window.mouse_hook_handle = None
        self.window.mouse_recording_buttons = {(0x05, False)}
        self.window._uninstall_mouse_hook()
        self.assertEqual(self.window.mouse_recording_buttons, set())
        self.assertIsNone(self.window.mouse_hook_callback)
        self.native.UnhookWindowsHookEx.assert_not_called()


class HookCloseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_actual_close_removes_both_hooks_without_building_browser(self):
        class CleanupWindow(MainWindow):
            def __init__(self):
                QMainWindow.__init__(self)
                state = hotkey_window()
                for name, value in vars(state).items():
                    if not name.startswith("_"):
                        setattr(self, name, value)
                self.exit_requested = True
                self.tray_icon = None
                self.store = Mock()
                self._read_settings_from_form = Mock(return_value=SimpleNamespace())
                self._restore_system_sleep_state = Mock()
                self._shutdown_background_executor = Mock()
                self.browser_background_host = Mock()
                self.translation_overlay = Mock()
                self.quick_chat_overlay = Mock()

        with patch.object(module, "user32", Mock()) as native:
            window = CleanupWindow()
            window.mouse_recording_buttons = {(0x06, False)}
            event = QCloseEvent()
            MainWindow.closeEvent(window, event)
            self.assertTrue(event.isAccepted())
            self.assertEqual(native.UnhookWindowsHookEx.call_args_list, [call(123), call(456)])
            self.assertIsNone(window.keyboard_hook_handle)
            self.assertIsNone(window.mouse_hook_handle)
            self.assertEqual(window.mouse_recording_buttons, set())
            window.store.save_settings.assert_called_once()
            window.browser_background_host.close.assert_called_once_with()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == "__main__":
    unittest.main()
