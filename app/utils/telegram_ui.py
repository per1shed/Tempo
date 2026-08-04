from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from app.models import UserSettings


async def clear_keyboard(bot: Bot, chat_id: int, message_id: int | None) -> None:
    if not message_id:
        return
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id, message_id=message_id, reply_markup=None
        )
    except TelegramBadRequest:
        pass


async def remember_keyboard(
    settings: UserSettings, message: Message, *, bot: Bot | None = None
) -> None:
    """Снимает кнопки с предыдущего сообщения и запоминает новое."""
    chat_id = message.chat.id
    prev = settings.last_kb_message_id
    if prev and prev != message.message_id:
        b = bot or message.bot
        await clear_keyboard(b, chat_id, prev)
    settings.last_kb_message_id = message.message_id


async def show_screen(
    callback: CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    *,
    user_settings: UserSettings | None = None,
) -> Message:
    """
    Показывает текстовый экран.
    Если есть user_settings — соблюдает правило «кнопки только у последнего».
    """
    msg = callback.message
    if msg is None:
        raise RuntimeError("callback without message")

    bot = callback.bot
    chat_id = msg.chat.id

    if user_settings and reply_markup is not None:
        await clear_keyboard(bot, chat_id, user_settings.last_kb_message_id)

    # Фото / медиа — только новое сообщение
    if msg.photo or msg.video or msg.document or msg.animation:
        sent = await msg.answer(text, reply_markup=reply_markup)
    else:
        try:
            sent = await msg.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as exc:
            if "message is not modified" in str(exc).lower():
                sent = msg
            else:
                sent = await msg.answer(text, reply_markup=reply_markup)

    if user_settings and reply_markup is not None:
        await remember_keyboard(user_settings, sent, bot=bot)
    return sent


async def send_home_card(
    bot: Bot,
    chat_id: int,
    *,
    caption: str,
    png: bytes,
    reply_markup: InlineKeyboardMarkup | None,
    user_settings: UserSettings,
) -> Message:
    """Главный экран: график дня + caption. Снимает кнопки у предыдущего."""
    await clear_keyboard(bot, chat_id, user_settings.last_kb_message_id)
    sent = await bot.send_photo(
        chat_id,
        BufferedInputFile(png, filename="today.png"),
        caption=caption,
        reply_markup=reply_markup,
    )
    if reply_markup is not None:
        await remember_keyboard(user_settings, sent, bot=bot)
    else:
        user_settings.last_kb_message_id = None
    return sent
