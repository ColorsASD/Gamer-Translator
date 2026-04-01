from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .defaults import DEFAULT_BIDIRECTIONAL_PROMPT, DEFAULT_SETTINGS, LEGACY_BIDIRECTIONAL_PROMPT, PREVIOUS_BIDIRECTIONAL_PROMPT


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
    prompt_template: str = str(DEFAULT_SETTINGS["promptTemplate"])
    auto_submit: bool = bool(DEFAULT_SETTINGS["autoSubmit"])
    copy_response_to_clipboard: bool = bool(DEFAULT_SETTINGS["copyResponseToClipboard"])
    type_out_hotkey_enabled: bool = bool(DEFAULT_SETTINGS["typeOutHotkeyEnabled"])
    type_out_hotkey: str = str(DEFAULT_SETTINGS["typeOutHotkey"])
    screen_clip_hotkey_enabled: bool = bool(DEFAULT_SETTINGS["screenClipHotkeyEnabled"])
    screen_clip_hotkey: str = str(DEFAULT_SETTINGS["screenClipHotkey"])
    overlay_opacity_percent: int = int(DEFAULT_SETTINGS["overlayOpacityPercent"])
    overlay_duration_seconds: int = int(DEFAULT_SETTINGS["overlayDurationSeconds"])
    page_load_delay_ms: int = int(DEFAULT_SETTINGS["pageLoadDelayMs"])
    page_ready_timeout_ms: int = int(DEFAULT_SETTINGS["pageReadyTimeoutMs"])
    before_submit_delay_ms: int = int(DEFAULT_SETTINGS["beforeSubmitDelayMs"])
    after_attach_delay_ms: int = int(DEFAULT_SETTINGS["afterAttachDelayMs"])

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "AppSettings":
        raw = raw or {}
        type_out_hotkey = str(raw.get("typeOutHotkey", DEFAULT_SETTINGS["typeOutHotkey"]) or DEFAULT_SETTINGS["typeOutHotkey"])
        screen_clip_hotkey = str(raw.get("screenClipHotkey", DEFAULT_SETTINGS["screenClipHotkey"]) or DEFAULT_SETTINGS["screenClipHotkey"])
        prompt_template = str(raw.get("promptTemplate", DEFAULT_SETTINGS["promptTemplate"]) or DEFAULT_SETTINGS["promptTemplate"])

        if "screenClipHotkey" not in raw and type_out_hotkey == "Ctrl+Alt+Shift+V":
            type_out_hotkey = str(DEFAULT_SETTINGS["typeOutHotkey"])

        if type_out_hotkey == "F6":
            type_out_hotkey = str(DEFAULT_SETTINGS["typeOutHotkey"])

        if screen_clip_hotkey == "F5":
            screen_clip_hotkey = str(DEFAULT_SETTINGS["screenClipHotkey"])

        if prompt_template in {LEGACY_BIDIRECTIONAL_PROMPT, PREVIOUS_BIDIRECTIONAL_PROMPT}:
            prompt_template = DEFAULT_BIDIRECTIONAL_PROMPT

        return cls(
            monitoring_enabled=bool(raw.get("monitoringEnabled", DEFAULT_SETTINGS["monitoringEnabled"])),
            chatgpt_url=str(raw.get("chatgptUrl", DEFAULT_SETTINGS["chatgptUrl"]) or DEFAULT_SETTINGS["chatgptUrl"]),
            keep_chatgpt_in_background=bool(raw.get("keepChatGptInBackground", DEFAULT_SETTINGS["keepChatGptInBackground"])),
            prompt_template=prompt_template,
            auto_submit=True,
            copy_response_to_clipboard=bool(raw.get("copyResponseToClipboard", DEFAULT_SETTINGS["copyResponseToClipboard"])),
            type_out_hotkey_enabled=bool(raw.get("typeOutHotkeyEnabled", DEFAULT_SETTINGS["typeOutHotkeyEnabled"])),
            type_out_hotkey=type_out_hotkey,
            screen_clip_hotkey_enabled=bool(raw.get("screenClipHotkeyEnabled", DEFAULT_SETTINGS["screenClipHotkeyEnabled"])),
            screen_clip_hotkey=screen_clip_hotkey,
            overlay_opacity_percent=coerce_int(raw.get("overlayOpacityPercent"), DEFAULT_SETTINGS["overlayOpacityPercent"]),
            overlay_duration_seconds=coerce_int(raw.get("overlayDurationSeconds"), DEFAULT_SETTINGS["overlayDurationSeconds"]),
            page_load_delay_ms=coerce_int(raw.get("pageLoadDelayMs"), DEFAULT_SETTINGS["pageLoadDelayMs"]),
            page_ready_timeout_ms=coerce_int(raw.get("pageReadyTimeoutMs"), DEFAULT_SETTINGS["pageReadyTimeoutMs"]),
            before_submit_delay_ms=coerce_int(raw.get("beforeSubmitDelayMs"), DEFAULT_SETTINGS["beforeSubmitDelayMs"]),
            after_attach_delay_ms=coerce_int(raw.get("afterAttachDelayMs"), DEFAULT_SETTINGS["afterAttachDelayMs"]),
        )

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        return {
            "monitoringEnabled": raw["monitoring_enabled"],
            "chatgptUrl": raw["chatgpt_url"],
            "keepChatGptInBackground": raw["keep_chatgpt_in_background"],
            "promptTemplate": raw["prompt_template"],
            "autoSubmit": True,
            "copyResponseToClipboard": raw["copy_response_to_clipboard"],
            "typeOutHotkeyEnabled": raw["type_out_hotkey_enabled"],
            "typeOutHotkey": raw["type_out_hotkey"],
            "screenClipHotkeyEnabled": raw["screen_clip_hotkey_enabled"],
            "screenClipHotkey": raw["screen_clip_hotkey"],
            "overlayOpacityPercent": raw["overlay_opacity_percent"],
            "overlayDurationSeconds": raw["overlay_duration_seconds"],
            "pageLoadDelayMs": raw["page_load_delay_ms"],
            "pageReadyTimeoutMs": raw["page_ready_timeout_ms"],
            "beforeSubmitDelayMs": raw["before_submit_delay_ms"],
            "afterAttachDelayMs": raw["after_attach_delay_ms"],
        }


@dataclass(slots=True)
class LastRunStatus:
    at: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "LastRunStatus":
        raw = raw or {}
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
        if not self.config_path.exists():
            return {}

        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_document(self, document: dict[str, Any]) -> None:
        self.config_path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def coerce_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return int(fallback)

    return parsed
