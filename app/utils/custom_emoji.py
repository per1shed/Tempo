"""Custom emoji из пака TgAndroidIcons (t.me/addemoji/TgAndroidIcons)."""

from __future__ import annotations

# curated ids: роль → (custom_emoji_id, unicode fallback)
EMOJI = {
    "person": ("5879770735999717115", "👤"),
    "calendar": ("5967412305338568701", "📅"),
    "clock": ("5776213190387961618", "🕓"),
    "alarm": ("5985616167740379273", "⏰"),
    "timer": ("5877613700344450910", "⏲"),
    "sleep": ("5886366951067883092", "💤"),
    "sun": ("6005924903419646424", "🌞"),
    "moon": ("6005928962163742139", "🌝"),
    "chart": ("5994378914636500516", "📈"),
    "stats": ("5877485980901971030", "📊"),
    "weight": ("5913702317667913862", "📊"),
    "ai": ("5819078828017849357", "🤖"),
    "settings": ("5877260593903177342", "⚙"),
    "party": ("5994502837327892086", "🎉"),
    "check": ("5776375003280838798", "✅"),
    "cross": ("5778527486270770928", "❌"),
    "plus": ("5775937998948404844", "➕"),
    "fire": ("5843553939672274145", "⚡️"),
    "star": ("5958376256788502078", "⭐️"),
    "money": ("5967390100357648692", "💵"),
    "crown": ("5807868868886009920", "👑"),
    "book": ("5897850551156084824", "📖"),
    "gym": ("5994323406479167187", "⚽️"),
    "home": ("5967822972931542886", "🏠"),
    "chat": ("5886666250158870040", "💬"),
    "warn": ("5881702736843511327", "⚠️"),
    "gift": ("6032937473162614352", "🎁"),
    "uni": ("5992157823838984339", "🎓"),
    "it": ("5877318502947229960", "💻"),
    "bell": ("5909201569898827582", "🔔"),
}

STICKER_SET_NAME = "TgAndroidIcons"

# BlockKind.value → ключ из EMOJI
BLOCK_EMOJI = {
    "routine_morning": "sun",
    "university": "uni",
    "study": "book",
    "english": "chat",
    "gym": "gym",
    "it": "it",
    "routine_evening": "moon",
    "sleep": "sleep",
    "recovery": "party",
    "free": "clock",
}


def ce(key: str) -> str:
    """HTML custom emoji для ParseMode.HTML."""
    emoji_id, fallback = EMOJI[key]
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def icon_id(key: str) -> str:
    """custom_emoji_id для icon_custom_emoji_id на кнопках."""
    return EMOJI[key][0]


def block_ce(kind: str | object) -> str:
    """Custom emoji для блока расписания."""
    value = getattr(kind, "value", kind)
    return ce(BLOCK_EMOJI.get(str(value), "bell"))
