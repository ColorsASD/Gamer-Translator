"""Alt+V regressziók kizárólag mockolt Windows bevitel és mesterséges fordítás mellett."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow


class NativeTypingTests(unittest.TestCase):
    def setUp(self):
        self.native = Mock()
        self.native.GetForegroundWindow.return_value = 111
        self.native.GetAsyncKeyState.return_value = 0
        self.native.GetKeyState.return_value = 0
        self.native.GetWindowThreadProcessId.return_value = 9
        self.native.GetKeyboardLayout.return_value = 0x040E040E
        self.native.VkKeyScanExW.side_effect = lambda character, layout: ord(character.upper())
        self.native.MapVirtualKeyExW.side_effect = lambda key, mode, layout: key
        self.native.MapVirtualKeyW.side_effect = lambda key, mode: key
        self.native.SendInput.side_effect = lambda count, inputs, size: count
        self.kernel = Mock()
        self.kernel.GetLastError.return_value = 5
        self.queued = []
        self.patch(module, "user32", self.native)
        self.patch(module, "kernel32", self.kernel)
        self.patch(module, "active_hotkey_editor", Mock(return_value=None))
        self.logs = self.patch(module, "log_event", Mock())
        self.events = self.patch(module.QGuiApplication, "processEvents", Mock())
        self.patch(module.QTimer, "singleShot", Mock(side_effect=lambda delay, callback: self.queued.append(callback)))
        self.patch(module.time, "sleep", Mock())

    def patch(self, target, name, replacement):
        patcher = patch.object(target, name, replacement)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def window(self, text="ab"):
        window = SimpleNamespace(
            last_translated_text=text, latest_translation_request_id="a" * 32,
            translation_result_request_id="a" * 32, translation_result_complete=True,
            hotkey_errors={}, settings=SimpleNamespace(type_out_hotkey="Alt+V"),
            registered_hotkeys={"type_out": (module.MOD_ALT, ord("V"))},
            suppressed_hotkey_presses={}, hotkey_pressed_states={}, hotkey_generation=3,
            hotkey_action_running=False, pending_hotkey_actions=[], _current_modifiers_match=lambda value: True,
            _mask_hotkey_modifier_menu=Mock(), _set_live_status=Mock(),
            _wait_for_modifier_release=Mock(return_value=True),
        )
        for name in ("_handle_hotkey_keydown", "_trigger_hotkey_action", "_trigger_type_out_hotkey", "_type_cached_text_via_hotkey"):
            setattr(window, name, getattr(MainWindow, name).__get__(window, SimpleNamespace))
        return window

    def event(self, name):
        return next(call.kwargs for call in self.logs.call_args_list if call.args[0] == name)

    def test_hook_snapshot_does_not_retarget_after_gui_callback_delay(self):
        window = self.window()
        self.assertTrue(window._handle_hotkey_keydown(ord("V")))
        self.native.GetForegroundWindow.assert_called_once_with()
        self.native.GetForegroundWindow.return_value = 222
        self.queued.pop(0)()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.cancelled")["reason"], "focus_changed")

    def test_callback_does_not_type_a_replacement_translation(self):
        window = self.window()
        window._handle_hotkey_keydown(ord("V"))
        window.last_translated_text = "abcd"
        self.queued.pop(0)()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.rejected")["reason"], "translation_changed")

    def test_null_foreground_at_hook_is_not_retargeted_later(self):
        window = self.window()
        self.native.GetForegroundWindow.return_value = 0
        window._handle_hotkey_keydown(ord("V"))
        self.native.GetForegroundWindow.return_value = 111
        self.queued.pop(0)()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.rejected")["reason"], "no_foreground")

    def test_same_request_cache_change_is_cancelled_before_next_character(self):
        window = self.window()
        calls = 0

        def update(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                window.last_translated_text = "abcd"

        self.events.side_effect = update
        window._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 1)
        self.assertEqual(self.event("typing.cancelled")["reason"], "translation_changed")
        self.assertEqual(self.event("typing.cancelled")["count"], 1)
        self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))

    def test_new_request_during_modifier_wait_does_not_start_or_report_old_request_complete(self):
        window = self.window()

        def update():
            window.latest_translation_request_id = "b" * 32
            window.translation_result_request_id = "b" * 32
            window.last_translated_text = "cd"
            return True

        window._wait_for_modifier_release.side_effect = update
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.cancelled")["reason"], "new_request")
        self.assertEqual(self.event("typing.cancelled")["request_id"], "a" * 32)

    def test_pending_partial_response_cannot_be_typed(self):
        window = self.window()
        window.translation_result_complete = False
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.rejected")["reason"], "response_pending")

    def test_modifier_timeout_has_status_and_explicit_diagnostic(self):
        window = self.window()
        window._wait_for_modifier_release.return_value = False
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        record = self.event("typing.rejected")
        self.assertEqual(record["reason"], "modifier_timeout")
        self.assertEqual(record["timeout_ms"], 1200)
        self.assertIn("módosító", window._set_live_status.call_args.args[0])

    def test_modifier_pressed_after_initial_wait_cancels_injection(self):
        window = self.window()
        self.events.side_effect = lambda *args: setattr(self.native.GetAsyncKeyState, "return_value", 0x8000)
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.cancelled")["reason"], "modifier_pressed")

    def test_typing_uses_foreground_thread_layout_for_virtual_key_and_scan_code(self):
        window = self.window("z")
        self.native.GetKeyboardLayout.side_effect = lambda thread: 0x040E040E if thread == 9 else 0x04090409
        self.native.VkKeyScanExW.return_value = ord("Z")
        self.native.VkKeyScanExW.side_effect = None
        self.native.MapVirtualKeyExW.return_value = 0x15
        self.native.MapVirtualKeyExW.side_effect = None
        window._trigger_type_out_hotkey()
        self.native.GetWindowThreadProcessId.assert_called_with(111, None)
        self.native.GetKeyboardLayout.assert_called_with(9)
        self.native.VkKeyScanExW.assert_called_once_with("z", 0x040E040E)
        self.native.MapVirtualKeyExW.assert_any_call(ord("Z"), module.MAPVK_VK_TO_VSC, 0x040E040E)
        self.native.MapVirtualKeyW.assert_not_called()
        self.assertEqual(self.native.SendInput.call_args.args[1][0].ki.wScan, 0x15)

    def test_unknown_target_layout_uses_unicode_instead_of_caller_layout(self):
        window = self.window("z")
        self.native.GetWindowThreadProcessId.return_value = 0
        window._trigger_type_out_hotkey()
        self.native.GetKeyboardLayout.assert_not_called()
        self.native.VkKeyScanExW.assert_not_called()
        inputs = self.native.SendInput.call_args.args[1]
        self.assertTrue(inputs[0].ki.dwFlags & module.KEYEVENTF_UNICODE)

    def test_blocked_input_reports_error_code_without_claiming_completion(self):
        window = self.window("a")
        self.native.SendInput.side_effect = None
        self.native.SendInput.return_value = 0
        window._trigger_type_out_hotkey()
        record = self.event("typing.input_rejected")
        self.assertEqual(record["level"], "ERROR")
        self.assertEqual(record["reason"], "blocked_input")
        self.assertEqual(record["code"], 5)
        self.assertEqual(record["count"], 0)
        self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))

    def test_partial_input_releases_only_keys_that_were_actually_pressed(self):
        window = self.window("A")
        self.native.VkKeyScanExW.side_effect = None
        self.native.VkKeyScanExW.return_value = 0x0141
        self.native.SendInput.side_effect = [1, 1]
        window._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 2)
        count, releases, _ = self.native.SendInput.call_args.args
        self.assertEqual(count, 1)
        self.assertEqual(releases[0].ki.wScan, module.VK_SHIFT)
        self.assertTrue(releases[0].ki.dwFlags & module.KEYEVENTF_KEYUP)
        self.assertEqual(self.event("typing.input_rejected")["reason"], "partial_input")

    def test_completed_metadata_reports_exact_immutable_snapshot(self):
        window = self.window("ab")
        window._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 2)
        self.assertEqual(self.event("typing.started")["request_id"], "a" * 32)
        self.assertEqual(self.event("typing.completed")["request_id"], "a" * 32)
        self.assertEqual(self.event("typing.completed")["text_length"], 2)

    def test_same_process_target_reads_key_events_and_flushes_last_character(self):
        window = self.window("A🎮")
        with patch.object(module, "_typing_event_flags", return_value=module.QEventLoop.ProcessEventsFlag.AllEvents):
            window._trigger_type_out_hotkey()
        self.assertEqual(self.events.call_count, 3)
        for call in self.events.call_args_list:
            self.assertEqual(call.args, (module.QEventLoop.ProcessEventsFlag.AllEvents,))
        self.assertEqual(self.event("typing.started")["mode"], "same_process")
        self.assertEqual(self.native.SendInput.call_count, 2)

    def test_external_process_target_keeps_existing_event_filter(self):
        window = self.window("ab")
        window._trigger_type_out_hotkey()
        self.assertEqual(self.events.call_count, 2)
        for call in self.events.call_args_list:
            self.assertEqual(call.args, (module.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents,))
        self.assertEqual(self.event("typing.started")["mode"], "external_process")

    def test_event_flags_compare_real_pid_from_output_pointer(self):
        def window_thread(hwnd, process_pointer):
            process_pointer._obj.value = os.getpid()
            return 9

        self.native.GetWindowThreadProcessId.side_effect = window_thread
        self.assertEqual(module._typing_event_flags(111), module.QEventLoop.ProcessEventsFlag.AllEvents)
        self.native.GetWindowThreadProcessId.side_effect = OSError("synthetic failure")
        self.assertEqual(module._typing_event_flags(111), module.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def test_last_error_is_reset_immediately_before_native_submission(self):
        order = []
        self.kernel.SetLastError.side_effect = lambda code: order.append(("reset", code))
        self.native.SendInput.side_effect = lambda count, inputs, size: order.append(("send", count)) or count
        self.window("a")._trigger_type_out_hotkey()
        self.assertEqual(order, [("reset", 0), ("send", 2)])

    def test_release_failure_is_logged_and_retried_only_once(self):
        self.native.VkKeyScanExW.side_effect = None
        self.native.VkKeyScanExW.return_value = 0x0141
        self.native.SendInput.side_effect = [1, 0, 0]
        self.window("A")._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 3)
        failures = [call.kwargs for call in self.logs.call_args_list if call.args[0] == "typing.release_rejected"]
        self.assertEqual([entry["attempt"] for entry in failures], [1, 2])
        self.assertTrue(all(entry["pending_count"] == 1 and entry["code"] == 5 for entry in failures))
        self.assertEqual(self.kernel.SetLastError.call_count, 3)
        self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))

    def test_partial_cleanup_retries_only_unreleased_suffix(self):
        self.native.VkKeyScanExW.side_effect = None
        self.native.VkKeyScanExW.return_value = 0x0141
        self.native.SendInput.side_effect = [2, 1, 1]
        self.window("A")._trigger_type_out_hotkey()
        cleanup, retry = self.native.SendInput.call_args_list[1:]
        self.assertEqual(cleanup.args[0], 2)
        self.assertEqual(retry.args[0], 1)
        self.assertEqual(retry.args[1][0].ki.wScan, module.VK_SHIFT)
        self.assertTrue(retry.args[1][0].ki.dwFlags & module.KEYEVENTF_KEYUP)

    def test_caps_lock_telemetry_explicitly_identifies_callers_queue(self):
        self.native.GetKeyState.return_value = 1
        self.window("a")._trigger_type_out_hotkey()
        record = self.event("typing.keyboard_state")
        self.assertTrue(record["enabled"])
        self.assertEqual(record["kind"], "caps_lock")
        self.assertEqual(record["source"], "caller_queue")

    def test_explicit_caps_lock_preserves_hungarian_letter_case_with_unicode(self):
        for character in "ÁrvíztűrőTÜKÖRFÚRÓGÉP":
            with self.subTest(character=character):
                inputs = module.build_character_inputs(character, keyboard_layout=0x040E040E, caps_lock=True)
                self.assertEqual(len(inputs), 2)
                self.assertTrue(all(entry.ki.dwFlags & module.KEYEVENTF_UNICODE for entry in inputs))
                self.assertEqual(inputs[0].ki.wScan, ord(character))
                self.assertTrue(inputs[1].ki.dwFlags & module.KEYEVENTF_KEYUP)
                self.assertTrue(all(entry.ki.dwExtraInfo == module.OWN_INPUT_MARKER for entry in inputs))
        self.native.GetKeyState.assert_not_called()
        self.native.VkKeyScanExW.assert_not_called()

    def test_explicit_caps_lock_off_keeps_existing_scan_code_path(self):
        self.native.GetKeyState.return_value = 1
        inputs = module.build_character_inputs("A", keyboard_layout=0x040E040E, caps_lock=False)
        self.assertTrue(inputs[0].ki.dwFlags & module.KEYEVENTF_SCANCODE)
        self.assertFalse(inputs[0].ki.dwFlags & module.KEYEVENTF_UNICODE)
        self.native.GetKeyState.assert_not_called()
        self.native.VkKeyScanExW.assert_called_once_with("A", 0x040E040E)

    def test_caps_lock_does_not_switch_punctuation_or_modify_toggle(self):
        inputs = module.build_character_inputs("!", keyboard_layout=0x040E040E, caps_lock=True)
        self.assertFalse(inputs[0].ki.dwFlags & module.KEYEVENTF_UNICODE)
        self.native.VkKeyScanExW.assert_called_once_with("!", 0x040E040E)
        self.native.SendInput.assert_not_called()

    def test_default_caps_lock_reads_toggle_bit_and_preserves_existing_emoji_path(self):
        for state, expected_unicode in ((0, False), (0x8000, False), (1, True), (-32767, True)):
            with self.subTest(state=state):
                self.native.GetKeyState.return_value = state
                inputs = module.build_character_inputs("a", keyboard_layout=0x040E040E)
                self.assertEqual(bool(inputs[0].ki.dwFlags & module.KEYEVENTF_UNICODE), expected_unicode)
        self.native.GetKeyState.assert_called_with(0x14)
        inputs = module.build_character_inputs("🎮", keyboard_layout=0x040E040E, caps_lock=True)
        self.assertEqual(len(inputs), 4)
        self.assertTrue(all(entry.ki.dwFlags & module.KEYEVENTF_UNICODE for entry in inputs))

    def test_caps_lock_change_during_typing_is_rechecked_before_next_letter(self):
        self.native.GetKeyState.side_effect = [0, 1]
        self.window("ab")._trigger_type_out_hotkey()
        first, second = self.native.SendInput.call_args_list
        self.assertTrue(first.args[1][0].ki.dwFlags & module.KEYEVENTF_SCANCODE)
        self.assertTrue(second.args[1][0].ki.dwFlags & module.KEYEVENTF_UNICODE)
        records = [call.kwargs for call in self.logs.call_args_list if call.args[0] == "typing.keyboard_state"]
        self.assertEqual([record["enabled"] for record in records], [False, True])

    def test_shutdown_already_requested_rejects_typing_without_touching_widgets(self):
        for field in ("operations_cancelled", "exit_requested"):
            with self.subTest(field=field):
                self.logs.reset_mock()
                window = self.window()
                setattr(window, field, True)
                window._trigger_type_out_hotkey()
                self.assertEqual(self.event("typing.rejected")["reason"], "shutdown")
                window._wait_for_modifier_release.assert_not_called()
                window._set_live_status.assert_not_called()
        self.native.SendInput.assert_not_called()

    def test_shutdown_during_typing_stops_before_next_character_without_success_status(self):
        for field in ("operations_cancelled", "exit_requested"):
            with self.subTest(field=field):
                self.logs.reset_mock()
                self.native.SendInput.reset_mock()
                window = self.window()
                calls = []

                def shutdown(*args):
                    calls.append(1)
                    if len(calls) == 2:
                        setattr(window, field, True)

                self.events.side_effect = shutdown
                window._trigger_type_out_hotkey()
                self.assertEqual(self.native.SendInput.call_count, 1)
                self.assertEqual(self.event("typing.cancelled")["reason"], "shutdown")
                self.assertEqual(self.event("typing.cancelled")["count"], 1)
                window._set_live_status.assert_not_called()
                self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))

    def test_shutdown_rejection_keeps_the_original_hook_request_snapshot(self):
        window = self.window()
        context = {"target_window": 111, "text": "ab", "request_id": "a" * 32}
        window.latest_translation_request_id = "b" * 32
        window.operations_cancelled = True
        window._trigger_type_out_hotkey(typing_context=context)
        self.assertEqual(self.event("typing.rejected")["request_id"], "a" * 32)
        self.native.SendInput.assert_not_called()
        window._set_live_status.assert_not_called()

    def test_shutdown_during_modifier_wait_never_starts_native_typing(self):
        window = self.window()

        def shutdown():
            window.operations_cancelled = True
            return False

        window._wait_for_modifier_release.side_effect = shutdown
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        window._set_live_status.assert_not_called()
        self.assertEqual(self.event("typing.cancelled")["reason"], "shutdown")
        self.assertFalse(any(call.args[0] == "typing.started" for call in self.logs.call_args_list))

    def test_modifier_wait_returns_immediately_when_shutdown_is_requested(self):
        window = self.window()
        window.operations_cancelled = True
        self.assertFalse(MainWindow._wait_for_modifier_release(window))
        self.native.GetAsyncKeyState.assert_not_called()
        self.events.assert_not_called()

    def test_hotkey_generation_change_during_wait_rejects_old_activation(self):
        window = self.window()

        def reregister():
            window.hotkey_generation += 1
            return True

        window._wait_for_modifier_release.side_effect = reregister
        window._trigger_type_out_hotkey()
        self.native.SendInput.assert_not_called()
        self.assertEqual(self.event("typing.rejected")["reason"], "hotkey_changed")
        self.assertIn("gyorsbillentyű", window._set_live_status.call_args.args[0])

    def test_hotkey_generation_change_stops_active_typing(self):
        window = self.window()
        calls = []

        def reregister(*args):
            calls.append(1)
            if len(calls) == 2:
                window.hotkey_generation += 1

        self.events.side_effect = reregister
        window._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 1)
        self.assertEqual(self.event("typing.cancelled")["reason"], "hotkey_changed")
        self.assertIn("gyorsbillentyű", window._set_live_status.call_args.args[0])
        self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))

    def test_shutdown_during_same_process_final_flush_does_not_report_completed(self):
        window = self.window("a")
        calls = []

        def shutdown(*args):
            calls.append(1)
            if len(calls) == 2:
                window.operations_cancelled = True

        self.events.side_effect = shutdown
        with patch.object(module, "_typing_event_flags", return_value=module.QEventLoop.ProcessEventsFlag.AllEvents):
            window._trigger_type_out_hotkey()
        self.assertEqual(self.native.SendInput.call_count, 1)
        self.assertEqual(self.event("typing.cancelled")["reason"], "shutdown")
        window._set_live_status.assert_not_called()
        self.assertFalse(any(call.args[0] == "typing.completed" for call in self.logs.call_args_list))


if __name__ == "__main__":
    unittest.main()
