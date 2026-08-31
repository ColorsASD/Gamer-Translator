"""A saját képkivágási gyorsbillentyű engedélyei, valódi vágólap és küldés nélkül."""
from __future__ import annotations

import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow


def capture_window() -> SimpleNamespace:
    settings = SimpleNamespace(
        monitoring_enabled=True,
        screen_clip_hotkey_enabled=True,
        screen_clip_hotkey="Alt+C",
        copy_response_to_clipboard=False,
    )
    window = SimpleNamespace(
        settings=settings,
        clipboard=SimpleNamespace(Mode=SimpleNamespace(Clipboard=0, Selection=1)),
        clipboard_translation_in_progress=False,
        browser_interaction_active=False,
        clipboard_translation_heartbeat_monotonic=0.0,
        clipboard_debounce_timer=Mock(),
        pending_clipboard_payload=None,
        last_seen_image_signature="",
        screen_clip_hotkey_armed_until=0.0,
        hotkey_errors={},
        registered_hotkeys={"screen_clip": (module.MOD_ALT, ord("C"))},
        registered_hotkey_primary_keys={ord("C")},
        hotkey_pressed_states={},
        suppressed_hotkey_presses={},
        hotkey_generation=0,
        keyboard_hook_handle=123,
        _read_settings_from_form=Mock(return_value=settings),
        _read_clipboard_image_payload=Mock(return_value={"imageSignature": "kép-1"}),
        _process_clipboard_translation=Mock(),
        _set_live_status=Mock(),
        _save_last_run_status=Mock(),
        _update_keyboard_hook_state=Mock(),
        _handle_hotkey_keydown=Mock(return_value=False),
        _handle_hotkey_keyup=Mock(return_value=False),
        _current_modifiers_match=Mock(return_value=False),
    )
    for name in (
        "_arm_screen_clip_hotkey", "_clear_screen_clip_hotkey_arm", "_is_screen_clip_hotkey_armed",
        "_handle_clipboard_changed", "_poll_clipboard", "_trigger_screen_clip_hotkey",
    ):
        setattr(window, name, getattr(MainWindow, name).__get__(window, SimpleNamespace))
    return window


