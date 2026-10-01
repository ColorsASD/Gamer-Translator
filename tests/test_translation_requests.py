"""Fordítási kérések regressziói, éles vágólap és billentyűküldés nélkül."""
from __future__ import annotations

import os
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gamer_translator import main_window as module
from gamer_translator.main_window import MainWindow
from gamer_translator.settings_store import AppSettings


class TranslationRequestTests(unittest.TestCase):
    def test_timeout_invalidates_old_text_and_type_out_is_rejected(self):
        settings = AppSettings()
        window = SimpleNamespace(
            settings=settings, last_translated_text="Korábbi fordítás", store=Mock(),
            quick_chat_overlay=SimpleNamespace(hide_overlay=Mock(), show_error=Mock()),
            clipboard_translation_in_progress=False, browser_interaction_active=False,
            _read_settings_from_form=lambda: settings, _begin_browser_interaction=Mock(),
            _end_browser_interaction=Mock(), _show_loading_overlay=Mock(),
            _hide_translation_overlay=Mock(), _save_last_run_status=Mock(),
            _set_live_status=Mock(), _ensure_chatgpt_page_loaded=Mock(),
            _ensure_automation_ready=Mock(), _build_quick_chat_translation_prompt=lambda text: text,
            _build_response_progress_handler=lambda **kwargs: (Mock(), {"last_text": "", "notified": False}),
            _execute_delivery=Mock(side_effect=RuntimeError("A ChatGPT válasza nem érkezett meg időben.")),
            _store_translation_result=Mock(), _wait_for_modifier_release=Mock(return_value=True),
            _type_cached_text_via_hotkey=Mock(return_value=True), hotkey_errors={},
        )
        MainWindow._process_quick_chat_translation(window, "Új kérés")
        self.assertEqual(window.last_translated_text, "")
        window.store.save_last_translated_text.assert_called_once_with("")
        MainWindow._trigger_type_out_hotkey(window)
        window._type_cached_text_via_hotkey.assert_not_called()

    def test_obsolete_result_cannot_replace_latest_request(self):
        window = SimpleNamespace(latest_translation_request_id="2" * 32,
                                 last_translated_text="", store=Mock(), clipboard=Mock())
        MainWindow._store_translation_result(window, "Korábbi kérés válasza", copy_to_clipboard=True,
                                             show_overlay=False, play_sound=False, request_id="1" * 32)
        self.assertEqual(window.last_translated_text, "")
        window.store.save_last_translated_text.assert_not_called()
        window.clipboard.setText.assert_not_called()

    def test_obsolete_progress_cannot_store_or_notify(self):
        window = SimpleNamespace(latest_translation_request_id="2" * 32,
                                 _store_translation_result=Mock(), _save_last_run_status=Mock())
        handler, state = MainWindow._build_response_progress_handler(
            window, copy_to_clipboard=True, show_overlay=True, play_sound=True, request_id="1" * 32)
        handler({"kind": "assistant_response", "text": "Régi válasz"})
        window._store_translation_result.assert_not_called()
        self.assertFalse(state["notified"])

    def test_late_reply_is_still_polled_after_twenty_seconds_without_first_text(self):
        window = SimpleNamespace(
            response_followup_progress_call_id="followup", response_followup_request_id="1" * 32,
            latest_translation_request_id="1" * 32, response_followup_started_monotonic=100.0,
            response_followup_last_activity_monotonic=100.0,
            response_followup_waiting_for_first_response=True,
            _run_javascript=Mock(return_value=None), _stop_response_followup_polling=Mock(),
        )
        with patch.object(module.time, "monotonic", return_value=125.0):
            MainWindow._poll_response_followup_progress(window)
        window._run_javascript.assert_called_once()
        window._stop_response_followup_polling.assert_not_called()

    def test_new_request_stops_obsolete_late_watcher(self):
        window = SimpleNamespace(response_followup_progress_call_id="followup",
                                 response_followup_request_id="1" * 32,
                                 latest_translation_request_id="2" * 32,
                                 _run_javascript=Mock(), _stop_response_followup_polling=Mock())
        MainWindow._poll_response_followup_progress(window)
        window._stop_response_followup_polling.assert_called_once()
        window._run_javascript.assert_not_called()

    def test_final_late_response_is_delivered_before_watcher_stops(self):
        progress = {"kind": "assistant_response", "text": "A késői végleges válasz", "done": True, "complete": True, "seq": 2}
        observed = []
        window = SimpleNamespace(
            response_followup_progress_call_id="followup", response_followup_request_id="1" * 32,
            latest_translation_request_id="1" * 32, response_followup_started_monotonic=100.0,
            response_followup_last_activity_monotonic=100.0,
            response_followup_waiting_for_first_response=True, response_followup_last_sequence=0,
            response_followup_error_count=0,
            response_followup_handler=lambda value: observed.append(value["text"]),
            _run_javascript=Mock(return_value=json.dumps({"progress": json.dumps(progress), "diagnostics": []})),
            _stop_response_followup_polling=lambda **kwargs: observed.append("stopped"),
        )
        with patch.object(module.time, "monotonic", return_value=110.0):
            MainWindow._poll_response_followup_progress(window)
        self.assertEqual(observed, ["A késői végleges válasz", "stopped"])

    def test_late_watcher_keeps_background_host_active_without_keepalive_setting(self):
        window = SimpleNamespace(browser_interaction_active=False, page_loading=False,
                                 clipboard_translation_in_progress=False,
                                 response_followup_progress_call_id="active-followup",
                                 settings=SimpleNamespace(keep_chatgpt_in_background=False),
                                 _is_window_hidden_for_tray=lambda: True)
        self.assertTrue(MainWindow._should_use_background_browser_host(window))

    def test_screen_capture_hotkey_waits_while_other_action_runs(self):
        window = SimpleNamespace(registered_hotkeys={"screen_clip": (0, 1)}, hotkey_generation=7,
                                 hotkey_action_running=True, pending_hotkey_actions=[],
                                 _trigger_screen_clip_hotkey=Mock())
        with patch.object(module, "active_hotkey_editor", return_value=None):
            MainWindow._trigger_hotkey_action(window, "screen_clip", 7)
        self.assertEqual(window.pending_hotkey_actions, [("screen_clip", 7)])
        window._trigger_screen_clip_hotkey.assert_not_called()

    def test_queued_capture_does_not_run_after_hotkey_reconfiguration(self):
        window = SimpleNamespace(registered_hotkeys={"screen_clip": (0, 1)}, hotkey_generation=8,
                                 hotkey_action_running=False, _trigger_screen_clip_hotkey=Mock())
        with patch.object(module, "active_hotkey_editor", return_value=None):
            MainWindow._trigger_hotkey_action(window, "screen_clip", 7)
        window._trigger_screen_clip_hotkey.assert_not_called()

    def test_page_diagnostics_cannot_override_request_or_break_delivery(self):
        events = [{"event": "response_observed", "fields": {
            "event": "foreign", "request_id": "2" * 32, "level": "CRITICAL",
            123: "invalid-key", "response_count": 2,
        }}]
        with patch.object(module, "log_event") as log:
            MainWindow._log_page_diagnostics(SimpleNamespace(), events, "1" * 32)
        log.assert_called_once_with("page.response_observed", request_id="1" * 32, response_count=2)

    def test_partial_progress_does_not_become_ready_or_notify(self):
        window = SimpleNamespace(latest_translation_request_id='1' * 32,
                                 _store_translation_result=Mock(), _save_last_run_status=Mock())
        handler, state = MainWindow._build_response_progress_handler(
            window, copy_to_clipboard=False, show_overlay=True, play_sound=True, request_id='1' * 32)
        handler({'kind': 'assistant_response', 'text': 'Részleges válasz', 'complete': False})
        window._store_translation_result.assert_not_called()
        self.assertEqual(state['last_text'], ''); self.assertFalse(state['notified'])
        handler({'kind': 'assistant_response', 'text': 'Részleges válasz', 'complete': True})
        window._store_translation_result.assert_called_once()
        self.assertEqual(state['last_text'], 'Részleges válasz'); self.assertTrue(state['notified'])

    def test_partial_store_cannot_enable_cached_typing(self):
        window = SimpleNamespace(latest_translation_request_id='1' * 32,
                                 last_translated_text='', translation_result_complete=False,
                                 translation_result_request_id='', store=Mock(), clipboard=Mock())
        MainWindow._store_translation_result(window, 'Részleges', copy_to_clipboard=True,
            show_overlay=False, play_sound=False, request_id='1' * 32, complete=False)
        self.assertFalse(window.translation_result_complete)
        self.assertEqual(window.last_translated_text, '')
        window.store.save_last_translated_text.assert_not_called()
        window.clipboard.setText.assert_not_called()

    def test_image_response_is_cached_with_clipboard_copy_disabled(self):
        settings = AppSettings(copy_response_to_clipboard=False, ocr_text_from_clipboard_image=False)
        request_id = '1' * 32
        window = SimpleNamespace(settings=settings, latest_translation_request_id=request_id,
            translation_result_request_id='', translation_result_complete=False, last_translated_text='',
            store=Mock(), clipboard=Mock(), clipboard_translation_in_progress=False,
            pending_clipboard_payload=None, _read_settings_from_form=lambda: settings,
            _touch_clipboard_translation_heartbeat=Mock(), _begin_browser_interaction=Mock(),
            _end_browser_interaction=Mock(), _save_last_run_status=Mock(), _set_live_status=Mock(),
            _show_loading_overlay=Mock(), _hide_translation_overlay=Mock(),
            _show_translation_overlay=Mock(), _play_ready_sound=Mock(),
            _ensure_chatgpt_page_loaded=Mock(), _ensure_automation_ready=Mock())
        window._build_translation_delivery_payload = lambda payload: MainWindow._build_translation_delivery_payload(window, payload)
        window._build_response_progress_handler = lambda **kwargs: MainWindow._build_response_progress_handler(window, **kwargs)
        window._store_translation_result = lambda text, **kwargs: MainWindow._store_translation_result(window, text, **kwargs)
        def execute(payload, *, progress_handler):
            self.assertTrue(payload['waitForResponse']); self.assertFalse(payload['copyResponseToClipboard'])
            progress_handler({'kind': 'assistant_response', 'text': 'Elkészült fordítás', 'complete': True})
            return {'ok': True, 'assistantResponseText': 'Elkészült fordítás', 'assistantResponseComplete': True}
        window._execute_delivery = execute
        MainWindow._process_clipboard_translation(window, {'requestId': request_id,
            'imageDataUrl': 'data:image/png;base64,aGVsbG8=', 'imageMimeType': 'image/png', 'imageFilename': 'synthetic.png'})
        self.assertEqual(window.last_translated_text, 'Elkészült fordítás')
        self.assertTrue(window.translation_result_complete)
        self.assertEqual(window.translation_result_request_id, request_id)
        window.store.save_last_translated_text.assert_called_once_with('Elkészült fordítás')
        window.clipboard.setText.assert_not_called()

    def test_final_bucket_is_drained_at_deadline_and_idle_deadline(self):
        for waiting, now in ((True, 220.05), (False, 125.0)):
            with self.subTest(waiting=waiting):
                progress = {'kind': 'assistant_response', 'text': 'Végső válasz', 'complete': True, 'done': True, 'seq': 2}
                observed = []
                window = SimpleNamespace(response_followup_progress_call_id='followup', response_followup_request_id='1'*32,
                    latest_translation_request_id='1'*32, response_followup_started_monotonic=100.0,
                    response_followup_last_activity_monotonic=100.0, response_followup_waiting_for_first_response=waiting,
                    response_followup_last_sequence=0, response_followup_error_count=0,
                    response_followup_handler=lambda record: observed.append(record['text']),
                    _run_javascript=Mock(return_value=json.dumps({'progress': json.dumps(progress), 'diagnostics': []})),
                    _stop_response_followup_polling=lambda **kwargs: observed.append('stopped'))
                with patch.object(module.time, 'monotonic', return_value=now):
                    MainWindow._poll_response_followup_progress(window)
                self.assertEqual(observed, ['Végső válasz', 'stopped'])
                window._run_javascript.assert_called_once()

    def test_empty_final_drain_still_stops_expired_followup(self):
        window = SimpleNamespace(response_followup_progress_call_id='followup', response_followup_request_id='1'*32,
            latest_translation_request_id='1'*32, response_followup_started_monotonic=100.0,
            response_followup_last_activity_monotonic=100.0, response_followup_waiting_for_first_response=True,
            response_followup_last_sequence=0, _run_javascript=Mock(return_value=json.dumps({'progress': None, 'diagnostics': []})),
            _stop_response_followup_polling=Mock())
        with patch.object(module.time, 'monotonic', return_value=220.05):
            MainWindow._poll_response_followup_progress(window)
        window._run_javascript.assert_called_once(); window._stop_response_followup_polling.assert_called_once()

    def test_invalidation_resets_completion_flag(self):
        window = SimpleNamespace(last_translated_text='Előző fordítás', translation_result_complete=True, store=Mock())
        MainWindow._invalidate_translation_result(window, '2'*32, 'image')
        self.assertFalse(window.translation_result_complete); self.assertEqual(window.last_translated_text, '')

    def test_closing_cancels_quick_chat_without_error_status(self):
        settings = AppSettings()
        window = SimpleNamespace(settings=settings, last_translated_text='', store=Mock(),
            quick_chat_overlay=SimpleNamespace(hide_overlay=Mock(), show_error=Mock()),
            clipboard_translation_in_progress=False, browser_interaction_active=False,
            _read_settings_from_form=lambda: settings, _begin_browser_interaction=Mock(), _end_browser_interaction=Mock(),
            _show_loading_overlay=Mock(), _hide_translation_overlay=Mock(), _save_last_run_status=Mock(),
            _ensure_chatgpt_page_loaded=Mock(), _ensure_automation_ready=Mock(),
            _build_quick_chat_translation_prompt=lambda text: text,
            _build_response_progress_handler=lambda **kwargs: (Mock(), {'last_text': '', 'notified': False}),
            _execute_delivery=Mock(side_effect=module.BrowserOperationCancelled()))
        with patch.object(module, 'log_exception') as errors:
            MainWindow._process_quick_chat_translation(window, 'Mesterséges kérés')
        errors.assert_not_called()
        window._hide_translation_overlay.assert_not_called()
        window._save_last_run_status.assert_called_once_with('A gyors chat szöveg elküldése folyamatban.')
        window._end_browser_interaction.assert_called_once()

    def test_closing_cancels_followup_without_timeout_error(self):
        window = SimpleNamespace(response_followup_progress_call_id='followup', response_followup_request_id='1'*32,
            latest_translation_request_id='1'*32, response_followup_started_monotonic=100.0,
            response_followup_last_activity_monotonic=100.0, response_followup_waiting_for_first_response=True,
            _run_javascript=Mock(side_effect=module.BrowserOperationCancelled()), _stop_response_followup_polling=Mock())
        with patch.object(module.time, 'monotonic', return_value=110.0), patch.object(module, 'log_exception') as errors:
            MainWindow._poll_response_followup_progress(window)
        errors.assert_not_called(); window._stop_response_followup_polling.assert_called_once_with(stop_remote=False)


if __name__ == "__main__":
    unittest.main()
