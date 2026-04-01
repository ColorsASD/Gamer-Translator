from __future__ import annotations

APP_NAME = "Gamer Translator"
WINDOW_TITLE = APP_NAME
CHATGPT_URL = "https://chatgpt.com/"
LEGACY_HUNGARIAN_PROMPT = "From now on, whenever I send an image, translate all visible text in it into Hungarian. Return only the Hungarian translation, with no extra commentary unless I ask."
DEFAULT_ENGLISH_PROMPT = "From now on, whenever I send an image, translate all visible text in it into English. Return only the English translation, with no extra commentary unless I ask."
LEGACY_BIDIRECTIONAL_PROMPT = "From now on, whenever I send an image, detect whether the visible text is primarily Hungarian or English. If it is Hungarian, translate it into English. If it is English, translate it into Hungarian. Return only the translation, with no extra commentary unless I ask."
PREVIOUS_BIDIRECTIONAL_PROMPT = "From now on, whenever I send an image, detect whether the visible text is primarily Hungarian or not. If it is Hungarian, translate it into English. If it is any language other than Hungarian, translate it into Hungarian. Return only the translation, with no extra commentary unless I ask."
DEFAULT_BIDIRECTIONAL_PROMPT = (
    "From now on, whenever I send an image, detect whether the visible text is primarily Hungarian or not. "
    "If it is primarily Hungarian, translate it into natural, fluent English. "
    "If it is any language other than Hungarian, translate it into natural Hungarian.\n\n"
    "Translate by intended meaning, not word-for-word. If the text contains gaming slang, internet slang, abbreviations, memes, insults, or casual chat language, interpret and translate them the way they are actually used by gamers online, not just by dictionary meaning.\n\n"
    "When translating from Hungarian into English, prefer natural gamer-style English that sounds like something a real player would actually say in chat.\n\n"
    "Preserve the original tone and style. Keep it casual, aggressive, sarcastic, funny, competitive, or rude if that matches the source. Do not over-formalize the wording, and do not sanitize the tone.\n\n"
    "Keep proper nouns unchanged unless there is a very common natural translation. This includes usernames, server names, game titles, map names, item names, ranks, commands, keybinds, and brand names.\n\n"
    "If a word or phrase has multiple possible meanings, prefer the meaning that best fits general gaming context. Choose natural gamer-style wording over textbook phrasing whenever appropriate.\n\n"
    "Return only the final translation, with no extra commentary, labels, quotation marks, or explanations unless I explicitly ask for them."
)
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
    "overlayOpacityPercent": 50,
    "overlayDurationSeconds": 30,
    "pageLoadDelayMs": 0,
    "pageReadyTimeoutMs": 25000,
    "beforeSubmitDelayMs": 0,
    "afterAttachDelayMs": 0,
}
CHATGPT_HOSTS = ("chatgpt.com", "chat.openai.com")