class CapturePermissionTests(unittest.TestCase):
    def setUp(self):
        self.window = capture_window()
        self.clock = patch.object(module.time, "monotonic", return_value=100.0).start()
        self.addCleanup(patch.stopall)

    def receive_image(self, signature="kép-1"):
        payload = {"imageSignature": signature}
        self.window._read_clipboard_image_payload.return_value = payload
        self.window._handle_clipboard_changed(self.window.clipboard.Mode.Clipboard)
        return payload

    def test_unarmed_clipboard_image_is_not_read_or_sent(self):
        self.receive_image()
        self.window._poll_clipboard()
        self.window._read_clipboard_image_payload.assert_not_called()
        self.window._process_clipboard_translation.assert_not_called()
        self.assertIsNone(self.window.pending_clipboard_payload)

    def test_unarmed_image_is_ignored_during_running_translation(self):
        self.window.clipboard_translation_in_progress = True
        self.receive_image()
        self.assertIsNone(self.window.pending_clipboard_payload)
        self.window._read_clipboard_image_payload.assert_not_called()

    def test_armed_image_is_captured_and_sent_once(self):
        self.window._arm_screen_clip_hotkey()
        payload = self.receive_image()
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.assertIs(self.window.pending_clipboard_payload, payload)
        self.window._process_clipboard_translation.assert_not_called()
        self.window.clipboard_debounce_timer.start.assert_called_once()
        self.window._poll_clipboard()
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(payload)
        self.assertIsNone(self.window.pending_clipboard_payload)

    def test_next_unarmed_image_cannot_replace_captured_payload(self):
        self.window._arm_screen_clip_hotkey()
        own_payload = self.receive_image("saját")
        self.receive_image("idegen")
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(own_payload)
        self.assertEqual(self.window._read_clipboard_image_payload.call_count, 1)

    def test_poll_does_not_read_later_clipboard_contents(self):
        self.window._arm_screen_clip_hotkey()
        payload = self.receive_image()
        self.window._read_clipboard_image_payload.side_effect = AssertionError("Későbbi vágólapolvasás")
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(payload)

    def test_old_debounce_cannot_claim_existing_image_after_arming(self):
        self.receive_image("régi")
        self.window._arm_screen_clip_hotkey()
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_not_called()
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())
        own_payload = self.receive_image("új")
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(own_payload)

    def test_repeated_image_requires_and_accepts_new_permission(self):
        self.window.last_seen_image_signature = "azonos"
        for _ in range(2):
            self.window._arm_screen_clip_hotkey()
            payload = self.receive_image("azonos")
            self.window._poll_clipboard()
            self.window._process_clipboard_translation.assert_called_with(payload)
        self.assertEqual(self.window._process_clipboard_translation.call_count, 2)
        self.receive_image("azonos")
        self.window._poll_clipboard()
        self.assertEqual(self.window._process_clipboard_translation.call_count, 2)

    def test_other_clipboard_mode_does_not_consume_permission(self):
        self.window._arm_screen_clip_hotkey()
        self.window._handle_clipboard_changed(self.window.clipboard.Mode.Selection)
        self.window._read_clipboard_image_payload.assert_not_called()
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())

    def test_nonimage_event_does_not_consume_permission(self):
        self.window._arm_screen_clip_hotkey()
        self.window._read_clipboard_image_payload.return_value = None
        self.window._handle_clipboard_changed(self.window.clipboard.Mode.Clipboard)
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())
        self.assertIsNone(self.window.pending_clipboard_payload)
        self.window.clipboard_debounce_timer.start.assert_not_called()

    def test_expired_permission_does_not_read_image(self):
        self.window._arm_screen_clip_hotkey()
        self.clock.return_value = 100.0 + module.SCREEN_CLIP_ARM_TIMEOUT_SECONDS
        self.receive_image()
        self.window._poll_clipboard()
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.window._read_clipboard_image_payload.assert_not_called()
        self.window._process_clipboard_translation.assert_not_called()

    def test_captured_image_survives_permission_timeout_during_browser_work(self):
        self.window._arm_screen_clip_hotkey()
        self.window.browser_interaction_active = True
        payload = self.receive_image()
        self.window._poll_clipboard()
        self.assertIs(self.window.pending_clipboard_payload, payload)
        self.window._process_clipboard_translation.assert_not_called()
        self.clock.return_value = 1000.0
        self.window.browser_interaction_active = False
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(payload)

    def test_running_translation_preserves_authorized_pending_image(self):
        self.window.clipboard_translation_in_progress = True
        self.window._arm_screen_clip_hotkey()
        own_payload = self.receive_image("saját")
        self.receive_image("idegen")
        self.window._poll_clipboard()
        self.assertIs(self.window.pending_clipboard_payload, own_payload)
        self.window._process_clipboard_translation.assert_not_called()
        self.window.clipboard_translation_in_progress = False
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(own_payload)

    def test_disabled_capture_settings_reject_image(self):
        for setting in ("monitoring_enabled", "screen_clip_hotkey_enabled"):
            with self.subTest(setting=setting):
                self.window = capture_window()
                self.window._arm_screen_clip_hotkey()
                setattr(self.window.settings, setting, False)
                self.receive_image()
                self.window._poll_clipboard()
                self.window._process_clipboard_translation.assert_not_called()
                self.assertIsNone(self.window.pending_clipboard_payload)
                self.assertFalse(self.window._is_screen_clip_hotkey_armed())

    def test_unregister_hotkeys_clears_pending_permission(self):
        self.window._arm_screen_clip_hotkey()
        MainWindow._unregister_hotkeys(self.window)
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.assertEqual(self.window.registered_hotkeys, {})
        self.window._update_keyboard_hook_state.assert_called_once()

    def test_trigger_arms_before_launching_snipping_tool(self):
        def launch(uri):
            self.assertEqual(uri, "ms-screenclip:")
            self.assertTrue(self.window._is_screen_clip_hotkey_armed())
        with patch.object(module.os, "startfile", side_effect=launch) as start:
            self.window._trigger_screen_clip_hotkey()
        start.assert_called_once_with("ms-screenclip:")
        self.window._read_settings_from_form.assert_called_once()

    def test_failed_snipping_tool_launch_clears_permission(self):
        with patch.object(module.os, "startfile", side_effect=OSError("Teszt indítási hiba")):
            self.window._trigger_screen_clip_hotkey()
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.receive_image()
        self.window._process_clipboard_translation.assert_not_called()

    def test_disabled_settings_do_not_launch_snipping_tool(self):
        for setting in ("monitoring_enabled", "screen_clip_hotkey_enabled"):
            with self.subTest(setting=setting):
                self.window = capture_window()
                setattr(self.window.settings, setting, False)
                with patch.object(module.os, "startfile") as start:
                    self.window._trigger_screen_clip_hotkey()
                start.assert_not_called()
                self.assertFalse(self.window._is_screen_clip_hotkey_armed())

    def test_hotkey_error_does_not_launch_snipping_tool(self):
        self.window.hotkey_errors["screen_clip"] = "Teszt gyorsbillentyűhiba"
        with patch.object(module.os, "startfile") as start:
            self.window._trigger_screen_clip_hotkey()
        start.assert_not_called()
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())


