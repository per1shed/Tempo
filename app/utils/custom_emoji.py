"""Premium custom emoji из стикерпаков пользователя."""

from __future__ import annotations

# ключ → (custom_emoji_id, alt)
# alt должен совпадать с emoji стикера в Telegram — иначе дублируется fallback
# Паки: AdaptiveStatus, SuperAdminKoylli, DClickEmoji, FragmentIcons,
#       TgAndroidIcons, IconsInTg
EMOJI: dict[str, tuple[str, str]] = {
    # AdaptiveStatus
    "person": ("5319007286004299794", "👋"),
    "check": ("5316653334688446735", "✅"),
    "gym": ("5316595051982239381", "💪"),
    "phys": ("5316963916658522983", "🫀"),
    "star": ("5316765712507747050", "🧠"),
    "sleep": ("5316982535341750234", "💤"),
    "sun": ("5318861536289108970", "☀️"),
    "moon": ("5316710702566619149", "🌙"),
    "warn": ("5316554554735607106", "⚠️"),
    "bell": ("5316773525053258010", "🔔"),
    "fire": ("5316924123786524990", "🔥"),
    # SuperAdminKoylli
    "cross": ("5336769136141811523", "❌"),
    "trash": ("5337017423906226569", "🔴"),
    # DClickEmoji
    "settings": ("5262614107709789636", "🔘"),
    "chat": ("5264860178037101093", "💬"),
    "play": ("5262949729339201712", "▶️"),
    "chart": ("5265014582111396470", "📈"),
    "stats": ("5267318205000471835", "📊"),
    "mark": ("5879841310902324730", "✏️"),
    # FragmentIcons
    "money": ("5328171590867768723", "💲"),
    # TgAndroidIcons
    "book": ("5195450074854865713", "📝"),
    "folder": ("5875206779196935950", "📁"),
    "home": ("5967822972931542886", "🏠"),
    "party": ("5994502837327892086", "🎉"),
    "gift": ("6032937473162614352", "🎁"),
    "crown": ("5807868868886009920", "👑"),
    "refresh": ("5877410604225924969", "🔄"),
    "calendar": ("5967412305338568701", "📅"),
    "plus": ("5775937998948404844", "➕"),
    "timer": ("5877613700344450910", "⏲"),
    "alarm": ("5985616167740379273", "⏰"),
    "uni": ("5992157823838984339", "🎓"),
    "ai": ("5931415565955503486", "🤖"),
    "it": ("5877318502947229960", "💻"),
    # IconsInTg
    "clock": ("5976544483846654540", "⏲"),
    # decorrat
    "line": ("5465143565430566413", "➿"),
}

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

# Невидимый символ для кнопки «только иконка» (без дубля emoji в тексте)
_ICON_ONLY_TEXT = "\u2800"

# Кнопки: только MintEmoji2025 (alt должен совпадать со стикером)
BUTTON_EMOJI: dict[str, tuple[str, str]] = {
    "home": ("5967822972931542886", "🏠"),
    "stats": ("5375380522765679294", "📈"),
    "money": ("5375218203066663939", "👛"),
    "book": ("5373140564176826934", "📝"),
    "timer": ("5375363394436109945", "🕖"),
    "alarm": ("5375419774471796186", "🔔"),
    "plus": ("5395806910484083234", "✨"),
    "refresh": ("5877410604225924969", "🔄"),
    "reset": ("5372929943275598657", "🚫"),
    "sw_start": ("5262949729339201712", "▶️"),
    "sw_continue": ("6026302448769961329", "⏩"),
    "sw_pause": ("5372990734242706763", "⬅️"),
    "sw_lap": ("5775937998948404844", "➕"),
    "sw_refresh": ("5974326631454477674", "🔃"),
    "sw_reset": ("5375386290906755934", "🗑"),
    "cross": ("5375557664396835394", "❌"),
    "uni": ("5375497341581159904", "🌟"),
    "bell": ("5375419774471796186", "🔔"),
    "settings": ("5375107165277158175", "⚙️"),
    "calendar": ("5372929307620440846", "📌"),
    "trash": ("5375386290906755934", "🗑"),
    "mark": ("5375225337007337355", "🖌"),
    "edit": ("5879841310902324730", "✏️"),
    "phys": ("5316595051982239381", "💪"),
    "star": ("5316765712507747050", "🧠"),
    "play": ("5375353138054198975", "➡️"),
    "folder": ("5375473611886849332", "🖼"),
    "check": ("5372821765934317546", "✅"),
    "chat": ("5373293391998121666", "💬"),
    "chart": ("5375380522765679294", "📈"),
    "gift": ("5372870213165412912", "🎁"),
    "crown": ("5458590115351793560", "👑"),
    "fire": ("5375204965977454908", "🔥"),
    "sun": ("5375226973389882317", "☀️"),
    "person": ("5375504342377852839", "👋"),
    "ai": ("5375385556467349282", "🤖"),
    "warn": ("5420461938318541150", "❗️"),
}


def ce(key: str) -> str:
    """HTML custom emoji для ParseMode.HTML."""
    emoji_id, alt = EMOJI[key]
    return f'<tg-emoji emoji-id="{emoji_id}">{alt}</tg-emoji>'



def icon_id(key: str) -> str:
    """custom_emoji_id для кнопок — MintEmoji2025."""
    if key in BUTTON_EMOJI:
        return BUTTON_EMOJI[key][0]
    return EMOJI[key][0]


def icon_only_text() -> str:
    """Плейсхолдер для icon-only кнопок."""
    return _ICON_ONLY_TEXT


def icon_label(key: str, text: str) -> str:
    """Emoji вплотную к тексту кнопки (без icon_custom_emoji_id и пробела)."""
    src = BUTTON_EMOJI.get(key) or EMOJI[key]
    return f"{src[1]}{text}"


def block_ce(kind: str | object) -> str:
    """Custom emoji для блока расписания."""
    value = getattr(kind, "value", kind)
    return ce(BLOCK_EMOJI.get(str(value), "bell"))
