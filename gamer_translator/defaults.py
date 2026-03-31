from __future__ import annotations

APP_NAME = "Gamer Translator"
WINDOW_TITLE = APP_NAME
CHATGPT_URL = "https://chatgpt.com/"
LEGACY_HUNGARIAN_PROMPT = "From now on, whenever I send an image, translate all visible text in it into Hungarian. Return only the Hungarian translation, with no extra commentary unless I ask."
DEFAULT_ENGLISH_PROMPT = "From now on, whenever I send an image, translate all visible text in it into English. Return only the English translation, with no extra commentary unless I ask."
LEGACY_BIDIRECTIONAL_PROMPT = "From now on, whenever I send an image, detect whether the visible text is primarily Hungarian or English. If it is Hungarian, translate it into English. If it is English, translate it into Hungarian. Return only the translation, with no extra commentary unless I ask."
DEFAULT_BIDIRECTIONAL_PROMPT = "From now on, whenever I send an image, detect whether the visible text is primarily Hungarian or not. If it is Hungarian, translate it into English. If it is any language other than Hungarian, translate it into Hungarian. Return only the translation, with no extra commentary unless I ask."
DEFAULT_SETTINGS = {
    "monitoringEnabled": True,
    "chatgptUrl": CHATGPT_URL,
    "keepChatGptInBackground": True,
    "promptTemplate": DEFAULT_BIDIRECTIONAL_PROMPT,
    "autoSubmit": True,
    "copyResponseToClipboard": True,
    "typeOutHotkeyEnabled": True,
    "typeOutHotkey": "Alt+V",
    "screenClipHotkeyEnabled": True,
    "screenClipHotkey": "Alt+C",
    "pageLoadDelayMs": 0,
    "pageReadyTimeoutMs": 25000,
    "beforeSubmitDelayMs": 0,
    "afterAttachDelayMs": 0,
}
CHATGPT_HOSTS = ("chatgpt.com", "chat.openai.com")