class CaptureCancellationTests(unittest.TestCase):
    def setUp(self):
        self.window = capture_window()
        self.window._arm_screen_clip_hotkey()
        self.native = patch.object(module, "user32", Mock()).start()
        self.native.CallNextHookEx.return_value = 73
        self.addCleanup(patch.stopall)

    def key_event(self, key, *, message=None, flags=0, n_code=None, extra_info=0):
        event = module.KBDLLHOOKSTRUCT()
        event.vkCode = key
        event.flags = flags
        event.dwExtraInfo = extra_info
        return MainWindow._keyboard_hook_proc(
            self.window,
            module.HC_ACTION if n_code is None else n_code,
            module.WM_KEYDOWN if message is None else message,
            ctypes.pointer(event),
        )

    def test_escape_cancels_permission_without_swallowing_key(self):
        self.assertEqual(self.key_event(0x1B), 73)
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.native.CallNextHookEx.assert_called_once()

    def test_windows_snipping_shortcut_cancels_permission_without_swallowing_key(self):
        self.window._current_modifiers_match.side_effect = lambda modifiers: modifiers == (module.MOD_WIN | module.MOD_SHIFT)
        self.assertEqual(self.key_event(ord("S")), 73)
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())
        self.native.CallNextHookEx.assert_called_once()
        self.window._handle_clipboard_changed(self.window.clipboard.Mode.Clipboard)
        self.window._read_clipboard_image_payload.assert_not_called()

    def test_ordinary_s_does_not_cancel_permission(self):
        self.assertEqual(self.key_event(ord("S")), 73)
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())

    def test_own_injected_cancel_key_does_not_change_permission(self):
        for key in (0x1B, ord("S")):
            with self.subTest(key=key):
                self.assertEqual(self.key_event(key, flags=module.LLKHF_INJECTED, extra_info=module.OWN_INPUT_MARKER), 73)
                self.assertTrue(self.window._is_screen_clip_hotkey_armed())
        self.window._handle_hotkey_keydown.assert_not_called()

    def test_external_injected_escape_cancels_permission(self):
        self.assertEqual(self.key_event(0x1B, flags=module.LLKHF_INJECTED), 73)
        self.assertFalse(self.window._is_screen_clip_hotkey_armed())

    def test_escape_keyup_does_not_cancel_permission(self):
        self.assertEqual(self.key_event(0x1B, message=module.WM_KEYUP), 73)
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())

    def test_nonaction_hook_event_does_not_change_permission(self):
        self.assertEqual(self.key_event(0x1B, n_code=-1), 73)
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())

    def test_configured_shortcut_wins_over_windows_shortcut_cancellation(self):
        self.window.registered_hotkeys = {"screen_clip": (module.MOD_WIN | module.MOD_SHIFT, ord("S"))}
        self.window.registered_hotkey_primary_keys = {ord("S")}
        self.window._current_modifiers_match.return_value = True
        self.window._handle_hotkey_keydown.return_value = True
        self.assertEqual(self.key_event(ord("S")), 1)
        self.assertTrue(self.window._is_screen_clip_hotkey_armed())
        self.native.CallNextHookEx.assert_not_called()

    def test_cancellation_does_not_discard_previously_authorized_image(self):
        payload = {"imageSignature": "korábban-engedélyezett"}
        self.window.pending_clipboard_payload = payload
        self.key_event(0x1B)
        self.window._poll_clipboard()
        self.window._process_clipboard_translation.assert_called_once_with(payload)


class CaptureCleanupTests(unittest.TestCase):
    def test_translation_cleanup_reschedules_only_authorized_pending_image(self):
        for pending in (None, {"imageSignature": "azonos"}):
            with self.subTest(pending=pending):
                window = capture_window()
                window.pending_clipboard_payload = pending
                window.last_seen_image_signature = "azonos"
                window._touch_clipboard_translation_heartbeat = Mock()
                window._begin_browser_interaction = Mock()
                window._show_loading_overlay = Mock()
                window._ensure_chatgpt_page_loaded = Mock(side_effect=RuntimeError("Teszt küldési hiba"))
                window._hide_translation_overlay = Mock()
                window._end_browser_interaction = Mock()
                with patch.object(module.QTimer, "singleShot") as single_shot:
                    MainWindow._process_clipboard_translation(window, {"imageSignature": "első"})
                self.assertFalse(window.clipboard_translation_in_progress)
                self.assertIs(window.pending_clipboard_payload, pending)
                if pending is None:
                    window.clipboard_debounce_timer.start.assert_not_called()
                else:
                    window.clipboard_debounce_timer.start.assert_called_once()
                single_shot.assert_not_called()


if __name__ == "__main__":
    unittest.main()
