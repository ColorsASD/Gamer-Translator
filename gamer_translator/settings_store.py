from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import (
    DEFAULT_BIDIRECTIONAL_PROMPT,
    DEFAULT_SETTINGS,
    IMAGE_ONLY_BIDIRECTIONAL_PROMPT,
    LEGACY_BIDIRECTIONAL_PROMPT,
    PREVIOUS_BACKGROUND_KEEPALIVE_BIDIRECTIONAL_PROMPT,
    PREVIOUS_BACKGROUND_KEEPALIVE_INTERVAL_BIDIRECTIONAL_PROMPT,
    PREVIOUS_DEFAULT_BIDIRECTIONAL_PROMPT,
    PREVIOUS_BIDIRECTIONAL_PROMPT,
    PREVIOUS_OCR_RECONSTRUCTION_PROMPT,
    PREVIOUS_QUICK_CHAT_BIDIRECTIONAL_PROMPT,
    PREVIOUS_TEXT_AND_IMAGE_BIDIRECTIONAL_PROMPT,
)


def default_app_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        return Path(local_app_data) / "Gamer Translator"

    return Path.home() / ".gamer-translator"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AppSettings:
    monitoring_enabled: bool = bool(DEFAULT_SETTINGS["monitoringEnabled"])
    chatgpt_url: str = str(DEFAULT_SETTINGS["chatgptUrl"])
    keep_chatgpt_in_background: bool = bool(DEFAULT_SETTINGS["keepChatGptInBackground"])
    game_mode_enabled: bool = bool(DEFAULT_SETTINGS["gameModeEnabled"])
    prompt_template: str = str(DEFAULT_SETTINGS["promptTemplate"])
    auto_submit: bool = bool(DEFAULT_SETTINGS["autoSubmit"])
    copy_response_to_clipboard: bool = bool(DEFAULT_SETTINGS["copyResponseToClipboard"])
    ocr_text_from_clipboard_image: bool = bool(DEFAULT_SETTINGS["ocrTextFromClipboardImage"])
    webview_gpu_acceleration_enabled: bool = bool(DEFAULT_SETTINGS["webViewGpuAccelerationEnabled"])
    type_out_hotkey_enabled: bool = bool(DEFAULT_SETTINGS["typeOutHotkeyEnabled"])
    type_out_hotkey: str = str(DEFAULT_SETTINGS["typeOutHotkey"])
    screen_clip_hotkey_enabled: bool = bool(DEFAULT_SETTINGS["screenClipHotkeyEnabled"])
    screen_clip_hotkey: str = str(DEFAULT_SETTINGS["screenClipHotkey"])
    quick_chat_hotkey_enabled: bool = bool(DEFAULT_SETTINGS["quickChatHotkeyEnabled"])
    quick_chat_hotkey: str = str(DEFAULT_SETTINGS["quickChatHotkey"])
    overlay_opacity_percent: int = int(DEFAULT_SETTINGS["overlayOpacityPercent"])
    overlay_duration_seconds: int = int(DEFAULT_SETTINGS["overlayDurationSeconds"])
    page_ready_timeout_ms: int = int(DEFAULT_SETTINGS["pageReadyTimeoutMs"])

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "AppSettings":
        raw = raw if isinstance(raw, dict) else {}
        type_out_hotkey = str(raw.get("typeOutHotkey", DEFAULT_SETTINGS["typeOutHotkey"]) or DEFAULT_SETTINGS["typeOutHotkey"])
        screen_clip_hotkey = str(raw.get("screenClipHotkey", DEFAULT_SETTINGS["screenClipHotkey"]) or DEFAULT_SETTINGS["screenClipHotkey"])
        quick_chat_hotkey = str(raw.get("quickChatHotkey", DEFAULT_SETTINGS["quickChatHotkey"]) or DEFAULT_SETTINGS["quickChatHotkey"])
        prompt_template = str(raw.get("promptTemplate", DEFAULT_SETTINGS["promptTemplate"]) or DEFAULT_SETTINGS["promptTemplate"])

        if "screenClipHotkey" not in raw and type_out_hotkey == "Ctrl+Alt+Shift+V":
            type_out_hotkey = str(DEFAULT_SETTINGS["typeOutHotkey"])

        if type_out_hotkey == "F6":
            type_out_hotkey = str(DEFAULT_SETTINGS["typeOutHotkey"])

        if screen_clip_hotkey == "F5":
            screen_clip_hotkey = str(DEFAULT_SETTINGS["screenClipHotkey"])

        if prompt_template in {
            LEGACY_BIDIRECTIONAL_PROMPT,
            PREVIOUS_BIDIRECTIONAL_PROMPT,
            IMAGE_ONLY_BIDIRECTIONAL_PROMPT,
            PREVIOUS_TEXT_AND_IMAGE_BIDIRECTIONAL_PROMPT,
            PREVIOUS_OCR_RECONSTRUCTION_PROMPT,
            PREVIOUS_DEFAULT_BIDIRECTIONAL_PROMPT,
            PREVIOUS_QUICK_CHAT_BIDIRECTIONAL_PROMPT,
            PREVIOUS_BACKGROUND_KEEPALIVE_BIDIRECTIONAL_PROMPT,
            PREVIOUS_BACKGROUND_KEEPALIVE_INTERVAL_BIDIRECTIONAL_PROMPT,
        }:
            prompt_template = DEFAULT_BIDIRECTIONAL_PROMPT

        return cls(
            monitoring_enabled=coerce_bool(raw.get("monitoringEnabled"), DEFAULT_SETTINGS["monitoringEnabled"]),
            chatgpt_url=str(raw.get("chatgptUrl", DEFAULT_SETTINGS["chatgptUrl"]) or DEFAULT_SETTINGS["chatgptUrl"]),
            keep_chatgpt_in_background=coerce_bool(raw.get("keepChatGptInBackground"), DEFAULT_SETTINGS["keepChatGptInBackground"]),
            game_mode_enabled=coerce_bool(raw.get("gameModeEnabled"), DEFAULT_SETTINGS["gameModeEnabled"]),
            prompt_template=prompt_template,
            auto_submit=True,
            copy_response_to_clipboard=coerce_bool(raw.get("copyResponseToClipboard"), DEFAULT_SETTINGS["copyResponseToClipboard"]),
            ocr_text_from_clipboard_image=coerce_bool(raw.get("ocrTextFromClipboardImage"), DEFAULT_SETTINGS["ocrTextFromClipboardImage"]),
            webview_gpu_acceleration_enabled=coerce_bool(raw.get("webViewGpuAccelerationEnabled"), DEFAULT_SETTINGS["webViewGpuAccelerationEnabled"]),
            type_out_hotkey_enabled=coerce_bool(raw.get("typeOutHotkeyEnabled"), DEFAULT_SETTINGS["typeOutHotkeyEnabled"]),
            type_out_hotkey=type_out_hotkey,
            screen_clip_hotkey_enabled=coerce_bool(raw.get("screenClipHotkeyEnabled"), DEFAULT_SETTINGS["screenClipHotkeyEnabled"]),
            screen_clip_hotkey=screen_clip_hotkey,
            quick_chat_hotkey_enabled=coerce_bool(raw.get("quickChatHotkeyEnabled"), DEFAULT_SETTINGS["quickChatHotkeyEnabled"]),
            quick_chat_hotkey=quick_chat_hotkey,
            overlay_opacity_percent=max(1, min(100, coerce_int(raw.get("overlayOpacityPercent"), DEFAULT_SETTINGS["overlayOpacityPercent"]))),
            overlay_duration_seconds=max(1, min(120, coerce_int(raw.get("overlayDurationSeconds"), DEFAULT_SETTINGS["overlayDurationSeconds"]))),
            page_ready_timeout_ms=max(1000, min(120000, coerce_int(raw.get("pageReadyTimeoutMs"), DEFAULT_SETTINGS["pageReadyTimeoutMs"]))),
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return {
            "monitoringEnabled": raw["monitoring_enabled"],
            "chatgptUrl": raw["chatgpt_url"],
            "keepChatGptInBackground": raw["keep_chatgpt_in_background"],
            "gameModeEnabled": raw["game_mode_enabled"],
            "promptTemplate": raw["prompt_template"],
            "autoSubmit": True,
            "copyResponseToClipboard": raw["copy_response_to_clipboard"],
            "ocrTextFromClipboardImage": raw["ocr_text_from_clipboard_image"],
            "webViewGpuAccelerationEnabled": raw["webview_gpu_acceleration_enabled"],
            "typeOutHotkeyEnabled": raw["type_out_hotkey_enabled"],
            "typeOutHotkey": raw["type_out_hotkey"],
            "screenClipHotkeyEnabled": raw["screen_clip_hotkey_enabled"],
            "screenClipHotkey": raw["screen_clip_hotkey"],
            "quickChatHotkeyEnabled": raw["quick_chat_hotkey_enabled"],
            "quickChatHotkey": raw["quick_chat_hotkey"],
            "overlayOpacityPercent": raw["overlay_opacity_percent"],
            "overlayDurationSeconds": raw["overlay_duration_seconds"],
            "pageReadyTimeoutMs": raw["page_ready_timeout_ms"],
        }


@dataclass(slots=True)
class LastRunStatus:
    at: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "LastRunStatus":
        raw = raw if isinstance(raw, dict) else {}
        return cls(
            at=str(raw.get("at", "") or ""),
            message=str(raw.get("message", "") or ""),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "at": self.at,
            "message": self.message,
        }


class SettingsStore:
    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or default_app_data_dir()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.browser_dir = self.root_dir / "browser"
        self.browser_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.root_dir / "settings.json"
        self._document_cache: dict[str, Any] | None = None

    def load_settings(self) -> AppSettings:
        return AppSettings.from_dict(self._read_document().get("settings"))

    def save_settings(self, settings: AppSettings) -> None:
        document = self._read_document()
        document["settings"] = settings.to_dict()
        self._write_document(document)

    def load_last_run_status(self) -> LastRunStatus:
        return LastRunStatus.from_dict(self._read_document().get("lastRunStatus"))

    def save_last_run_status(self, message: str) -> LastRunStatus:
        document = self._read_document()
        status = LastRunStatus(at=utc_now_iso(), message=str(message))
        document["lastRunStatus"] = status.to_dict()
        self._write_document(document)
        return status

    def load_last_translated_text(self) -> str:
        return str(self._read_document().get("lastTranslatedText", "") or "")

    def save_last_translated_text(self, text: str) -> None:
        document = self._read_document()
        document["lastTranslatedText"] = str(text or "")
        self._write_document(document)

    def _read_document(self) -> dict[str, Any]:
        if self._document_cache is not None:
            return dict(self._document_cache)

        try:
            document = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeError, OSError):
            return {}

        if not isinstance(document, dict):
            return {}

        self._document_cache = dict(document)
        return dict(document)

    def _write_document(self, document: dict[str, Any]) -> None:
        if self._document_cache == document:
            return

        # Az atomikus csere megszakadt mentéskor is megőrzi az előző beállításokat.
        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root_dir, prefix=".settings-", suffix=".tmp", delete=False) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(document, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            os.replace(temporary_path, self.config_path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        self._document_cache = dict(document)


def coerce_bool(value: Any, fallback: bool) -> bool:
    if isinstance(value, bool):
        return value

    # A kézzel szerkesztett "false" érték sem kapcsolhatja be a vágólapfigyelést.
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"

    return bool(fallback)


def coerce_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return int(fallback)

    return parsed
